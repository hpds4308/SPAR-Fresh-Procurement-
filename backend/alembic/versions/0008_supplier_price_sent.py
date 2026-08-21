"""supplier_prices: add sent_to_supplier_at so Admin can explicitly send
an adjusted price to the supplier instead of it being visible immediately

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-10

"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "supplier_prices",
        sa.Column("sent_to_supplier_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("supplier_prices", "sent_to_supplier_at")
