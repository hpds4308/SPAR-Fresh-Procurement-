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
    # True -> the SPA must show the change-password screen before anything else (see get_current_user).
    must_change_password: bool = False


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    """Optional body for /auth/logout: the refresh token of the session being closed, so it can be revoked."""

    refresh_token: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


class RedeemRecoveryTokenRequest(BaseModel):
    """Body for the break-glass account-recovery endpoint — see
    scripts/generate_recovery_token.py for how the token is issued."""

    token: str
    new_password: str = Field(min_length=8)


class ChangePasswordResponse(BaseModel):
    detail: str = "Password changed successfully."
    # Fresh tokens: changing the password revokes every older token, including the caller's own.
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class CurrentUserResponse(BaseModel):
    id: int
    username: str
    role: str
    must_change_password: bool = False
    branch_id: int | None = None
    branch_name: str | None = None
    supplier_id: int | None = None
    supplier_name: str | None = None
