"""Custos Python SDK — the ≤5-line integration surface.

import custos
custos.configure(base_url="http://localhost:8000", api_key=KEY)

@custos.guard(model_id="credit-risk-v3", action="approve_loan", features="features")
def approve_loan(*, features): ...
"""

from custos.client import CustosClient, Verdict
from custos.enforce import Blocked, CustosError, ReviewRequired, enforce
from custos.guard import configure, gate, get_client, guard

__all__ = [
    "Blocked",
    "CustosClient",
    "CustosError",
    "ReviewRequired",
    "Verdict",
    "configure",
    "enforce",
    "gate",
    "get_client",
    "guard",
]
