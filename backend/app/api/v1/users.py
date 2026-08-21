import secrets

from fastapi import APIRouter, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_roles, get_user_roles, hash_password
from app.core.audit import write_audit_log
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models.user import User, Role, UserRole
from app.models.branch import Branch
from app.models.supplier import Supplier
from app.schemas.user import (
    UserListItem,
    AvailablePartyOut,
    UserCreateRequest,
    UserCreatedOut,
    UserUpdateRequest,
)

router = APIRouter(prefix="/users", dependencies=[Depends(require_roles("ADMIN"))])

VALID_ROLES = {"ADMIN", "BRANCH", "SUPPLIER"}


def _generate_temp_password() -> str:
    # URL-safe, no ambiguous-character issues when read aloud/typed —
    # unlike seed_users.py's single fixed default, each new account gets
    # its own one-time password that's only ever shown once, here.
    return secrets.token_urlsafe(9)


@router.get("", response_model=list[UserListItem])
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.username).all()
    result = []
    for u in users:
        roles = get_user_roles(db, u.id)
        branch_name = None
        supplier_name = None
        if u.branch_id:
            b = db.get(Branch, u.branch_id)
            branch_name = b.branch_name if b else None
        if u.supplier_id:
            s = db.get(Supplier, u.supplier_id)
            supplier_name = s.supplier_name if s else None
        result.append(
            UserListItem(
                id=u.id,
                username=u.username,
                role=roles[0] if roles else "",
                branch_name=branch_name,
                supplier_name=supplier_name,
                is_active=u.is_active,
                last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
            )
        )
    return result


@router.get("/available-branches", response_model=list[AvailablePartyOut])
def available_branches(db: Session = Depends(get_db)):
    """Active branches with no login account yet — candidates for a new BRANCH user."""
    taken = {u.branch_id for u in db.query(User.branch_id).filter(User.branch_id.isnot(None)).all()}
    branches = db.query(Branch).filter(Branch.status == "ACTIVE").order_by(Branch.branch_name).all()
    return [
        AvailablePartyOut(id=b.id, code=b.branch_code, name=b.branch_name)
        for b in branches
        if b.id not in taken
    ]


@router.get("/available-suppliers", response_model=list[AvailablePartyOut])
def available_suppliers(db: Session = Depends(get_db)):
    """Active suppliers with no login account yet — candidates for a new SUPPLIER user."""
    taken = {u.supplier_id for u in db.query(User.supplier_id).filter(User.supplier_id.isnot(None)).all()}
    suppliers = db.query(Supplier).filter(Supplier.status == "ACTIVE").order_by(Supplier.supplier_name).all()
    return [
        AvailablePartyOut(id=s.id, code=s.supplier_code, name=s.supplier_name)
        for s in suppliers
        if s.id not in taken
    ]


