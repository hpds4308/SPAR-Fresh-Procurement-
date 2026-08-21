"""
Seed authentication data: the 3 roles, one Admin account, and one login
per branch and per supplier (as agreed: shared account per branch/supplier,
not per staff member — this can be changed later without a schema change,
since users.branch_id/supplier_id already model it either way).

Usage:
    python -m scripts.seed_users

Idempotent: existing usernames are left untouched. Prints the generated
credentials once — change these passwords after first login in a real
deployment (Phase 3 ships change-password; forced-reset-on-first-login
can be added in a later phase if wanted).
"""
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import Role, User, UserRole
from app.models.branch import Branch
from app.models.supplier import Supplier

DEFAULT_PASSWORD = "ChangeMe123!"

ROLES = [
    ("ADMIN", "Administrator / Procurement"),
    ("BRANCH", "Branch User"),
    ("SUPPLIER", "Supplier User"),
]


def ensure_roles(db) -> dict[str, Role]:
    role_map = {}
    for code, name in ROLES:
        role = db.query(Role).filter_by(code=code).first()
        if not role:
            role = Role(code=code, name=name)
            db.add(role)
            db.commit()
        role_map[code] = role
    return role_map


def create_user_if_missing(db, username, branch_id=None, supplier_id=None, role: Role = None):
    existing = db.query(User).filter_by(username=username).first()
    if existing:
        return None
    user = User(
        username=username,
        password_hash=hash_password(DEFAULT_PASSWORD),
        branch_id=branch_id,
        supplier_id=supplier_id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    db.commit()
    return user


def main():
    db = SessionLocal()
    created = []
    try:
        roles = ensure_roles(db)

        admin = create_user_if_missing(db, "admin", role=roles["ADMIN"])
        if admin:
            created.append(("admin", "ADMIN"))

        for branch in db.query(Branch).order_by(Branch.branch_code).all():
            username = branch.branch_code.lower()
            user = create_user_if_missing(db, username, branch_id=branch.id, role=roles["BRANCH"])
            if user:
                created.append((username, f"BRANCH ({branch.branch_name})"))

        for supplier in db.query(Supplier).order_by(Supplier.supplier_code).all():
            username = supplier.supplier_code.lower()
            user = create_user_if_missing(db, username, supplier_id=supplier.id, role=roles["SUPPLIER"])
            if user:
                created.append((username, f"SUPPLIER ({supplier.supplier_name})"))

        if created:
            print(f"\nCreated {len(created)} accounts. Default password for all: {DEFAULT_PASSWORD}")
            print("(Each user should change this after first login — use /api/v1/auth/change-password)\n")
            for username, role in created:
                print(f"  {username:12s} -> {role}")
        else:
            print("No new accounts created (all usernames already exist).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
