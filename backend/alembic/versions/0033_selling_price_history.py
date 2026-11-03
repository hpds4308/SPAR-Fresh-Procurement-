"""selling price history: one row each time the Master Data Team publishes
a new/changed selling price for a product, so branches can look up the
prices that applied on any date

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-03

"""
from alembic import op
import sqlalchemy as sa

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "selling_price_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("version", sa.Integer(), nullable=True),
    )
    op.create_index(
        "idx_selling_price_history_product_time", "selling_price_history", ["product_id", "published_at"]
    )
    # Anything already published before history existed.
    op.execute(
        "INSERT INTO selling_price_history (product_id, price, published_at, published_by) "
        "SELECT id, published_selling_price, selling_price_published_at, selling_price_published_by "
        "FROM products WHERE published_selling_price IS NOT NULL AND selling_price_published_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("idx_selling_price_history_product_time", table_name="selling_price_history")
    op.drop_table("selling_price_history")
