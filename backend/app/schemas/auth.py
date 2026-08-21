from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str
    redirect_to: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class CurrentUserResponse(BaseModel):
    id: int
    username: str
    role: str
    branch_id: int | None = None
    branch_name: str | None = None
    supplier_id: int | None = None
    supplier_name: str | None = None
