"""PUT /config — tenant engines, weights, thresholds."""

from fastapi import APIRouter

router = APIRouter(prefix="/config", tags=["config"])

