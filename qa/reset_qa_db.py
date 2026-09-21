"""
Reset the transactional data in the LOCAL QA database so the e2e procurement cycle can be re-run
(a branch may only place one order per day, by design).

Safety: refuses to run unless the database name is exactly "spar_qa" and the host is local.

    QA_DATABASE_URL=postgresql://postgres:@127.0.0.1:5432/spar_qa  python qa/reset_qa_db.py
"""
import os
import sys
from urllib.parse import urlsplit

import psycopg2

url = os.environ.get("QA_DATABASE_URL", "postgresql://postgres:@127.0.0.1:5432/spar_qa").replace("+psycopg2", "")
parts = urlsplit(url)
if parts.path.lstrip("/") != "spar_qa" or parts.hostname not in ("127.0.0.1", "localhost"):
    sys.exit(f"Refusing to reset {parts.hostname}/{parts.path.lstrip('/')}: only local database 'spar_qa' is allowed.")

TABLES = [
    "supplier_order_items", "supplier_assignments", "order_lines", "orders",
    "supplier_prices", "market_reference_prices", "messages", "order_deadline_exceptions",
]
with psycopg2.connect(url) as conn, conn.cursor() as cur:
    for t in TABLES:
        cur.execute(f"DELETE FROM {t}")
        print(f"cleared {t}: {cur.rowcount} rows")
    cur.execute("DELETE FROM revoked_tokens")
    print(f"cleared revoked_tokens: {cur.rowcount} rows")
    # Restore the seeded starting password and lift the forced-change flag, so the e2e/perf scripts (which
    # sign in as br02/sup01/admin with the seeded password) work again after a test changed a password.
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from passlib.context import CryptContext

    seeded = CryptContext(schemes=["argon2"]).hash(os.environ.get("QA_PASSWORD", "ChangeMe123!"))
    cur.execute(
        "UPDATE users SET failed_login_attempts = 0, locked_until = NULL, is_active = true, "
        "password_hash = %s, must_change_password = false, token_version = 0",
        (seeded,),
    )
    print(f"reset users (unlocked, active, seeded password, no forced change): {cur.rowcount}")
