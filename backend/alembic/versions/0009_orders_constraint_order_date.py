"""orders: re-key the one-order-per-day constraint on order_date instead
of delivery_date.

Why: delivery_date used to always be order_date + 1, so constraining on
(branch_id, delivery_date) was equivalent to one-per-day. Now that
delivery_date == order_date (see the "delivery date = order date" change),
a branch's very last order placed under the *old* rule — e.g. placed
yesterday, targeting delivery today — occupies today's delivery_date.
Any new order placed *today* under the new rule also targets delivery
today, so it collides with that leftover row on the old constraint even
though it's a legitimate, distinct order. order_date is now the true
"one order per branch per day" key going forward, so the constraint moves
there instead.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-11

"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_orders_branch_delivery_date", "orders", type_="unique")
    op.create_unique_constraint(
        "uq_orders_branch_order_date", "orders", ["branch_id", "order_date"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_orders_branch_order_date", "orders", type_="unique")
    op.create_unique_constraint(
        "uq_orders_branch_delivery_date", "orders", ["branch_id", "delivery_date"]
    )