@router.post("", response_model=UserCreatedOut)
def create_user(
    payload: UserCreateRequest,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Creates a login account — previously only possible by SSHing into the
    server and running scripts/seed_users.py. BRANCH/SUPPLIER usernames
    are derived from the branch/supplier code (matching that script's
    convention); ADMIN accounts need an explicit username. Returns a
    one-time temporary password — shown only in this response, never
    stored in plain text or logged.
    """
    if payload.role not in VALID_ROLES:
        raise ValidationFailedError(f"Role must be one of {sorted(VALID_ROLES)}.")

    branch_id = None
    supplier_id = None
    username: str

    if payload.role == "ADMIN":
        if not payload.username:
            raise ValidationFailedError("Username is required for an Admin account.")
        username = payload.username.strip().lower()
    elif payload.role == "BRANCH":
        if not payload.branch_id:
            raise ValidationFailedError("Pick a branch for this account.")
        branch = db.get(Branch, payload.branch_id)
        if not branch:
            raise NotFoundError("Branch not found.")
        if db.query(User).filter(User.branch_id == branch.id).first():
            raise ValidationFailedError(f"{branch.branch_name} already has a login account.")
        branch_id = branch.id
        username = branch.branch_code.lower()
    else:  # SUPPLIER
        if not payload.supplier_id:
            raise ValidationFailedError("Pick a supplier for this account.")
        supplier = db.get(Supplier, payload.supplier_id)
        if not supplier:
            raise NotFoundError("Supplier not found.")
        if db.query(User).filter(User.supplier_id == supplier.id).first():
            raise ValidationFailedError(f"{supplier.supplier_name} already has a login account.")
        supplier_id = supplier.id
        username = supplier.supplier_code.lower()

    if db.query(User).filter(User.username == username).first():
        raise ValidationFailedError(f"Username '{username}' is already taken.")

    role_row = db.query(Role).filter(Role.code == payload.role).first()
    if not role_row:
        raise ValidationFailedError(f"Role '{payload.role}' isn't set up in this system.")

    temp_password = _generate_temp_password()
    user = User(
        username=username,
        password_hash=hash_password(temp_password),
        branch_id=branch_id,
        supplier_id=supplier_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.add(UserRole(user_id=user.id, role_id=role_row.id))
    db.commit()

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="USER_CREATED",
        entity_type="user",
        entity_id=user.id,
        description=f"Created {payload.role} account '{username}'.",
    )
    return UserCreatedOut(id=user.id, username=username, role=payload.role, temporary_password=temp_password)


@router.post("/{user_id}/reset-password", response_model=UserCreatedOut)
def reset_password(
    user_id: int,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Generates a new one-time password for an account that's locked out or
    forgotten its password — previously the only way back in was someone
    with direct DB/server access. Also clears any failed-login lockout,
    since a forgotten password and a lockout tend to arrive together.
    There's no self-service email flow: these are shared branch/supplier
    logins (seed_users.py never sets an email), so "reset via email"
    doesn't fit the account model — Admin resetting it directly is the
    equivalent of a branch/supplier manager calling in, same as before,
    just without needing the server.
    """
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found.")

    roles = get_user_roles(db, user.id)
    role = roles[0] if roles else ""

    temp_password = _generate_temp_password()
    user.password_hash = hash_password(temp_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    db.commit()

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="PASSWORD_RESET",
        entity_type="user",
        entity_id=user.id,
        description=f"Password reset for '{user.username}'.",
    )
    return UserCreatedOut(id=user.id, username=user.username, role=role, temporary_password=temp_password)


@router.patch("/{user_id}", response_model=UserListItem)
def update_user(
    user_id: int,
    payload: UserUpdateRequest,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Renames an account's username and/or sets a specific password Admin
    chooses (as opposed to /reset-password's randomly generated one) —
    the account detail view's "edit" action. Passwords are hashed
    one-way, so there's no equivalent "view the current password";
    setting a new one is the only thing possible, same as everywhere
    else passwords are handled.
    """
    if payload.username is None and payload.password is None:
        raise ValidationFailedError("Nothing to update — provide a new username and/or password.")

    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found.")

    changes = []
    if payload.username is not None:
        new_username = payload.username.strip().lower()
        if new_username != user.username:
            existing = db.query(User).filter(User.username == new_username, User.id != user.id).first()
            if existing:
                raise ValidationFailedError(f"Username '{new_username}' is already taken.")
            changes.append(f"username '{user.username}' -> '{new_username}'")
            user.username = new_username

    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
        user.failed_login_attempts = 0
        user.locked_until = None
        changes.append("password set")

    db.commit()
    db.refresh(user)

    if changes:
        write_audit_log(
            db,
            user_id=admin.id,
            role="ADMIN",
            action="USER_UPDATED",
            entity_type="user",
            entity_id=user.id,
            description=f"Updated account {user.id}: {', '.join(changes)}.",
        )

    roles = get_user_roles(db, user.id)
    branch_name = None
    supplier_name = None
    if user.branch_id:
        b = db.get(Branch, user.branch_id)
        branch_name = b.branch_name if b else None
    if user.supplier_id:
        s = db.get(Supplier, user.supplier_id)
        supplier_name = s.supplier_name if s else None
    return UserListItem(
        id=user.id,
        username=user.username,
        role=roles[0] if roles else "",
        branch_name=branch_name,
        supplier_name=supplier_name,
        is_active=user.is_active,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


@router.post("/{user_id}/deactivate")
def deactivate_user(user_id: int, admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found.")
    user.is_active = False
    db.commit()
    write_audit_log(db, user_id=admin.id, role="ADMIN", action="USER_DISABLED", entity_type="user", entity_id=user_id)
    return {"detail": "User deactivated."}


@router.post("/{user_id}/activate")
def activate_user(user_id: int, admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found.")
    user.is_active = True
    db.commit()
    write_audit_log(db, user_id=admin.id, role="ADMIN", action="USER_ACTIVATED", entity_type="user", entity_id=user_id)
    return {"detail": "User activated."}


@router.delete("/{user_id}")
def delete_user(user_id: int, admin: User = Depends(require_roles("ADMIN")), db: Session = Depends(get_db)):
    """
    Permanently removes an account — only allowed once it's deactivated,
    so this is always a deliberate second step, never a one-click delete
    of a live login. Accounts with real history (past logins, orders,
    price submissions, messages, ...) can't be removed this way: every
    one of those tables references users.id without cascade, so the
    delete fails atomically at the database level and we surface that as
    a friendly error instead of silently losing audit trail / business
    records. In practice this means only accounts that were created by
    mistake and never actually used can be deleted; anything with
    history stays deactivated, which is the correct way to disable it.
    """
    user = db.get(User, user_id)
    if not user:
        raise NotFoundError("User not found.")
    if user.is_active:
        raise ValidationFailedError("Deactivate this account before deleting it.")

    username = user.username
    roles = get_user_roles(db, user.id)
    role = roles[0] if roles else ""

    db.delete(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError(
            "This account can't be deleted — it has activity history (logins, orders, prices, or "
            "messages) linked to it. It stays deactivated so it can no longer sign in, but its "
            "records are kept."
        )

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="USER_DELETED",
        entity_type="user",
        entity_id=user_id,
        description=f"Deleted {role} account '{username}'.",
    )
    return {"detail": f"Account '{username}' deleted."}
