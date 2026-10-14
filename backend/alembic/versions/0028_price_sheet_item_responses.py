"""supplier_price_revisions.item_responses: the supplier approves or rejects
each item on a price sheet separately, optionally giving their own final
price for a rejected item; a sheet with both approved and rejected items
gets the new PARTIAL status

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-14

"""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("supplier_price_revisions", sa.Column("item_responses", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("supplier_price_revisions", "item_responses")
