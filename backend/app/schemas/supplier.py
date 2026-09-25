import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[0-9][0-9 \-]{6,19}$")


class SupplierOut(BaseModel):
    id: int
    supplier_code: str
    supplier_name: str
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    company_number: str | None = None
    whatsapp_number: str | None = None
    account_updated_at: datetime | None = None
    status: str

    class Config:
        from_attributes = True


class SupplierCreate(BaseModel):
    # If omitted, the next sequential code (SUP17, SUP18, ...) is
    # generated to match the existing SUP01..SUP16 convention from
    # seed_master_data.py — Admin can still override it if they want a
    # specific code.
    supplier_code: str | None = Field(default=None, max_length=20)
    supplier_name: str = Field(min_length=1, max_length=150)
    contact_person: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=120)
    address: str | None = None


class SupplierAccountUpdate(BaseModel):
    """What a supplier fills in on their own Account page — every field is required."""

    supplier_name: str = Field(min_length=1, max_length=150)
    company_number: str = Field(min_length=1, max_length=50)
    whatsapp_number: str = Field(min_length=1, max_length=30)
    email: str = Field(min_length=1, max_length=120)

    @field_validator("supplier_name", "company_number", "whatsapp_number", "email")
    @classmethod
    def _strip_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("This field is required.")
        return v

    @field_validator("whatsapp_number")
    @classmethod
    def _valid_phone(cls, v: str) -> str:
        if not _PHONE_RE.match(v):
            raise ValueError("Enter a valid WhatsApp number, e.g. 0771234567 or +94771234567.")
        return v

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        if not _EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address.")
        return v.lower()
