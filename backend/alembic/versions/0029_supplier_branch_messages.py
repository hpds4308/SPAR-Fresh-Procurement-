"""messages: suppliers and branches chat with each other directly — a
message with BOTH supplier_id and branch_id set belongs to that
supplier<->branch conversation (Admin can read it, not post in it)

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-14

"""
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_messages_exactly_one_party", "messages", type_="check")
    # Supplier only = Admin<->supplier, branch only = Admin<->branch,
    # both = supplier<->branch. Never neither.
    op.create_check_constraint(
        "ck_messages_has_party",
        "messages",
        "supplier_id IS NOT NULL OR branch_id IS NOT NULL",
    )
    op.create_index("idx_messages_supplier_branch", "messages", ["supplier_id", "branch_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_messages_supplier_branch", table_name="messages")
    op.execute("DELETE FROM messages WHERE supplier_id IS NOT NULL AND branch_id IS NOT NULL")
    op.drop_constraint("ck_messages_has_party", "messages", type_="check")
    op.create_check_constraint(
        "ck_messages_exactly_one_party",
        "messages",
        "(supplier_id IS NOT NULL AND branch_id IS NULL) OR (supplier_id IS NULL AND branch_id IS NOT NULL)",
    )
