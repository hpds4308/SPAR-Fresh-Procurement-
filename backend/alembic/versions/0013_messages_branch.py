"""messages: extend the Admin<->Supplier chat thread model to also support
Admin<->Branch threads

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-19

"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("messages", "supplier_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("messages", sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=True))
    op.add_column("messages", sa.Column("read_by_branch_at", sa.DateTime(timezone=True), nullable=True))
    # Exactly one of supplier_id/branch_id is set — a message belongs to
    # one thread, never both and never neither.
    op.create_check_constraint(
        "ck_messages_exactly_one_party",
        "messages",
        "(supplier_id IS NOT NULL AND branch_id IS NULL) OR (supplier_id IS NULL AND branch_id IS NOT NULL)",
    )
    op.create_index("idx_messages_branch", "messages", ["branch_id", "created_at"])
    op.create_index("idx_messages_unread_admin_branch", "messages", ["branch_id", "read_by_admin_at"])
    op.create_index("idx_messages_unread_branch", "messages", ["branch_id", "read_by_branch_at"])


def downgrade() -> None:
    op.drop_index("idx_messages_unread_branch", table_name="messages")
    op.drop_index("idx_messages_unread_admin_branch", table_name="messages")
    op.drop_index("idx_messages_branch", table_name="messages")
    op.drop_constraint("ck_messages_exactly_one_party", "messages", type_="check")
    op.drop_column("messages", "read_by_branch_at")
    op.drop_column("messages", "branch_id")
    op.alter_column("messages", "supplier_id", existing_type=sa.Integer(), nullable=False)
