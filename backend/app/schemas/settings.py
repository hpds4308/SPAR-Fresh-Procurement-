from datetime import datetime

from pydantic import BaseModel, Field


class SettingsOut(BaseModel):
    branch_order_deadline: str
    supplier_price_deadline: str
    # Suppliers approve/reject SPAR's adjusted prices by this time on the submission day.
    supplier_approval_deadline: str
    # Comma-separated weekday numbers (Monday=0 .. Sunday=6), e.g. "0,2,4".
    supplier_price_days: str
    support_phone: str


class SettingUpdateRequest(BaseModel):
    value: str = Field(min_length=1, max_length=200)


class EmailLogOut(BaseModel):
    id: int
    kind: str
    recipient: str
    subject: str
    status: str
    error: str | None = None
    created_at: datetime


class EmailStatusOut(BaseModel):
    configured: bool
    provider: str | None = None  # "Brevo" / "SMTP"
    from_address: str | None = None
    # Admin accounts with an email — who admin notifications go to.
    admin_recipients: list[str]
    # Active suppliers without an email on their Account page get no emails.
    suppliers_without_email: list[str]
    recent: list[EmailLogOut]


class TestEmailOut(BaseModel):
    status: str  # SENT / FAILED / SKIPPED


class MasterDataEmailOut(BaseModel):
    # Kept off the public SettingsOut on purpose — an internal distribution
    # address, only ever read/written by Admin.
    master_data_email: str
