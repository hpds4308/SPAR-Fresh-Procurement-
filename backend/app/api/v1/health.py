from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """
    Basic liveness + database connectivity check.
    Used by Docker/monitoring to confirm the API and DB are both up.
    """
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
