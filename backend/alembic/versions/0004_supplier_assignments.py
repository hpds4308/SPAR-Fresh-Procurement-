"""supplier_assignments: admin's supplier + agreed price per product/day

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-06

"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_assignments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("agreed_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_assignments_product_date", "supplier_assignments", ["product_id", "delivery_date"])
    op.create_index("idx_assignments_supplier", "supplier_assignments", ["supplier_id"])
    op.create_unique_constraint(
        "uq_assignment_product_date_supplier",
        "supplier_assignments",
        ["product_id", "delivery_date", "supplier_id"],
    )


def downgrade() -> None:
    op.drop_table("supplier_assignments")
