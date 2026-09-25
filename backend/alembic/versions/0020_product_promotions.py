"""product_promotions: admin-set fruit & vegetable promotion per product

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-25

"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_promotions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("promotion_type", sa.String(32), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        sa.UniqueConstraint("product_id", name="uq_product_promotions_product"),
        sa.CheckConstraint("end_date >= start_date", name="ck_product_promotions_date_range"),
    )


def downgrade() -> None:
    op.drop_table("product_promotions")
