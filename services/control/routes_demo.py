"""Guided-demo endpoints: the five-act story, one step at a time, for the dashboard.

Mounted only in demo mode — `run_demo --serve`, which `app.sh` uses, or
CUSTOS_DEMO_MODE=1. Never in a real deployment: one step here deliberately
edits the audit log behind Custos's back, to prove the hash chain catches it.

Each act drives the real system exactly as `run_demo` does — real HTTP to the
control plane, the real SDK through the real gateway, the real database — so
the dashboard shows what the system does, not a re-enactment of it.

One demo run is held in memory at a time: this is a presenter's tool, not a
multi-user service. Starting again creates a fresh tenant, so every run begins
from a clean slate without touching anyone else's data.
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field

from fastapi import APIRouter, HTTPException, Request

from shared.telemetry.logging import get_logger

log = get_logger(__name__)

# What the bot did, mapped to what Custos said. APPROVED and DENIED are both
# Custos ALLOWs — the model then decided — so the badge shows Custos's verdict.
CUSTOS_VERDICT = {
    "APPROVED": "ALLOW",
    "DENIED": "ALLOW",
    "HELD_FOR_REVIEW": "REVIEW",
    "BLOCKED": "BLOCK",
}


@dataclass(frozen=True)
class Sizes:
    baseline: int = 600
    healthy: int = 200
    shifted: int = 400


@dataclass
class _Run:
    tenant_id: str
    api_key: str
    bot: object
    application: dict[str, float]
    done: set[int] = field(default_factory=set)
    healthy_severity: float | None = None


def _outcome(o) -> dict:
    return {
        "bot": o.verdict,
        "custos": CUSTOS_VERDICT.get(o.verdict, o.verdict),
        "trust_score": None if o.trust_score is None else round(o.trust_score, 2),
        "reason": o.reason,
        "default_probability": round(o.default_probability, 3),
        "trace_id": o.trace_id,
    }


def _alive(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.5):
            return True
    except Exception:
        return False


def build_router(gateway_url: str, sizes: Sizes = Sizes()) -> APIRouter:
    from examples.fintech_demo import inject_drift
    from examples.fintech_demo.agent.loan_bot import MODEL_ID, LoanBot
    from examples.fintech_demo.run_demo import get, post, put

    router = APIRouter(prefix="/demo", tags=["demo"])
    lock = threading.Lock()
    state: dict[str, _Run | None] = {"run": None}

    def control(request: Request) -> str:
        return str(request.base_url).rstrip("/")

    def need_gateway() -> None:
        # Without this, a stopped gateway would make the SDK fail open and the
        # bot would report APPROVED — the demo would quietly lie on stage.
        if not _alive(f"{gateway_url}/health"):
            raise HTTPException(
                503, "The gateway is not running. In a terminal, run ./app.sh, then try again."
            )

    def current(step: int) -> _Run:
        run = state["run"]
        if run is None:
            raise HTTPException(409, "Start the demo first.")
        missing = [s for s in range(1, step) if s not in run.done]
        if missing:
            raise HTTPException(
                409, f"Run step {missing[0]} first — the steps build on each other."
            )
        return run

    def tally(outcomes) -> dict[str, int]:
        return dict(Counter(CUSTOS_VERDICT.get(o.verdict, o.verdict) for o in outcomes))

    @router.get("/status")
    def status() -> dict:
        run = state["run"]
        return {
            "gateway": _alive(f"{gateway_url}/health"),
            "control": True,
            "run": None if run is None else {"tenant_id": run.tenant_id, "done": sorted(run.done)},
        }

    @router.post("/start")
    def start(request: Request) -> dict:
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "A step is already running.")
        try:
            need_gateway()
            tenant_id = f"demo-{time.strftime('%H%M%S')}"
            created = post(
                f"{control(request)}/tenants", {"tenant_id": tenant_id, "name": "Demo Lender"}
            )
            application = inject_drift.clean_batch(n=1, seed=7)[0]
            state["run"] = _Run(
                tenant_id=tenant_id,
                api_key=created["api_key"],
                bot=LoanBot(gateway_url=gateway_url, api_key=created["api_key"]),
                application=application,
            )
            log.info("demo_started", extra={"tenant_id": tenant_id})
            return {
                "tenant_id": tenant_id,
                "api_key": created["api_key"],
                "application": {k: round(v, 3) for k, v in application.items()},
                "model_id": MODEL_ID,
            }
        finally:
            lock.release()

    @router.post("/act/{step}")
    def act(step: int, request: Request) -> dict:
        if step not in range(1, 6):
            raise HTTPException(404, "Steps are numbered 1 to 5.")
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "A step is already running.")
        try:
            run = current(step)
            need_gateway()
            url, key, bot = control(request), run.api_key, run.bot
            try:
                result = ACTS[step](url, key, bot, run)
            except urllib.error.URLError as exc:
                raise HTTPException(502, f"Custos call failed: {exc}") from exc
            run.done.add(step)
            return {"step": step, **result}
        finally:
            lock.release()

    def act1(url, key, bot, run):
        decision = _outcome(bot.decide(run.application, amount=250_000))
        return {"decision": decision, "amount": 250_000}

    def act2(url, key, bot, run):
        post(f"{url}/models", {"model_id": MODEL_ID, "name": "Credit Risk v3"}, key)
        baseline = inject_drift.clean_batch(n=sizes.baseline, seed=1)
        post(f"{url}/models/{MODEL_ID}/baseline", {"samples": baseline}, key)
        put(
            f"{url}/config/rules",
            {
                "rule_id": "supported-regions",
                "condition": 'region not in ["IN", "SG"]',
                "action": "veto",
                "description": "lending is licensed only in IN and SG",
            },
            key,
        )
        healthy_rows = inject_drift.clean_batch(n=sizes.healthy, seed=2)
        traffic = [bot.decide(r, amount=200_000) for r in healthy_rows]
        healthy = post(f"{url}/models/{MODEL_ID}/recompute", {}, key)
        run.healthy_severity = healthy.get("severity")
        return {
            "baseline_size": len(baseline),
            "traffic": {"sent": len(traffic), "verdicts": tally(traffic)},
            "severity": run.healthy_severity,
            "decision": _outcome(bot.decide(run.application, amount=250_000)),
            "amount": 250_000,
        }

    def act3(url, key, bot, run):
        shifted = inject_drift.population_shift(n=sizes.shifted, seed=3)
        traffic = [bot.decide(r, amount=200_000) for r in shifted]
        drifted = post(f"{url}/models/{MODEL_ID}/recompute", {}, key)
        history = get(f"{url}/models/{MODEL_ID}/drift", key)
        per_feature = (history.get("current") or {}).get("per_feature", {})
        return {
            "traffic": {"sent": len(traffic), "verdicts": tally(traffic)},
            "severity_before": run.healthy_severity,
            "severity_after": drifted.get("severity"),
            "band_after": (history.get("current") or {}).get("band"),
            "features": sorted(
                (
                    {
                        "feature": n,
                        "psi": round(s["psi"], 3),
                        "band": s["band"],
                        "severity": s["severity"],
                    }
                    for n, s in per_feature.items()
                ),
                key=lambda f: -f["psi"],
            ),
        }

    def act4(url, key, bot, run):
        return {
            "decision": _outcome(bot.decide(run.application, amount=250_000)),
            "amount": 250_000,
            "held_for_review": len(bot.held),
        }

    def act5(url, key, bot, run):
        put(
            f"{url}/config/rules",
            {
                "rule_id": "max-disbursement",
                "condition": 'action == "disburse" and amount > 500000',
                "action": "veto",
                "description": "disbursements above 500000 require manual authorisation",
            },
            key,
        )
        decision = _outcome(bot.decide(run.application, amount=900_000))
        return {"decision": decision, "amount": 900_000, "chain": get(f"{url}/audit/verify", key)}

    ACTS = {1: act1, 2: act2, 3: act3, 4: act4, 5: act5}

    @router.post("/tamper")
    def tamper(request: Request) -> dict:
        """Rewrite the newest audit record directly in the database, then verify."""
        if not lock.acquire(blocking=False):
            raise HTTPException(409, "A step is already running.")
        try:
            run = current(6)
            from sqlalchemy import select

            from shared.db.models import AuditEntry
            from shared.db.session import session_scope

            url, key = control(request), run.api_key
            newest = get(f"{url}/audit?limit=1", key)["entries"][0]
            with session_scope() as db:
                entry = db.execute(
                    select(AuditEntry).where(
                        AuditEntry.tenant_id == run.tenant_id, AuditEntry.seq == newest["seq"]
                    )
                ).scalar_one()
                before = entry.payload.get("decision")
                entry.payload = {
                    **entry.payload,
                    "decision": "ALLOW",
                    "trust_score": 1.0,
                    "reasons": ["approved"],
                }
            run.done.add(6)
            return {
                "step": 6,
                "edited_seq": newest["seq"],
                "changed": {"from": before, "to": "ALLOW"},
                "chain": get(f"{url}/audit/verify", key),
            }
        finally:
            lock.release()

    return router
