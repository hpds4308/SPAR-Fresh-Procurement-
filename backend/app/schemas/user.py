from pydantic import BaseModel, Field


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
