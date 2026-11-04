"""imported products: a new "Imported" category whose items are ordered
and priced per case, with Admin setting how many kg one case holds on
each product

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-04

"""
from alembic import op
import sqlalchemy as sa

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("case_kg", sa.Numeric(7, 2), nullable=True))
    op.execute(
        "INSERT INTO product_categories (name) SELECT 'Imported' "
        "WHERE NOT EXISTS (SELECT 1 FROM product_categories WHERE name = 'Imported')"
    )
    op.execute(
        "INSERT INTO product_units (code) SELECT 'case' "
        "WHERE NOT EXISTS (SELECT 1 FROM product_units WHERE lower(code) = 'case')"
    )


def downgrade() -> None:
    # The category and unit rows stay: products may already point at them.
    op.drop_column("products", "case_kg")
