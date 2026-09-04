"""PolicyEngine(SignalEngine): "Is this action ALLOWED?" [MVP-lite]

Deterministic rules over request facts. Unlike drift, policy answers a question
with a definite yes or no, which is why it is the engine allowed to issue a
veto: "this action is forbidden" is a statement of fact, not of degree.
"""

from __future__ import annotations

import asyncio

from engines.base.engine import SignalEngine
from engines.policy.rules import Rule, evaluate_condition
from shared.cache import get_cache
from shared.schemas.evaluation import EvaluationContext
from shared.schemas.signals import SignalResult, VetoInfo

_CACHE_TTL_S = 30


def _cache_key(tenant_id: str) -> str:
    return f"custos:policy_rules:{tenant_id}"


def load_rules(tenant_id: str) -> list[Rule]:
    """Enabled rules for a tenant, cached.

    A rule that no longer parses is dropped rather than raising. Rules are
    validated when written through the control plane, so this only triggers if
    a row was edited out of band — and one bad row must not disable the whole
    policy engine.
    """
    cache = get_cache()
    cached = cache.get(_cache_key(tenant_id))
    if cached is not None:
        return [Rule(**item) for item in cached]

    from sqlalchemy import select

    from shared.db.models import PolicyRule
    from shared.db.session import session_scope

    rules: list[Rule] = []
    with session_scope() as db:
        rows = db.execute(
            select(PolicyRule).where(
                PolicyRule.tenant_id == tenant_id,
                PolicyRule.enabled.is_(True),
            )
        ).scalars()
        for row in rows:
            try:
                rules.append(
                    Rule(
                        rule_id=row.rule_id,
                        condition=row.condition,
                        action=row.action,
                        description=row.description or "",
                    )
                )
            except ValueError:
                continue

    cache.set(_cache_key(tenant_id), [r.model_dump() for r in rules], _CACHE_TTL_S)
    return rules


def invalidate(tenant_id: str) -> None:
    get_cache().delete(_cache_key(tenant_id))


def build_facts(ctx: EvaluationContext) -> dict:
    """Flatten the request into the namespace rules are written against.

    Business context is spread at the top level so tenants write ``amount >
    50000`` rather than ``context.amount > 50000``, and is *also* available
    under ``context.*``. Features live only under ``features.*`` — they are
    model inputs, not business facts, and letting a feature named ``action``
    shadow the real action would be a policy bypass.
    """
    return {
        **ctx.context,
        "action": ctx.action,
        "model_id": ctx.model_id,
        "tenant_id": ctx.tenant_id,
        "context": ctx.context,
        "features": ctx.features,
    }


class PolicyEngine(SignalEngine):
    name = "policy"

    async def evaluate(self, ctx: EvaluationContext) -> SignalResult:
        # Off-thread for the same reason as DriftEngine: a cache miss hits the
        # database, and a blocked event loop cannot honour the fan-out timeout.
        rules = await asyncio.to_thread(load_rules, ctx.tenant_id)
        if not rules:
            # No rules configured is not "everything is fine" — it is an
            # absent signal. Reporting it as degraded keeps it out of the
            # weighted mean instead of inflating trust with a free 1.0.
            return SignalResult.degraded_result(self.name, reason="no_rules_configured")

        facts = build_facts(ctx)
        matched: list[dict] = []
        veto: VetoInfo | None = None
        score = 1.0

        for rule in rules:
            try:
                if not evaluate_condition(rule, facts):
                    continue
            except ValueError:
                continue

            matched.append(
                {"rule_id": rule.rule_id, "action": rule.action, "description": rule.description}
            )

            if rule.action == "veto":
                # First veto wins and short-circuits: nothing below can raise
                # the verdict, so continuing only adds latency to the hot path.
                veto = VetoInfo(
                    engine=self.name,
                    reason=rule.description or f"blocked by rule {rule.rule_id}",
                    rule_id=rule.rule_id,
                )
                score = 0.0
                break
            if rule.action == "deny":
                score = 0.0
            elif rule.action == "warn":
                # Penalties compound: three warnings are worse than one.
                score = min(score, score * rule.penalty)

        return SignalResult(
            engine=self.name,
            score=score,
            veto=veto,
            detail={"matched_rules": matched, "rules_evaluated": len(rules)},
        )
