"""Name -> class map; tenants enable engines by name in config."""

from engines.base.engine import SignalEngine

REGISTRY: dict[str, type[SignalEngine]] = {}


def register(name: str, cls: type[SignalEngine]) -> None:
    REGISTRY[name] = cls


def get_engine(name: str) -> type[SignalEngine]:
    return REGISTRY[name]

