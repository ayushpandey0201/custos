"""Maps verdict -> execute / raise Blocked / route review.

Enforcement is separated from transport so that a caller who wants the verdict
without the consequence (shadow mode, canary rollout) can have exactly that:
call ``client.evaluate`` and never call ``enforce``.
"""

from __future__ import annotations

from collections.abc import Callable

from custos.client import Verdict


class CustosError(Exception):
    """Base for every exception the SDK raises."""


class Blocked(CustosError):
    """Raised when Custos returns BLOCK and the caller has no block handler."""

    def __init__(self, verdict: Verdict) -> None:
        reason = "; ".join(verdict.reasons) or "blocked by Custos"
        super().__init__(f"{reason} (trace_id={verdict.trace_id})")
        self.verdict = verdict


class ReviewRequired(CustosError):
    """Raised when Custos returns REVIEW and the caller has no review handler."""

    def __init__(self, verdict: Verdict) -> None:
        reason = "; ".join(verdict.reasons) or "review required by Custos"
        super().__init__(f"{reason} (trace_id={verdict.trace_id})")
        self.verdict = verdict


def enforce(
    verdict: Verdict,
    on_review: Callable[[Verdict], None] | None = None,
    on_block: Callable[[Verdict], None] | None = None,
) -> Verdict:
    """Turn a verdict into control flow.

    ALLOW returns. BLOCK and REVIEW call their handler if one was supplied,
    otherwise raise.

    REVIEW deliberately raises by default rather than falling through to ALLOW.
    A REVIEW that silently proceeds is indistinguishable from an ALLOW, which
    would make the whole middle verdict decorative — the caller must make an
    explicit choice about what "send this to a human" means in their system.
    """
    if verdict.decision == "BLOCK":
        if on_block is not None:
            on_block(verdict)
            return verdict
        raise Blocked(verdict)

    if verdict.decision == "REVIEW":
        if on_review is not None:
            on_review(verdict)
            return verdict
        raise ReviewRequired(verdict)

    return verdict
