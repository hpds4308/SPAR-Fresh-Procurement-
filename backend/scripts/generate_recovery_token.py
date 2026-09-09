"""
Break-glass account recovery: generates a one-time token that lets one
locked-out account (typically Admin, when there is no other way in) set a
new password via POST /auth/redeem-recovery-token, without needing to
already be logged in.

Requires direct server/Docker access to run — that's deliberate. Issuing
a recovery token needs the same level of access resetting the database
directly would require anyway, so this doesn't lower the security bar; it
just makes the recovery step safe, single-use, and auditable instead of a
raw SQL UPDATE against password_hash.

The token is printed ONCE, here, and nowhere else — never stored in plain
form, never logged. Valid for 30 minutes; generating a new one for the
same account invalidates any earlier unused one.

Usage (from /backend, inside the container or a venv with DATABASE_URL set):
    python -m scripts.generate_recovery_token <username>

If you don't know the username, look it up first, e.g. for the Admin role:
    docker compose exec db psql -U spar_user -d spar_procurement -c \
        "SELECT u.username FROM users u JOIN user_roles ur ON ur.user_id=u.id \
         JOIN roles r ON r.id=ur.role_id WHERE r.code='ADMIN';"
"""
import sys

from app.core.database import SessionLocal
from app.core.errors import NotFoundError
from app.services import auth_service


def main():
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.generate_recovery_token <username>")
        sys.exit(1)
    username = sys.argv[1]

    db = SessionLocal()
    try:
        token = auth_service.create_recovery_token(db, username)
    except NotFoundError as e:
        print(f"Error: {e.message}")
        sys.exit(1)
    finally:
        db.close()

    print(f"\nRecovery token for '{username}' (valid 30 minutes, single use):\n")
    print(f"  {token}\n")
    print("Give this to the account holder directly — it is not stored or logged anywhere else.")
    print("They redeem it at the app's /recover page, or via POST /api/v1/auth/redeem-recovery-token.\n")


if __name__ == "__main__":
    main()
