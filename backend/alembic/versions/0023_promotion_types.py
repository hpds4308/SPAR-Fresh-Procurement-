"""promotion_types: admin-managed promotions (name + color) instead of the
three hardcoded ones; product_promotions now points at one by id, and
deleting a promotion removes it from every product

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-29

"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

# The three promotions that used to be hardcoded, seeded so existing
# product promotions keep their label and color.
BUILT_IN = [
    ("FRESH_CHOICE", "Fresh Choice", "blue"),
    ("SPECIAL_WEEKEND", "Special Weekend Promotion", "green"),
    ("SPECIAL", "Special Promotion", "yellow"),
]


def upgrade() -> None:
    op.create_table(
        "promotion_types",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("color", sa.String(16), nullable=False),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.create_index("uq_promotion_types_name_lower", "promotion_types", [sa.text("lower(name)")], unique=True)

    op.add_column(
        "product_promotions",
        sa.Column(
            "promotion_type_id",
            sa.Integer(),
            sa.ForeignKey("promotion_types.id", ondelete="CASCADE"),
            nullable=True,
        ),
    )
    conn = op.get_bind()
    for code, name, color in BUILT_IN:
        type_id = conn.execute(
            sa.text("INSERT INTO promotion_types (name, color) VALUES (:name, :color) RETURNING id"),
            {"name": name, "color": color},
        ).scalar_one()
        conn.execute(
            sa.text("UPDATE product_promotions SET promotion_type_id = :id WHERE promotion_type = :code"),
            {"id": type_id, "code": code},
        )
    conn.execute(sa.text("DELETE FROM product_promotions WHERE promotion_type_id IS NULL"))
    op.alter_column("product_promotions", "promotion_type_id", nullable=False)
    op.drop_column("product_promotions", "promotion_type")


def downgrade() -> None:
    op.add_column("product_promotions", sa.Column("promotion_type", sa.String(32), nullable=True))
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE product_promotions SET promotion_type = 'SPECIAL'"))
    for code, name, _color in BUILT_IN:
        conn.execute(
            sa.text(
                "UPDATE product_promotions SET promotion_type = :code FROM promotion_types t "
                "WHERE t.id = product_promotions.promotion_type_id AND lower(t.name) = lower(:name)"
            ),
            {"code": code, "name": name},
        )
    op.alter_column("product_promotions", "promotion_type", nullable=False)
    op.drop_column("product_promotions", "promotion_type_id")
    op.drop_index("uq_promotion_types_name_lower", table_name="promotion_types")
    op.drop_table("promotion_types")
