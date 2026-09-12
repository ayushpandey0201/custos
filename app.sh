#!/usr/bin/env bash
#
# Start Custos — backend and dashboard — with one command.
#
#     ./app.sh              start whatever is not already running
#     ./app.sh --open       ... and open the dashboard in your browser
#     ./app.sh --restart    stop everything first, then start fresh
#
# Stop it with ./stop.sh
#
# Running this twice is safe and does nothing the second time. It never stops a
# server it finds already healthy — it just tells you where it is. An earlier
# version stopped everything first "for a clean slate"; that threw away a
# working system to rebuild an identical one, and the stop-then-start sequence
# raced badly enough to kill the server it had just launched. Idempotent is
# both safer and what you actually want when you run this by reflex.
#
# Use --restart when you deliberately want fresh demo data.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$ROOT/.run"

GATEWAY_PORT=8000
CONTROL_PORT=8001
UI_PORT=5173

BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
GREEN=$'\033[32m'; RED=$'\033[31m'; CYAN=$'\033[36m'; YELLOW=$'\033[33m'

OPEN_BROWSER=0
RESTART=0
for arg in "$@"; do
    case "$arg" in
        --open)    OPEN_BROWSER=1 ;;
        --restart) RESTART=1 ;;
        -h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) printf 'unknown option: %s (try --help)\n' "$arg" >&2; exit 2 ;;
    esac
done

say()  { printf '%s\n' "$*"; }
step() { printf '%s==>%s %s\n' "$CYAN$BOLD" "$RESET" "$*"; }
note() { printf '    %s%s%s\n' "$DIM" "$*" "$RESET"; }
die()  { printf '%s!!%s %s\n' "$RED$BOLD" "$RESET" "$*" >&2; exit 1; }

backend_up() {
    curl -sf -o /dev/null --max-time 2 "http://localhost:$GATEWAY_PORT/health" \
        && curl -sf -o /dev/null --max-time 2 "http://localhost:$CONTROL_PORT/health"
}
ui_up()      { curl -sf -o /dev/null --max-time 2 "http://localhost:$UI_PORT"; }
port_busy()  { lsof -ti "tcp:$1" >/dev/null 2>&1; }

# --------------------------------------------------------------------- restart

if [ "$RESTART" = "1" ]; then
    step "Stopping everything first (--restart)"
    "$ROOT/stop.sh" --quiet
    # Give the OS a moment to actually release the listening sockets, so the
    # health checks below cannot see a half-dead server and skip starting one.
    sleep 1
fi

mkdir -p "$RUN"

BACKEND_WAS_UP=0
UI_WAS_UP=0
backend_up && BACKEND_WAS_UP=1
ui_up && UI_WAS_UP=1

# A port held by something that does not answer our health check is not our
# server. Saying so is far more useful than failing to bind three lines later.
if [ "$BACKEND_WAS_UP" = "0" ]; then
    for port in "$GATEWAY_PORT" "$CONTROL_PORT"; do
        if port_busy "$port"; then
            die "port $port is in use but not answering as Custos.
    Run ./stop.sh first, or find the process with: lsof -i tcp:$port"
        fi
    done
fi
if [ "$UI_WAS_UP" = "0" ] && port_busy "$UI_PORT"; then
    die "port $UI_PORT is in use but not serving the dashboard.
    Run ./stop.sh first, or find the process with: lsof -i tcp:$UI_PORT"
fi

# ------------------------------------------------------------- prerequisites

if [ "$BACKEND_WAS_UP" = "0" ] && [ ! -x "$ROOT/.venv/bin/python" ]; then
    step "Creating the Python environment (first run only, takes a minute)"
    python3 -m venv "$ROOT/.venv" || die "could not create .venv — is python3 installed?"
    "$ROOT/.venv/bin/pip" install --quiet --upgrade pip
    "$ROOT/.venv/bin/pip" install --quiet -e "$ROOT[dev]" || die "dependency install failed"
fi

if [ "$UI_WAS_UP" = "0" ] && [ ! -d "$ROOT/dashboard/node_modules" ]; then
    step "Installing dashboard dependencies (first run only)"
    command -v npm >/dev/null || die "npm not found — install Node.js first"
    (cd "$ROOT/dashboard" && npm install --silent) || die "npm install failed"
fi

# ------------------------------------------------------------------ backend

API_KEY=""

if [ "$BACKEND_WAS_UP" = "1" ]; then
    step "Backend already running"
    note "gateway :$GATEWAY_PORT, control plane :$CONTROL_PORT — left alone"
    API_KEY="$(cat "$RUN/api-key.txt" 2>/dev/null || true)"
