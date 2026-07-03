"""GET /audit, GET /audit/export, GET /audit/verify."""

from fastapi import APIRouter

router = APIRouter(prefix="/audit", tags=["audit"])

