from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_session

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness probe — the process is up."""
    return {"status": "ok"}


@router.get("/health/db")
def health_db(session: Session = Depends(get_session)) -> dict[str, str]:
    """Readiness probe — the database answers."""
    session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}
