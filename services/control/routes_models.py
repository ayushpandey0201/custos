"""POST /models, POST /models/{id}/baseline, GET /models."""

from fastapi import APIRouter

router = APIRouter(prefix="/models", tags=["models"])

