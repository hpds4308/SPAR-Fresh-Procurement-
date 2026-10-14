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


class ContactThreadOut(BaseModel):
    """A supplier's chat with one branch, or a branch's chat with one supplier."""

    id: int  # branch_id for a supplier, supplier_id for a branch
    code: str
    name: str
    last_message_body: str | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0


class PairConversationOut(BaseModel):
    """One supplier<->branch chat, for Admin's read-only view."""

    supplier_id: int
    supplier_name: str
    branch_id: int
    branch_name: str
    message_count: int
    unread_count: int = 0  # not yet seen by Admin
    last_message_body: str
    last_message_at: datetime
    last_sender_role: str


class UnreadCountOut(BaseModel):
    count: int
    # Admin only — `count` split per Messages tab, and who wrote the newest
    # unread supplier<->branch message (e.g. "Bloomax → Kandy") with its id,
    # so the dashboard can pop up a notice once per new message.
    suppliers: int | None = None
    branches: int | None = None
    supplier_branch: int | None = None
    latest_supplier_branch: str | None = None
    latest_supplier_branch_id: int | None = None
