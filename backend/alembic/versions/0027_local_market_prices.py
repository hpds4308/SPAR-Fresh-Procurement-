"""local_market_prices: per-product min/max wholesale prices in four
markets from each HARTI daily bulletin, for the Admin Local Market
Prices page

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-02

"""
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None

_MARKETS = ("dambulla", "thambuththegama", "keppetipola", "nuwara_eliya")


def upgrade() -> None:
    price_columns = []
    for market in _MARKETS:
        price_columns.append(sa.Column(f"{market}_min", sa.Numeric(10, 2), nullable=True))
        price_columns.append(sa.Column(f"{market}_max", sa.Numeric(10, 2), nullable=True))

    op.create_table(
        "local_market_prices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("dc_code", sa.String(30), nullable=False),
        sa.Column("system_name", sa.String(200), nullable=False),
        sa.Column("pdf_name", sa.String(200), nullable=False),
        *price_columns,
        sa.Column("final_average", sa.Numeric(10, 2), nullable=False),
        sa.Column("imported_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("report_date", "dc_code", name="uq_local_market_price_date_dc_code"),
    )


def downgrade() -> None:
    op.drop_table("local_market_prices")
