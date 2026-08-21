from datetime import datetime

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: int
    username: str | None
    role: str | None
    action: str
    entity_type: str | None
    entity_id: int | None
    description: str | None
    created_at: datetime
