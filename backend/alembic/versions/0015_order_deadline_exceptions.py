"""order_deadline_exceptions: admin grants one branch a late-submission
exception for one specific order_date, past the normal daily cutoff.

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-04

"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_deadline_exceptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), sa.ForeignKey("branches.id"), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("granted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_order_deadline_exception_branch_date",
        "order_deadline_exceptions",
        ["branch_id", "order_date"],
    )


def downgrade() -> None:
    op.drop_table("order_deadline_exceptions")
