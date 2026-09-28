"""supplier_price_revisions: Admin's adjusted prices are sent to a supplier as
one price sheet, which the supplier e-signs to approve (or rejects with a
reason); supplier_prices.revision_id links each quote to the sheet it was
last sent on

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-28

"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_price_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("supplier_id", sa.Integer(), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("delivery_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("sent_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("responded_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signer_name", sa.String(150), nullable=True),
        sa.Column("signature_image", sa.Text(), nullable=True),
        sa.Column("signer_ip", sa.String(255), nullable=True),
        sa.Column("signer_user_agent", sa.String(500), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("closed_reason", sa.String(255), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_supplier_price_revisions_supplier_date",
        "supplier_price_revisions",
        ["supplier_id", "delivery_date"],
    )
    op.create_index("ix_supplier_price_revisions_status", "supplier_price_revisions", ["status"])

    op.add_column(
        "supplier_prices",
        sa.Column(
            "revision_id",
            sa.Integer(),
            sa.ForeignKey("supplier_price_revisions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Adjusted prices already sent before this migration were never signed
    # for. Un-send them so they show as drafts Admin can send for approval,
    # rather than being silently treated as agreed.
    op.execute("UPDATE supplier_prices SET sent_to_supplier_at = NULL")


def downgrade() -> None:
    op.drop_column("supplier_prices", "revision_id")
    op.drop_index("ix_supplier_price_revisions_status", table_name="supplier_price_revisions")
    op.drop_index("ix_supplier_price_revisions_supplier_date", table_name="supplier_price_revisions")
    op.drop_table("supplier_price_revisions")
