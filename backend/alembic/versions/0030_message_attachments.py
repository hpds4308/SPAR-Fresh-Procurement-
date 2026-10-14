"""message_attachments: photos and files attached to chat messages,
stored in the database (uploaded first, then linked to the message when
it's sent)

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-14

"""
from alembic import op
import sqlalchemy as sa

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "message_attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Null until the message it was uploaded for is sent.
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("idx_message_attachments_message", "message_attachments", ["message_id"])


def downgrade() -> None:
    op.drop_index("idx_message_attachments_message", table_name="message_attachments")
    op.drop_table("message_attachments")
