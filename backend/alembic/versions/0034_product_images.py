"""product images: one 1080x1080 photo (plus a list thumbnail) per
product, uploaded by Admin from the Product List

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-03

"""
from alembic import op
import sqlalchemy as sa

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_images",
        sa.Column(
            "product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("thumb_content_type", sa.String(50), nullable=False),
        sa.Column("thumb", sa.LargeBinary(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("product_images")
