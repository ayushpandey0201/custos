"""System-wide defaults: thresholds, timeouts, weights."""

DEFAULT_TIMEOUT_MS = 50
DEFAULT_WEIGHTS = {
    "policy": 0.3,
    "drift": 0.5,
    "risk": 0.2,
}
DEFAULT_THRESHOLDS = {
    "block": 0.3,
    "review": 0.6,
}