else
    step "Starting the backend"
    note "gateway on :$GATEWAY_PORT, control plane on :$CONTROL_PORT"
    note "seeding the demo: registering a model, capturing a baseline, driving traffic"

    # run_demo --serve rather than bare uvicorn: it leaves behind a tenant, a
    # registered model, a baseline, a drift snapshot and an audit chain. A
    # dashboard pointed at an empty database looks identical to a broken one.
    #
    # -u matters more than it looks. Without it Python block-buffers stdout when
    # it is a file rather than a terminal, and --serve never exits — so the
    # buffer is never flushed, the log stays empty, and the API key we wait for
    # below never appears even though the servers came up fine.
    (
        cd "$ROOT"
        exec "$ROOT/.venv/bin/python" -u -m examples.fintech_demo.run_demo --serve \
            --gateway-port "$GATEWAY_PORT" --control-port "$CONTROL_PORT"
    ) > "$RUN/backend.log" 2>&1 &
    BACKEND_PID=$!
    echo "$BACKEND_PID" > "$RUN/backend.pid"
    disown %% 2>/dev/null || true

    # The full API key prints only once the five-act demo has finished, so
    # waiting for it is also how we know the data is seeded and the servers are
    # up. An earlier log line shows a truncated key; the length bound skips it.
    step "Waiting for the demo to finish seeding"
    for _ in $(seq 1 240); do
        if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
            say ""
            tail -n 25 "$RUN/backend.log" >&2
            die "backend exited early — full output in .run/backend.log"
        fi
        API_KEY="$(grep -ao 'custos_[A-Za-z0-9_-]\{20,\}' "$RUN/backend.log" 2>/dev/null | head -1 || true)"
        [ -n "$API_KEY" ] && break
        printf '.'
        sleep 1
    done
    say ""
    if [ -z "$API_KEY" ]; then
        note "last lines of .run/backend.log:"
        tail -n 25 "$RUN/backend.log" >&2
        die "backend did not become ready in time — full output in .run/backend.log"
    fi
    printf '%s' "$API_KEY" > "$RUN/api-key.txt"
    note "backend ready"
fi

# ----------------------------------------------------------------- frontend

if [ "$UI_WAS_UP" = "1" ]; then
    step "Dashboard already running"
    note "http://localhost:$UI_PORT — left alone"
else
    step "Starting the dashboard"
    (
        cd "$ROOT/dashboard"
        exec npm run dev -- --port "$UI_PORT" --strictPort
    ) > "$RUN/dashboard.log" 2>&1 &
    UI_PID=$!
    echo "$UI_PID" > "$RUN/dashboard.pid"
    disown %% 2>/dev/null || true

    for _ in $(seq 1 60); do
        if ! kill -0 "$UI_PID" 2>/dev/null; then
            say ""
            tail -n 25 "$RUN/dashboard.log" >&2
            die "dashboard exited early — full output in .run/dashboard.log"
        fi
        ui_up && break
        printf '.'
        sleep 1
    done
    say ""
fi

# -------------------------------------------------------------------- report

say ""
if [ "$BACKEND_WAS_UP" = "1" ] && [ "$UI_WAS_UP" = "1" ]; then
    say "${GREEN}${BOLD}Custos is already running.${RESET} ${DIM}Nothing to do.${RESET}"
else
    say "${GREEN}${BOLD}Custos is running.${RESET}"
fi
say ""
say "  ${BOLD}Dashboard${RESET}      http://localhost:$UI_PORT"
say "  ${BOLD}Gateway docs${RESET}   http://localhost:$GATEWAY_PORT/docs"
say "  ${BOLD}Control docs${RESET}   http://localhost:$CONTROL_PORT/docs"
say ""
if [ -n "$API_KEY" ]; then
    say "  ${BOLD}API key${RESET}        $API_KEY"
    note "paste that into the dashboard once; it is saved in your browser"
else
    say "  ${BOLD}API key${RESET}        ${YELLOW}unknown${RESET}"
    note "this backend was not started by app.sh, so its key was never recorded"
    note "run ./app.sh --restart for a fresh one"
fi
say ""
say "  ${BOLD}Stop everything${RESET}   ./stop.sh"
say "  ${BOLD}Fresh demo data${RESET}   ./app.sh --restart"
note "logs: .run/backend.log  .run/dashboard.log"
say ""

if [ "$OPEN_BROWSER" = "1" ]; then
    command -v open >/dev/null && open "http://localhost:$UI_PORT"
fi
