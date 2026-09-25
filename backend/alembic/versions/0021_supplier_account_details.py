"""suppliers: company number, WhatsApp number and account-updated time, filled by the supplier

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-25

"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("company_number", sa.String(50), nullable=True))
    op.add_column("suppliers", sa.Column("whatsapp_number", sa.String(30), nullable=True))
    op.add_column("suppliers", sa.Column("account_updated_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("suppliers", "account_updated_at")
    op.drop_column("suppliers", "whatsapp_number")
    op.drop_column("suppliers", "company_number")
