"""Name -> class map; tenants enable engines by name in config.

The extensibility seam. Adding a signal to Custos is: write a ``SignalEngine``
subclass, call ``register()``, add its name to a tenant's ``enabled_engines``.
No service code changes.
"""

from __future__ import annotations

from engines.base.engine import SignalEngine

REGISTRY: dict[str, type[SignalEngine]] = {}


def register(name: str, cls: type[SignalEngine]) -> None:
    """Register an engine class under ``name``.

    Re-registration is allowed and replaces the previous binding — module
    reimports during tests would otherwise fail on a duplicate name.
    """
    if not issubclass(cls, SignalEngine):
        raise TypeError(f"{cls!r} is not a SignalEngine")
    REGISTRY[name] = cls


def get_engine(name: str) -> type[SignalEngine]:
    if name not in REGISTRY:
        raise KeyError(f"unknown engine {name!r}; registered: {sorted(REGISTRY)}")
    return REGISTRY[name]


def build_engines(names: list[str]) -> list[SignalEngine]:
    """Instantiate the engines a tenant has enabled.

    Unknown names are skipped rather than raising: a tenant config referencing
    an engine that has been removed should lose that signal, not lose the
    ability to evaluate anything at all.
    """
    engines: list[SignalEngine] = []
    for name in names:
        cls = REGISTRY.get(name)
        if cls is not None:
            engines.append(cls())
    return engines


def load_builtin_engines() -> None:
    """Import and register the engines shipped with Custos. Idempotent."""
    from engines.drift.engine import DriftEngine
    from engines.policy.engine import PolicyEngine
    from engines.risk.engine import RiskEngine

    register("policy", PolicyEngine)
    register("drift", DriftEngine)
    register("risk", RiskEngine)
