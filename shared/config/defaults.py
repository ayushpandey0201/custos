"""System-wide defaults: thresholds, timeouts, weights.

Every value here is overridable per tenant via ``PUT /config`` on the control
plane. These are the numbers a tenant gets before they have ever configured
anything, so they are chosen to be safe-but-not-annoying rather than optimal.
"""

from __future__ import annotations

import os

# --- Hot path budget -------------------------------------------------------
# Gateway p99 target is 50 ms end to end. Each engine gets a slice of that; an
# engine that overruns is cancelled and reported as degraded rather than
# allowed to blow the whole request's budget (ADR 0001, ADR 0004).
DEFAULT_TIMEOUT_MS = 50
ENGINE_TIMEOUT_MS = 20

# --- Fusion ----------------------------------------------------------------
# Drift carries the most weight: it is the signal nothing else in the stack
# provides, and the one this system exists to surface.
DEFAULT_WEIGHTS: dict[str, float] = {
    "policy": 0.3,
    "drift": 0.5,
    "risk": 0.2,
}

# --- Decision thresholds ---------------------------------------------------
# trust < 0.30            -> BLOCK
# 0.30 <= trust < 0.60    -> REVIEW
# trust >= 0.60           -> ALLOW
DEFAULT_THRESHOLDS: dict[str, float] = {
    "block": 0.3,
    "review": 0.6,
}

DEFAULT_ENGINES: list[str] = ["policy", "drift", "risk"]

# --- Drift -----------------------------------------------------------------
# PSI bands are the fintech industry convention (Pradeep Jinka interview,
# docs/conversations/01): < 0.10 stable, 0.10-0.25 moderate shift worth
# watching, > 0.25 significant shift that warrants investigation.
PSI_STABLE = 0.10
PSI_MODERATE = 0.25
# PSI at or above this is treated as maximum severity; beyond it the number
# stops carrying useful gradient.
PSI_SATURATION = 0.50
DRIFT_BUCKETS = 10

# --- Fail-open -------------------------------------------------------------
# When Custos cannot reach a verdict, callers proceed (ADR 0001). Tenants with
# a compliance requirement flip this per tenant.
FAIL_OPEN = True

# --- Infrastructure --------------------------------------------------------
# SQLite by default so the whole system runs on a laptop with no services;
# docker-compose overrides this with Postgres.
DATABASE_URL = os.getenv("CUSTOS_DATABASE_URL", "sqlite:///./custos.db")
REDIS_URL = os.getenv("CUSTOS_REDIS_URL", "")
TENANT_CONFIG_TTL_S = 30
