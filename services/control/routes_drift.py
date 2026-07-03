"""GET /models/{id}/drift — history for dashboard."""

from fastapi import APIRouter

router = APIRouter(prefix="/models", tags=["drift"])

