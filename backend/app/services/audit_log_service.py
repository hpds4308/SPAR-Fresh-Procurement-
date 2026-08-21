"""
Read-only access to the audit log. Every write to this table already
happens via app.core.audit.write_audit_log across the order, pricing,
assignment, and auth services — this module never writes, only reads,
so there's exactly one place a log entry gets created.
"""
from sqlalchemy.orm import Session

from app.models.system import AuditLog
from app.models.user import User
from app.schemas.audit_log import AuditLogOut

MAX_LIMIT = 500


def list_audit_logs(
    db: Session,
    limit: int = 100,
    action: str | None = None,
    entity_type: str | None = None,
) -> list[AuditLogOut]:
    limit = min(limit, MAX_LIMIT)
    query = db.query(AuditLog).order_by(AuditLog.created_at.desc())
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    rows = query.limit(limit).all()

    user_ids = {r.user_id for r in rows if r.user_id is not None}
    usernames = {u.id: u.username for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}

    return [
        AuditLogOut(
            id=r.id,
            username=usernames.get(r.user_id),
            role=r.role,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            description=r.description,
            created_at=r.created_at,
        )
        for r in rows
    ]


def list_distinct_actions(db: Session) -> list[str]:
    rows = db.query(AuditLog.action).distinct().order_by(AuditLog.action).all()
    return [r[0] for r in rows]
