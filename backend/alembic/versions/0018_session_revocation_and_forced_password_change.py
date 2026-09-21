"""users: token_version + must_change_password; revoked_tokens deny-list

QA findings BUG-03 (refresh tokens could not be revoked) and SEC-01 (all seeded accounts share one
well-known password and there was no way, in the UI or by policy, to change it).

Existing accounts that STILL use the seeded default password are flagged must_change_password here, so
deploying this migration is what forces the change at their next sign-in. Accounts whose password has
already been changed are left alone (each hash is checked - that is the only way to tell them apart).

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-21

"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

# Passwords that must never survive a deploy. Kept here (not imported from the app) so the migration
# stays runnable even if application code changes later.
KNOWN_DEFAULT_PASSWORDS = ("ChangeMe123!",)


def _flag_accounts_still_using_a_known_default() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, password_hash FROM users")).fetchall()
    if not rows:
        return
    try:
        from passlib.context import CryptContext

        ctx = CryptContext(schemes=["argon2"])
    except Exception:  # cannot verify hashes -> safest is to make everybody choose a new password
        bind.execute(sa.text("UPDATE users SET must_change_password = true"))
        return

    to_flag = []
    for user_id, password_hash in rows:
        try:
            if any(ctx.verify(candidate, password_hash) for candidate in KNOWN_DEFAULT_PASSWORDS):
                to_flag.append(user_id)
        except Exception:  # unreadable/legacy hash -> force a reset rather than trust it
            to_flag.append(user_id)
    if to_flag:
        stmt = sa.text("UPDATE users SET must_change_password = true WHERE id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)
        )
        bind.execute(stmt, {"ids": to_flag})


def upgrade() -> None:
    op.add_column("users", sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("users", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default="false"))

    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_revoked_tokens_expires_at", "revoked_tokens", ["expires_at"])

    _flag_accounts_still_using_a_known_default()


def downgrade() -> None:
    op.drop_index("ix_revoked_tokens_expires_at", table_name="revoked_tokens")
    op.drop_table("revoked_tokens")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "token_version")
