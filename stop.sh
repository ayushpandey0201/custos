#!/usr/bin/env bash
#
# Stop everything Custos is running — servers, dashboard, leftovers.
#
#     ./stop.sh           stop, and say what was stopped
#     ./stop.sh --quiet   stop silently (app.sh uses this)
#
# Note on browser tabs: a shell script cannot close them, and should not try.
# What this does instead is kill every server behind them, so every open tab
# and every browser stops working the moment this finishes. Refreshing any of
# them will show a connection error rather than stale data, which is the
# property you actually want.
#
# Three passes, in order of precision. Any one of them would usually be enough;
# together they mean it does not matter how the processes were started — by
# app.sh, by hand, by the benchmark harness, or by a run that crashed and left
# something holding a port.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN="$ROOT/.run"
PORTS=(8000 8001 5173)

BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'; GREEN=$'\033[32m'

QUIET=0
[ "${1:-}" = "--quiet" ] && QUIET=1

say() { [ "$QUIET" = "1" ] || printf '%s\n' "$*"; }

TARGETS=()

add() {
    # Collect a pid unless it is this script, our parent, or already listed.
    local pid="$1"
    [ -z "$pid" ] && return 0
    [ "$pid" = "$$" ] && return 0
    [ "$pid" = "${PPID:-0}" ] && return 0
    local existing
    for existing in ${TARGETS[@]+"${TARGETS[@]}"}; do
        [ "$existing" = "$pid" ] && return 0
    done
    kill -0 "$pid" 2>/dev/null && TARGETS+=("$pid")
    return 0
}

# --- pass 1: pids app.sh recorded ------------------------------------------

for pidfile in "$RUN"/*.pid; do
    [ -e "$pidfile" ] || continue
    add "$(cat "$pidfile" 2>/dev/null || true)"
    # Children too: `npm run dev` forks vite, and killing only npm orphans it,
    # which leaves the port held by a process no pid file knows about.
    for child in $(pgrep -P "$(cat "$pidfile" 2>/dev/null || echo 0)" 2>/dev/null || true); do
        add "$child"
    done
    rm -f "$pidfile"
done

# --- pass 2: anything matching this project's command lines -----------------

for pattern in \
    "examples.fintech_demo.run_demo" \
    "uvicorn services.gateway.main" \
    "uvicorn services.control.main" \
    "benchmarks.load_test" \
    "$ROOT/dashboard"
do
    for pid in $(pgrep -f "$pattern" 2>/dev/null || true); do
        add "$pid"
    done
done

# --- pass 3: whoever is holding our ports -----------------------------------
#
# The backstop. If a previous run died badly and left something listening,
# neither of the passes above will find it but this will.

for port in "${PORTS[@]}"; do
    for pid in $(lsof -ti "tcp:$port" 2>/dev/null || true); do
        add "$pid"
    done
done

# --- stop them --------------------------------------------------------------

if [ "${#TARGETS[@]}" -eq 0 ]; then
    say "${DIM}Nothing was running.${RESET}"
    exit 0
fi

say "${BOLD}Stopping ${#TARGETS[@]} process(es)…${RESET}"

# Ask politely first so uvicorn closes its sockets and SQLite commits cleanly.
kill -TERM "${TARGETS[@]}" 2>/dev/null || true

for _ in $(seq 1 10); do
    alive=0
    for pid in "${TARGETS[@]}"; do
        kill -0 "$pid" 2>/dev/null && alive=1
    done
    [ "$alive" = "0" ] && break
    sleep 0.3
done

# Anything still up after three seconds is not going to exit on its own.
for pid in "${TARGETS[@]}"; do
    kill -0 "$pid" 2>/dev/null && kill -KILL "$pid" 2>/dev/null
done
sleep 0.2

# --- verify -----------------------------------------------------------------

STILL_HELD=()
for port in "${PORTS[@]}"; do
    lsof -ti "tcp:$port" >/dev/null 2>&1 && STILL_HELD+=("$port")
done

if [ "${#STILL_HELD[@]}" -gt 0 ]; then
    printf '%s\n' "Ports still in use after stopping: ${STILL_HELD[*]}" >&2
    printf '%s\n' "Something outside this project is holding them." >&2
    exit 1
fi

say "${GREEN}${BOLD}Stopped.${RESET} ${DIM}Ports ${PORTS[*]} are free.${RESET}"
exit 0
