"""missed_order_notices: branch missed the cutoff and there was nothing to
auto-submit for it (no draft, no previous order) — shown to Admin until
dismissed

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-01

"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "missed_order_notices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("branch_id", "order_date", name="uq_missed_order_notice_branch_date"),
    )


def downgrade() -> None:
    op.drop_table("missed_order_notices")
