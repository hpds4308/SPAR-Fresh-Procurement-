"""master data workflow: MASTER_DATA role, where each selling price came
from (MANUAL / AUTO), the selling price the Master Data Team published
to branches (with who and when), and a versioned copy of the Master
Data Sheet each time Admin sends it to the team

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-03

"""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "INSERT INTO roles (code, name) SELECT 'MASTER_DATA', 'Master Data Team' "
        "WHERE NOT EXISTS (SELECT 1 FROM roles WHERE code = 'MASTER_DATA')"
    )

    op.add_column("products", sa.Column("selling_price_source", sa.String(10), nullable=True))
    op.create_check_constraint(
        "chk_products_selling_price_source", "products", "selling_price_source IN ('MANUAL', 'AUTO')"
    )
    # Nothing recorded where today's prices came from, so treat every one
    # as typed by Admin: Auto-generate then leaves all of them alone.
    op.execute("UPDATE products SET selling_price_source = 'MANUAL' WHERE selling_price IS NOT NULL")

    op.add_column("products", sa.Column("published_selling_price", sa.Numeric(10, 2), nullable=True))
    op.add_column("products", sa.Column("selling_price_published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "products",
        sa.Column("selling_price_published_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    )

    op.create_table(
        "master_data_submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False, unique=True),
        sa.Column("sent_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("product_count", sa.Integer(), nullable=False),
        # The sheet exactly as Admin sent it (MasterDataSheetOut as JSON).
        sa.Column("sheet", sa.JSON(), nullable=False),
        sa.Column("published_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_summary", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("master_data_submissions")
    op.drop_column("products", "selling_price_published_by")
    op.drop_column("products", "selling_price_published_at")
    op.drop_column("products", "published_selling_price")
    op.drop_constraint("chk_products_selling_price_source", "products", type_="check")
    op.drop_column("products", "selling_price_source")
    op.execute(
        "DELETE FROM user_roles WHERE role_id IN (SELECT id FROM roles WHERE code = 'MASTER_DATA')"
    )
    op.execute("DELETE FROM roles WHERE code = 'MASTER_DATA'")
