from datetime import datetime

from pydantic import BaseModel, Field


class MessageOut(BaseModel):
    id: int
    supplier_id: int | None = None
    branch_id: int | None = None
    sender_role: str  # "ADMIN" | "SUPPLIER" | "BRANCH"
    sender_username: str
    body: str
    created_at: datetime


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class SupplierThreadOut(BaseModel):
    supplier_id: int
    supplier_code: str
    supplier_name: str
    last_message_body: str | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0


class BranchThreadOut(BaseModel):
    branch_id: int
    branch_code: str
    branch_name: str
    last_message_body: str | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0


class UnreadCountOut(BaseModel):
    count: int
