"""branches: add pos_location_code for the 24X7Retail/Dynamic Web POS
integration's getStockInHand call — the POS system's own location code,
distinct from (and not assumed to match) our internal branch_code,
mirroring how products.pos_code is already kept separate from
product_code.

Revision ID: 0014
Revises: 0013
Create Date: 2026-08-28

"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("branches", sa.Column("pos_location_code", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("branches", "pos_location_code")
