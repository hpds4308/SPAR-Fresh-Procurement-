"""email notifications: admin users fill in their own Account details
(name, email, phone) and every email the app sends is logged in
email_log (also used so scheduled reminders go out only once)

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-14

"""
from alembic import op
import sqlalchemy as sa

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(150), nullable=True))
    op.add_column("users", sa.Column("phone", sa.String(30), nullable=True))
    op.create_table(
        "email_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(40), nullable=False),
        # Set for scheduled reminders so each goes out once, e.g.
        # "price-reminder:2026-10-16:5".
        sa.Column("dedupe_key", sa.String(200), nullable=True, unique=True),
        sa.Column("recipient", sa.String(500), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),  # SENT / FAILED / SKIPPED
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_email_log_created", "email_log", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_email_log_created", table_name="email_log")
    op.drop_table("email_log")
    op.drop_column("users", "phone")
    op.drop_column("users", "full_name")
