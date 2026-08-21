from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.schemas.audit_log import AuditLogOut
from app.services import audit_log_service

router = APIRouter(prefix="/audit-logs", dependencies=[Depends(get_current_user)])


@router.get("", response_model=list[AuditLogOut])
def list_audit_logs(
    limit: int = 100,
    action: str | None = None,
    entity_type: str | None = None,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Most recent audit log entries first. Read-only — see who did what and when."""
    return audit_log_service.list_audit_logs(db, limit, action, entity_type)


@router.get("/actions", response_model=list[str])
def list_audit_log_actions(
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Every distinct action type ever logged — powers the filter dropdown."""
    return audit_log_service.list_distinct_actions(db)
