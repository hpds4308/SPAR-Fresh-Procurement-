import re

from pydantic import BaseModel, Field, field_validator


class UserListItem(BaseModel):
    id: int
    username: str
    role: str
    branch_name: str | None = None
    supplier_name: str | None = None
    supplier_id: int | None = None
    is_active: bool
    last_login_at: str | None = None

    class Config:
        from_attributes = True


class AvailablePartyOut(BaseModel):
    """A branch or supplier that doesn't have a login account yet."""

    id: int
    code: str
    name: str


class UserCreateRequest(BaseModel):
    role: str  # "ADMIN" | "BRANCH" | "SUPPLIER"
    branch_id: int | None = None
    supplier_id: int | None = None
    # Only used for ADMIN accounts — BRANCH/SUPPLIER usernames are always
    # derived from the branch/supplier code, same convention seed_users.py
    # uses, so logins stay predictable instead of Admin inventing new ones.
    username: str | None = Field(default=None, min_length=3, max_length=50)


class UserCreatedOut(BaseModel):
    id: int
    username: str
    role: str
    temporary_password: str


class UserDetailOut(BaseModel):
    id: int
    username: str
    role: str
    branch_name: str | None = None
    supplier_name: str | None = None
    is_active: bool
    last_login_at: str | None = None


class UserUpdateRequest(BaseModel):
    # Both optional — send just the one(s) actually being changed. At
    # least one of the two must be present (enforced in the endpoint,
    # not here, so the error message can name which fields are missing).
    username: str | None = Field(default=None, min_length=3, max_length=50)
    password: str | None = Field(default=None, min_length=8, max_length=200)


_ACCOUNT_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_ACCOUNT_PHONE_RE = re.compile(r"^\+?[0-9][0-9 \-]{6,19}$")


class AdminAccountOut(BaseModel):
    username: str
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None


class AdminAccountUpdate(BaseModel):
    """What an Admin fills in on their own Account page. Notification emails go to `email`."""

    full_name: str = Field(min_length=1, max_length=150)
    email: str = Field(min_length=3, max_length=120)
    phone: str | None = Field(default=None, max_length=30)

    @field_validator("full_name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Enter your name.")
        return v

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        v = v.strip()
        if not _ACCOUNT_EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address.")
        return v

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        if not v:
            return None
        if not _ACCOUNT_PHONE_RE.match(v):
            raise ValueError("Enter a valid phone number, e.g. 0771234567 or +94771234567.")
        return v
