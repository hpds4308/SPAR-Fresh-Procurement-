from sqlalchemy.orm import Session

from app.models.system import AuditLog


def write_audit_log(
    db: Session,
    *,
    user_id: int | None,
    role: str | None,
    action: str,
    entity_type: str | None = None,
    entity_id: int | None = None,
    description: str | None = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """
    Writes one audit log row. Never pass passwords, tokens, or other secrets
    in `description` or `metadata` — this table is readable by Admin users.
    """
    db.add(
        AuditLog(
            user_id=user_id,
            role=role,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            log_metadata=metadata,
            ip_address=ip_address,
        )
    )
    db.commit()
