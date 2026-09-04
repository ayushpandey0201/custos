"""@guard decorator and `with custos.gate(...)` context manager.

The adoption surface. Integration must stay at five lines or fewer, because a
trust layer that is hard to adopt does not get adopted, and one that is not
adopted protects nothing.

    import custos
    custos.configure(base_url="http://localhost:8000", api_key=KEY)

    @custos.guard(model_id="credit-risk-v3", action="approve_loan")
    def approve(application):
        ...

The decorator extracts features and business context from the call, asks the
gateway, and either lets the function run or raises.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from custos.client import CustosClient, Verdict
from custos.enforce import enforce

_client: CustosClient | None = None


def configure(
    base_url: str = "http://localhost:8000",
    api_key: str = "",
    timeout_ms: int = 50,
    fail_open: bool = True,
) -> CustosClient:
    """Set up the process-wide client. Call once at startup."""
    global _client
    _client = CustosClient(
        base_url=base_url, api_key=api_key, timeout_ms=timeout_ms, fail_open=fail_open
    )
    return _client


def get_client() -> CustosClient:
    if _client is None:
        raise RuntimeError("custos.configure(...) must be called before guard/gate is used")
    return _client


def _extract(
    source: Any, extractor: Callable[..., dict] | str | None, args: tuple, kwargs: dict
) -> dict:
    """Resolve a features/context spec into a dict.

    Accepts a callable (given the original call's args), a keyword argument
    name, or nothing. Three ways rather than one because the shape of a
    guarded function is the caller's business, not ours — forcing a single
    convention is what pushes people into wrapping their own wrapper.
    """
    if extractor is None:
        return {}
    if callable(extractor):
        return dict(extractor(*args, **kwargs) or {})
    value = kwargs.get(extractor)
    if isinstance(value, dict):
        return dict(value)
    return {}


def guard(
    model_id: str,
    action: str = "predict",
    features: Callable[..., dict] | str | None = None,
    context: Callable[..., dict] | str | None = None,
    on_review: Callable[[Verdict], None] | None = None,
    on_block: Callable[[Verdict], None] | None = None,
) -> Callable:
    """Gate a function behind a Custos verdict.

    Args:
        features: callable receiving the wrapped call's arguments and returning
            the feature vector, or the name of a keyword argument holding it.
        context: same, for the business facts policy rules match against.
        on_review / on_block: handlers. Without them, REVIEW and BLOCK raise.
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            verdict = get_client().evaluate(
                model_id=model_id,
                action=action,
                features=_extract(fn, features, args, kwargs),
                context=_extract(fn, context, args, kwargs),
            )
            enforce(verdict, on_review=on_review, on_block=on_block)
            return fn(*args, **kwargs)

        # Exposed so callers can reach the guard's configuration for testing
        # or introspection without unwrapping the decorator.
        wrapper.custos_model_id = model_id  # type: ignore[attr-defined]
        wrapper.custos_action = action  # type: ignore[attr-defined]
        return wrapper

    return decorator


@contextmanager
def gate(
    model_id: str,
    action: str = "predict",
    features: dict[str, float] | None = None,
    context: dict[str, Any] | None = None,
    on_review: Callable[[Verdict], None] | None = None,
    on_block: Callable[[Verdict], None] | None = None,
) -> Iterator[Verdict]:
    """Block-scoped equivalent of :func:`guard`.

    For the common case where the features are only known partway through a
    function, so there is nothing to decorate:

        with custos.gate("credit-risk-v3", "approve", features=f) as verdict:
            disburse(...)
    """
    verdict = get_client().evaluate(
        model_id=model_id, action=action, features=features, context=context
    )
    enforce(verdict, on_review=on_review, on_block=on_block)
    yield verdict
