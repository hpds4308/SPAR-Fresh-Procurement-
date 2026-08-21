"""messages: one chat thread per supplier, shared by Admin and Supplier

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-11

"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("sender_role", sa.String(20), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("read_by_admin_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_by_supplier_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("idx_messages_supplier", "messages", ["supplier_id", "created_at"])
    # Speeds up unread-count queries for each side of a thread.
    op.create_index(
        "idx_messages_unread_admin", "messages", ["supplier_id", "read_by_admin_at"]
    )
    op.create_index(
        "idx_messages_unread_supplier", "messages", ["supplier_id", "read_by_supplier_at"]
    )


def downgrade() -> None:
    op.drop_table("messages")
