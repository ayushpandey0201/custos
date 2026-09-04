"""End-to-end demo: run the whole story in one command.

    python -m examples.fintech_demo.run_demo

Starts the real gateway and control plane on localhost, drives them with the
real Python SDK over real HTTP, and narrates what happens. No Docker, no
Postgres, no Redis — SQLite and an in-process cache are enough for one node,
which is the point of the fallbacks in shared/db and shared/cache.

The story, in five acts:

    1  a model nobody registered           -> REVIEW, not a silent allow
    2  registered and baselined, healthy   -> ALLOW, and loans get written
    3  the population shifts               -> drift severity climbs
    4  same code, no config change         -> REVIEW; the bot stops auto-approving
    5  a policy veto                       -> BLOCK, and the audit chain verifies
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "sdk" / "python"))

import urllib.error  # noqa: E402
import urllib.request  # noqa: E402

BOLD, DIM, RESET = "\033[1m", "\033[2m", "\033[0m"
GREEN, YELLOW, RED, CYAN = "\033[32m", "\033[33m", "\033[31m", "\033[36m"

COLOURS = {
    "ALLOW": GREEN,
    "APPROVED": GREEN,
    "REVIEW": YELLOW,
    "HELD_FOR_REVIEW": YELLOW,
    "DENIED": YELLOW,
    "BLOCK": RED,
    "BLOCKED": RED,
}


def act(number: int, title: str) -> None:
    print(f"\n{BOLD}{CYAN}── Act {number} ─ {title}{RESET}")


def note(text: str) -> None:
    print(f"   {DIM}{text}{RESET}")


def verdict_line(label: str, value: str, extra: str = "") -> None:
    colour = COLOURS.get(value, "")
    print(f"   {label:<28} {colour}{BOLD}{value}{RESET} {DIM}{extra}{RESET}")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def serve(app, port: int) -> threading.Thread:
    import uvicorn

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return thread


def wait_for(url: str, timeout_s: float = 20.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0):
                return
        except Exception:
            time.sleep(0.15)
    raise RuntimeError(f"{url} did not come up within {timeout_s:.0f}s")


def send(method: str, url: str, payload: dict, api_key: str | None = None) -> dict:
    import json

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method=method
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def post(url: str, payload: dict, api_key: str | None = None) -> dict:
    return send("POST", url, payload, api_key)


def put(url: str, payload: dict, api_key: str | None = None) -> dict:
    return send("PUT", url, payload, api_key)


def get(url: str, api_key: str) -> dict:
    import json

    request = urllib.request.Request(url, headers={"X-API-Key": api_key})
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read())


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(description="Run the Custos fintech demo end to end.")
    parser.add_argument(
        "--serve",
        action="store_true",
        help="keep the gateway and control plane running afterwards, on the default "
        "ports (8000/8001), so the dashboard can connect to them",
    )
    parser.add_argument("--gateway-port", type=int, default=None)
    parser.add_argument("--control-port", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # A fresh database each run, so the demo always tells the same story.
    db_path = ROOT / "custos-demo.db"
    db_path.unlink(missing_ok=True)

    import logging
    import os

    os.environ["CUSTOS_DATABASE_URL"] = f"sqlite:///{db_path}"

    # Quiet the per-decision JSON logs. They are the right default for a
    # service and the wrong one for a narrated walkthrough — the structured
    # logs are still there under `uvicorn ... --log-level info`.
    from shared.telemetry.logging import configure

    configure(level=logging.WARNING)

    from shared.db.session import create_all

    create_all(f"sqlite:///{db_path}")

    from services.control.main import create_app as control_app
    from services.gateway.main import create_app as gateway_app

    # With --serve, default to the ports the dashboard and docker-compose
    # already expect, so the UI connects without configuration.
    gateway_port = args.gateway_port or (8000 if args.serve else free_port())
    control_port = args.control_port or (8001 if args.serve else free_port())
    serve(gateway_app(), gateway_port)
    serve(control_app(), control_port)

    gateway_url = f"http://127.0.0.1:{gateway_port}"
    control_url = f"http://127.0.0.1:{control_port}"
    wait_for(f"{gateway_url}/health")
    wait_for(f"{control_url}/health")

    print(f"{BOLD}Custos — fintech demo{RESET}")
    note(f"gateway  {gateway_url}")
    note(f"control  {control_url}")

    from examples.fintech_demo import inject_drift
    from examples.fintech_demo.agent.loan_bot import MODEL_ID, LoanBot

    tenant = post(f"{control_url}/tenants", {"tenant_id": "lender", "name": "Lender Co"})
    api_key = tenant["api_key"]
    note(f"tenant 'lender' created, api key {api_key[:18]}…")

    bot = LoanBot(gateway_url=gateway_url, api_key=api_key)
    application = inject_drift.clean_batch(n=1, seed=7)[0]

    # ---------------------------------------------------------------- Act 1
    act(1, "An unregistered model asks to disburse money")
    outcome = bot.decide(application, amount=250_000)
    verdict_line("bot outcome", outcome.verdict, f"trust {outcome.trust_score}")
    note(outcome.reason)
    note("Custos has never seen this model. It does not guess — it escalates (ADR 0005).")

    # ---------------------------------------------------------------- Act 2
    act(2, "Register the model and capture its baseline")
    post(f"{control_url}/models", {"model_id": MODEL_ID, "name": "Credit Risk v3"}, api_key)
    baseline = inject_drift.clean_batch(n=600, seed=1)
    post(f"{control_url}/models/{MODEL_ID}/baseline", {"samples": baseline}, api_key)
    note(f"baseline captured from {len(baseline)} applications across 4 features")

    # A standing policy rule, so the policy engine is a live signal rather than
    # a degraded one. It does not match this demo's traffic — the point is that
    # the verdict below is a *fusion* of policy and drift, not drift alone.
    put(
        f"{control_url}/config/rules",
        {
            "rule_id": "supported-regions",
            "condition": 'region not in ["IN", "SG"]',
            "action": "veto",
            "description": "lending is licensed only in IN and SG",
        },
        api_key,
    )
    note('policy rule added:  region not in ["IN", "SG"]  →  veto')

    for row in inject_drift.clean_batch(n=200, seed=2):
        bot.decide(row, amount=200_000)
    healthy = post(f"{control_url}/models/{MODEL_ID}/recompute", {}, api_key)
    note(f"drift severity on healthy traffic: {healthy['severity']:.3f}")

    outcome = bot.decide(application, amount=250_000)
    verdict_line("bot outcome", outcome.verdict, f"trust {outcome.trust_score:.2f}")
    note(outcome.reason)

    # ---------------------------------------------------------------- Act 3
    act(3, "The population shifts — incomes fall, utilisation spikes")
    note("Nothing about the model, the code or the config changes from here on.")
    for row in inject_drift.population_shift(n=400, seed=3):
        bot.decide(row, amount=200_000)

    drifted = post(f"{control_url}/models/{MODEL_ID}/recompute", {}, api_key)
    print(f"   drift severity {healthy['severity']:.3f} → {BOLD}{drifted['severity']:.3f}{RESET}")

    history = get(f"{control_url}/models/{MODEL_ID}/drift", api_key)
    print(f"\n   {BOLD}per-feature attribution{RESET}")
    for name, stats in sorted(
        history["current"]["per_feature"].items(), key=lambda kv: -kv[1]["severity"]
    ):
        bar = "█" * int(stats["severity"] * 28)
        print(f"     {name:<17} PSI {stats['psi']:>7.3f}  {stats['band']:<12} {bar}")
    note("bureau_score did not move, and is not blamed. That is what makes this actionable.")

    # ---------------------------------------------------------------- Act 4
    act(4, "The same application, the same code — a different answer")
    outcome = bot.decide(application, amount=250_000)
    verdict_line("bot outcome", outcome.verdict, f"trust {outcome.trust_score:.2f}")
    note(outcome.reason)
    note(f"{len(bot.held)} application(s) routed to a human instead of being auto-decided.")

    # ---------------------------------------------------------------- Act 5
    act(5, "A policy veto, and the evidence trail")
    put(
        f"{control_url}/config/rules",
        {
            "rule_id": "max-disbursement",
            "condition": 'action == "disburse" and amount > 500000',
            "action": "veto",
            "description": "disbursements above 500000 require manual authorisation",
        },
        api_key,
    )
    note('rule added:  action == "disburse" and amount > 500000  →  veto')

    outcome = bot.decide(application, amount=900_000)
    verdict_line("bot outcome", outcome.verdict, f"trust {outcome.trust_score:.2f}")
    note(outcome.reason)

    verified = get(f"{control_url}/audit/verify", api_key)
    status = "VERIFIED" if verified["valid"] else "BROKEN"
    colour = GREEN if verified["valid"] else RED
    count = f"{DIM}({verified['entries']} entries){RESET}"
    print(f"\n   audit chain: {colour}{BOLD}{status}{RESET} {count}")

    # Now rewrite history: turn the BLOCK we just recorded into an ALLOW,
    # directly in the database, the way someone covering their tracks would.
    from sqlalchemy import select

    from shared.db.models import AuditEntry
    from shared.db.session import session_scope

    target_seq = get(f"{control_url}/audit?limit=1", api_key)["entries"][0]["seq"]
    with session_scope() as db:
        entry = db.execute(
            select(AuditEntry).where(AuditEntry.tenant_id == "lender", AuditEntry.seq == target_seq)
        ).scalar_one()
        entry.payload = {
            **entry.payload,
            "decision": "ALLOW",
            "trust_score": 1.0,
            "reasons": ["approved"],
        }
    note(f"someone edits entry #{target_seq} in the database: BLOCK → ALLOW…")

    verified = get(f"{control_url}/audit/verify", api_key)
    status = "VERIFIED" if verified["valid"] else f"BROKEN at entry {verified['broken_at']}"
    colour = GREEN if verified["valid"] else RED
    print(f"   audit chain: {colour}{BOLD}{status}{RESET}")
    note(verified["detail"])

    print(f"\n{BOLD}Done.{RESET} Explore the running system:")
    note(f"gateway docs   {gateway_url}/docs")
    note(f"control docs   {control_url}/docs")
    note(f"drift history  {control_url}/models/{MODEL_ID}/drift")
    note(f"metrics        {gateway_url}/metrics")

    if args.serve:
        print(f"\n{BOLD}Servers are still running.{RESET}")
        note("dashboard:  cd dashboard && npm run dev   (connect with the key below)")
        print(f"\n   {BOLD}API key{RESET}  {api_key}\n")
        note("Ctrl-C to stop.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("\nstopped.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
