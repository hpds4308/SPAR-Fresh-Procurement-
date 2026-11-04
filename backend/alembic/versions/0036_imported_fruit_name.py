"""rename the "Imported" category to "Imported Fruit"

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-04

"""
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE product_categories SET name = 'Imported Fruit' WHERE name = 'Imported' "
        "AND NOT EXISTS (SELECT 1 FROM product_categories WHERE name = 'Imported Fruit')"
    )


def downgrade() -> None:
    op.execute("UPDATE product_categories SET name = 'Imported' WHERE name = 'Imported Fruit'")
