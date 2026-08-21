from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import date
import io

from app.core.database import get_db
from app.core.security import get_current_user, get_user_roles, require_roles
from app.models.branch import Branch
from app.models.product import Product
from app.models.user import User
from app.schemas.order import (
    OrderCreate,
    OrderOut,
    OrderLineOut,
    OrderSummary,
    OrderWindowOut,
    OrderMatrixOut,
    DeliveryConfirmRequest,
)
from app.schemas.assignment import ProductComparisonOut, SetAssignmentsRequest
from app.services import order_service, assignment_service

router = APIRouter(prefix="/orders", dependencies=[Depends(get_current_user)])


def _to_order_out(db: Session, order) -> OrderOut:
    branch = db.get(Branch, order.branch_id)
    submitted_by = db.get(User, order.submitted_by)
    confirmed_by = db.get(User, order.confirmed_by) if order.confirmed_by else None

    # No ORM relationship defined between Order and OrderLine (kept explicit,
    # matching the rest of this codebase) — fetch lines directly instead.
    from app.models.order import OrderLine

    lines = db.query(OrderLine).filter(OrderLine.order_id == order.id).all()
    line_product_ids = [ln.product_id for ln in lines]
    products = {p.id: p for p in db.query(Product).filter(Product.id.in_(line_product_ids)).all()}

    return OrderOut(
        id=order.id,
        branch_id=order.branch_id,
        branch_name=branch.branch_name if branch else "—",
        order_date=order.order_date,
        delivery_date=order.delivery_date,
        status=order.status,
        notes=order.notes,
        submitted_by_username=submitted_by.username if submitted_by else "—",
        confirmed_at=order.confirmed_at.isoformat() if order.confirmed_at else None,
        confirmed_by_username=confirmed_by.username if confirmed_by else None,
        lines=[
            OrderLineOut(
                id=ln.id,
                product_id=ln.product_id,
                product_code=products[ln.product_id].product_code if ln.product_id in products else "—",
                product_description=products[ln.product_id].description if ln.product_id in products else "—",
                quantity=float(ln.quantity),
                unit_code=ln.unit_code,
                notes=ln.notes,
                received_quantity=float(ln.received_quantity) if ln.received_quantity is not None else None,
                receipt_notes=ln.receipt_notes,
            )
            for ln in lines
        ],
    )


@router.get("/window", response_model=OrderWindowOut)
def order_window(db: Session = Depends(get_db)):
    """Tells the branch UI whether ordering is open right now, and for which delivery date."""
    return order_service.get_order_window(db)


# NOTE: these two /admin/matrix* routes must stay registered before
# GET /{order_id} below — otherwise Starlette matches "admin" as an
# order_id path segment first and returns a 422 instead of ever reaching
# these handlers.
@router.get("/admin/matrix", response_model=OrderMatrixOut)
def get_order_matrix(
    delivery_date: date | None = None,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Consolidated view: every active product x every branch, quantities for the given delivery date."""
    return order_service.get_order_matrix(db, delivery_date)


@router.get("/admin/matrix/export")
def export_order_matrix(
    delivery_date: date | None = None,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Same data as /admin/matrix, as a downloadable .xlsx workbook."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    matrix = order_service.get_order_matrix(db, delivery_date)

    wb = Workbook()
    ws = wb.active
    ws.title = "Order Matrix"

    header = ["Category", "Product Code", "Product Description", "Unit"] + [
        b["branch_name"] for b in matrix["branches"]
    ]
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    for row in matrix["rows"]:
        values = [row["category_name"], row["product_code"], row["description"], row["unit_code"]]
        for b in matrix["branches"]:
            values.append(row["quantities"].get(str(b["branch_id"]), None))
        ws.append(values)

    widths = [12, 16, 34, 8] + [14] * len(matrix["branches"])
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "E2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"order-matrix-{matrix['delivery_date'].isoformat()}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/admin/product/{product_id}/comparison", response_model=ProductComparisonOut)
def get_product_comparison(
    product_id: int,
    delivery_date: date,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    All suppliers' quoted prices for one product on one delivery date,
    alongside total branch demand and any assignments already made.
    """
    return assignment_service.get_product_comparison(db, product_id, delivery_date)


@router.put("/admin/product/{product_id}/assignments", response_model=ProductComparisonOut)
def set_product_assignments(
    product_id: int,
    delivery_date: date,
    payload: SetAssignmentsRequest,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Replaces the full set of supplier assignments for this product on this
    delivery date (i.e. send the complete list each time, not a diff).
    Recomputes affected branch orders' status (SUBMITTED <-> ASSIGNED).
    """
    return assignment_service.set_assignments(db, admin, product_id, delivery_date, payload)


@router.post("", response_model=OrderOut)
def submit_order(
    payload: OrderCreate,
    current_user: User = Depends(require_roles("BRANCH")),
    db: Session = Depends(get_db),
):
    order = order_service.create_order(db, current_user, payload)
    return _to_order_out(db, order)


@router.get("", response_model=list[OrderSummary])
def list_orders(
    delivery_date: date | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    roles = get_user_roles(db, current_user.id)
    orders = order_service.list_orders(db, current_user, roles, delivery_date)
    from app.models.order import OrderLine

    result = []
    for o in orders:
        branch = db.get(Branch, o.branch_id)
        line_count = db.query(OrderLine).filter(OrderLine.order_id == o.id).count()
        result.append(
            OrderSummary(
                id=o.id,
                branch_id=o.branch_id,
                branch_name=branch.branch_name if branch else "—",
                order_date=o.order_date,
                delivery_date=o.delivery_date,
                status=o.status,
                line_count=line_count,
            )
        )
    return result


@router.get("/admin/dates", response_model=list[date])
def admin_order_dates(
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Every date any branch order exists for, most recent first — powers Order History's day browser."""
    return order_service.list_order_dates(db)


@router.get("/{order_id}", response_model=OrderOut)
def get_order(order_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    roles = get_user_roles(db, current_user.id)
    order = order_service.get_order_detail(db, current_user, order_id, roles)
    return _to_order_out(db, order)


@router.put("/{order_id}/confirm-delivery", response_model=OrderOut)
def confirm_delivery(
    order_id: int,
    payload: DeliveryConfirmRequest,
    current_user: User = Depends(require_roles("BRANCH")),
    db: Session = Depends(get_db),
):
    """
    Branch confirms what actually arrived for one of their assigned
    orders. Received quantities may differ from what was ordered.
    """
    order = order_service.confirm_delivery(db, current_user, order_id, payload)
    return _to_order_out(db, order)


@router.post("/{order_id}/cancel")
def cancel_order(
    order_id: int,
    current_user: User = Depends(require_roles("BRANCH")),
    db: Session = Depends(get_db),
):
    """
    Branch cancels its own still-SUBMITTED order before today's cutoff —
    only path is currently "submit a corrected one afterward", since
    there's no in-place edit. Only ADMIN reassignment work happens once
    it's ASSIGNED/CONFIRMED, which this deliberately does not touch.
    """
    order_service.cancel_order(db, current_user, order_id)
    return {"detail": "Order cancelled."}
