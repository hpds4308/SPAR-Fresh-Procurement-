"""orders: flag orders the system submitted on a branch's behalf after the
cutoff passed with nothing submitted (copied from the same weekday last
week, or the branch's own unsent draft), plus Admin's "reviewed" stamp

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-30

"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("auto_submitted", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("orders", sa.Column("auto_submit_source", sa.String(20), nullable=True))
    op.add_column(
        "orders",
        sa.Column(
            "auto_source_order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="SET NULL", name="fk_orders_auto_source_order_id"),
            nullable=True,
        ),
    )
    op.add_column("orders", sa.Column("auto_reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "orders",
        sa.Column("auto_reviewed_by", sa.Integer(), sa.ForeignKey("users.id", name="fk_orders_auto_reviewed_by"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "auto_reviewed_by")
    op.drop_column("orders", "auto_reviewed_at")
    op.drop_column("orders", "auto_source_order_id")
    op.drop_column("orders", "auto_submit_source")
    op.drop_column("orders", "auto_submitted")
