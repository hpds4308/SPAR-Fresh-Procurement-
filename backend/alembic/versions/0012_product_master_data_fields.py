"""products: add target_gp_percent, selling_price, reference_cost_price —
Admin's own margin/pricing reference fields for the Master Data Sheet

Revision ID: 0012
Revises: 0011
Create Date: 2026-08-13

"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("target_gp_percent", sa.Numeric(5, 4), nullable=True))
    op.add_column("products", sa.Column("selling_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("products", sa.Column("reference_cost_price", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "reference_cost_price")
    op.drop_column("products", "selling_price")
    op.drop_column("products", "target_gp_percent")
