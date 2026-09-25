"""branch_safety_stock: per-branch safety stock quantity for each product

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-25

"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "branch_safety_stock",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint("branch_id", "product_id", name="uq_branch_safety_stock_branch_product"),
    )
    op.create_index("ix_branch_safety_stock_branch_id", "branch_safety_stock", ["branch_id"])


def downgrade() -> None:
    op.drop_index("ix_branch_safety_stock_branch_id", table_name="branch_safety_stock")
    op.drop_table("branch_safety_stock")
