from datetime import date
import io

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.schemas.assignment import SupplierAssignedProductOut
from app.schemas.supplier_order import (
    SetSupplierOrderRequest,
    SupplierOrderAdminOut,
    SupplierOrderSummaryOut,
    MySupplierOrdersOut,
    SupplierPricePreviewOut,
)
from app.services import assignment_service, supplier_order_service

router = APIRouter(prefix="/supplier-orders", dependencies=[Depends(get_current_user)])


@router.get("/mine", response_model=MySupplierOrdersOut)
def my_supplier_orders(
    delivery_date: date | None = None,
    current_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    """A supplier's own orders, grouped branch by branch, for one delivery date."""
    return supplier_order_service.get_my_orders_by_branch(db, current_user, delivery_date)


def _pivot_by_branch(data: MySupplierOrdersOut) -> tuple[list[dict], list[dict]]:
    """Same transformation the frontend does — one row per product, one
    column per branch, quantity in the cell. Shared by the Excel and PDF
    downloads."""
    branches = [{"branch_id": b.branch_id, "branch_name": b.branch_name} for b in data.branches]
    products: dict[int, dict] = {}
    for branch in data.branches:
        for item in branch.items:
            row = products.setdefault(
                item.product_id,
                {
                    "product_code": item.product_code,
                    "category_name": item.category_name,
                    "description": item.product_description,
                    "unit_code": item.unit_code,
                    "cost_price": None,
                    "price_is_estimated": False,
                    "quantities": {},
                    "total": 0.0,
                },
            )
            row["quantities"][branch.branch_id] = item.quantity
            row["total"] += item.quantity
            if row["cost_price"] is None and item.effective_price is not None:
                row["cost_price"] = item.effective_price
                row["price_is_estimated"] = item.price_is_estimated

    rows = sorted(products.values(), key=lambda r: (r["category_name"], r["description"]))
    return branches, rows


@router.get("/mine/export")
def export_my_supplier_orders(
    delivery_date: date | None = None,
    current_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    """Same data as /mine, pivoted into product-rows x branch-columns and
    downloaded as .xlsx — mirrors the on-screen Orders by Branch table."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    data = supplier_order_service.get_my_orders_by_branch(db, current_user, delivery_date)
    branches, rows = _pivot_by_branch(data)

    wb = Workbook()
    ws = wb.active
    ws.title = "Orders by Branch"

    header = ["Product Code", "Category", "Description", "Cost Price", "Price Basis"] + [
        b["branch_name"] for b in branches
    ] + ["Total"]
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    qty_fill = PatternFill(start_color="FCE4E4", end_color="FCE4E4", fill_type="solid")
    estimated_fill = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")
    branch_totals = {b["branch_id"]: 0.0 for b in branches}
    grand_total = 0.0

    for row in rows:
        price_basis = "Estimated (older date)" if row["price_is_estimated"] else ("Confirmed" if row["cost_price"] is not None else "")
        # Write numeric codes as numbers so suppliers can VLOOKUP them; codes
        # with a leading zero stay text so the zero isn't lost.
        code = row["product_code"]
        code = int(code) if code.isdigit() and not code.startswith("0") else code
        values = [code, row["category_name"], row["description"], row["cost_price"], price_basis]
        for b in branches:
            values.append(row["quantities"].get(b["branch_id"]))
        values.append(row["total"])
        ws.append(values)
        excel_row = ws.max_row
        if row["price_is_estimated"]:
            ws.cell(row=excel_row, column=4).fill = estimated_fill
            ws.cell(row=excel_row, column=5).fill = estimated_fill
        for i, b in enumerate(branches):
            qty = row["quantities"].get(b["branch_id"])
            if qty is not None:
                ws.cell(row=excel_row, column=6 + i).fill = qty_fill
                branch_totals[b["branch_id"]] += qty
        grand_total += row["total"]

    totals_row = ["", "", "Total", "", ""] + [branch_totals[b["branch_id"]] for b in branches] + [grand_total]
    ws.append(totals_row)
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)

    widths = [12, 14, 30, 10, 18] + [12] * len(branches) + [10]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "F2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    date_label = data.delivery_date.isoformat() if data.delivery_date else "no-orders"
    filename = f"orders-by-branch-{date_label}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/mine/export/pdf")
def export_my_supplier_orders_pdf(
    delivery_date: date | None = None,
    current_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    """The Orders by Branch table as a printable PDF — same rows and columns
    as the Excel download, landscape so every branch fits across the page."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from app.models.supplier import Supplier
    from app.services.final_price_service import _SPAR_GREEN, _SPAR_LOGO_PATH

    data = supplier_order_service.get_my_orders_by_branch(db, current_user, delivery_date)
    branches, rows = _pivot_by_branch(data)
    supplier = db.get(Supplier, current_user.supplier_id)
    supplier_name = supplier.supplier_name if supplier else "—"

    def esc(s: str) -> str:
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    def num(v: float | None) -> str:
        if v is None:
            return ""
        return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}".rstrip("0")

    page = landscape(A4)
    margin = 12 * mm
    green = colors.HexColor("#" + _SPAR_GREEN)
    grey = colors.HexColor("#666666")
    # Shrink the type a little when there are many branch columns.
    font_size = 8 if len(branches) <= 8 else 7
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=font_size, leading=font_size + 2)
    head = ParagraphStyle("head", parent=body, fontName="Helvetica-Bold", textColor=colors.white, alignment=1)
    branch_head = ParagraphStyle("branch_head", parent=head, fontSize=font_size - 1, leading=font_size + 1)
    small = ParagraphStyle("small", parent=body, fontSize=8, leading=10, textColor=grey)
    title = ParagraphStyle("title", parent=styles["Title"], fontSize=16, leading=20, textColor=green, alignment=0, spaceAfter=2)

    # Fixed columns: Code, Product, Unit, Cost Price, ...branches..., Total.
    # Branch columns share what's left after giving Product a fair minimum.
    usable = page[0] - 2 * margin
    code_w, unit_w, price_w, total_w = 16 * mm, 10 * mm, 16 * mm, 15 * mm
    fixed = code_w + unit_w + price_w + total_w
    branch_w = min(22 * mm, max(12 * mm, (usable - fixed - 45 * mm) / max(len(branches), 1)))
    product_w = usable - fixed - branch_w * len(branches)

    header = [Paragraph(h, head) for h in ["Code", "Product", "Unit", "Cost Price"]]
    header += [Paragraph(esc(b["branch_name"]), branch_head) for b in branches]
    header.append(Paragraph("Total", head))
    table_rows = [header]
    branch_totals = {b["branch_id"]: 0.0 for b in branches}
    for row in rows:
        price = num(row["cost_price"]) + (" *" if row["price_is_estimated"] else "")
        line = [row["product_code"], Paragraph(esc(row["description"]), body), row["unit_code"], price]
        for b in branches:
            qty = row["quantities"].get(b["branch_id"])
            line.append(num(qty))
            if qty is not None:
                branch_totals[b["branch_id"]] += qty
        line.append(num(row["total"]))
        table_rows.append(line)
    table_rows.append(
        ["", "Total", "", ""] + [num(branch_totals[b["branch_id"]]) for b in branches] + [num(sum(r["total"] for r in rows))]
    )

    first_branch_col, last_col = 4, 4 + len(branches)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), green),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F4F8F5")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#D5E2D9")),
        ("LINEAFTER", (3, 0), (last_col - 1, -1), 0.25, colors.HexColor("#D5E2D9")),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTNAME", (last_col, 1), (last_col, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, green),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    # Same pink as the Excel sheet on cells where a branch ordered the item.
    for r, row in enumerate(rows, start=1):
        for c, b in enumerate(branches, start=first_branch_col):
            if b["branch_id"] in row["quantities"]:
                style.append(("BACKGROUND", (c, r), (c, r), colors.HexColor("#FCE4E4")))
    table = Table(
        table_rows,
        colWidths=[code_w, product_w, unit_w, price_w] + [branch_w] * len(branches) + [total_w],
        repeatRows=1,
    )
    table.setStyle(TableStyle(style))

    date_text = f"{data.delivery_date:%A %d %B %Y}" if data.delivery_date else "No orders yet"
    logo = Image(str(_SPAR_LOGO_PATH), width=50 * mm, height=50 * mm * 161 / 1014)
    logo.hAlign = "LEFT"
    story = [
        logo,
        Spacer(1, 3 * mm),
        Paragraph(f"Orders by Branch — {esc(supplier_name)}", title),
        Paragraph(
            f"<b>Delivery Date:</b> {date_text} &nbsp;·&nbsp; {len(branches)} store{'' if len(branches) == 1 else 's'}"
            f" &nbsp;·&nbsp; {len(rows)} item{'' if len(rows) == 1 else 's'}"
            f" &nbsp;·&nbsp; <b>Order value:</b> Rs. {data.grand_total:,.2f}",
            body,
        ),
        Spacer(1, 4 * mm),
        table,
    ]
    if any(r["price_is_estimated"] for r in rows):
        story += [Spacer(1, 2 * mm), Paragraph("* Cost price estimated from an older date.", small)]

    footer_text = f"SPAR orders by branch · {supplier_name} · delivery {data.delivery_date.isoformat() if data.delivery_date else '—'}"

    def footer(canvas, doc_) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(grey)
        canvas.drawString(margin, 7 * mm, footer_text)
        canvas.drawRightString(page[0] - margin, 7 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=page,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=14 * mm,
        title=f"Orders by Branch — {supplier_name} — {data.delivery_date.isoformat() if data.delivery_date else ''}",
        author="SPAR Fresh Procurement",
    )
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buf.seek(0)

    date_label = data.delivery_date.isoformat() if data.delivery_date else "no-orders"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="orders-by-branch-{date_label}.pdf"'},
    )


@router.get("/admin/dates", response_model=list[date])
def admin_supplier_order_dates(
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Every date any supplier order exists for — powers the Supplier-wise
    side of Admin Order History (Prev/Next navigation and the date picker),
    the same way /orders/admin/dates powers the Branch-wise side."""
    return supplier_order_service.list_supplier_order_dates(db)


@router.get("/admin/summary", response_model=list[SupplierOrderSummaryOut])
def admin_supplier_order_summary(
    delivery_date: date,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """One row per supplier with orders on this date — line count and total value.
    Expanding a row in the UI calls GET /supplier-orders/admin for the branch-by-branch detail."""
    return supplier_order_service.list_supplier_order_summaries(db, delivery_date)


@router.get("/admin", response_model=SupplierOrderAdminOut)
def admin_get_supplier_order(
    supplier_id: int,
    delivery_date: date,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Current order lines for one supplier on one delivery date — used to prefill the builder when editing."""
    return supplier_order_service.get_supplier_order(db, supplier_id, delivery_date)


@router.get("/admin/assigned", response_model=dict[int, float])
def admin_assigned_quantities(
    delivery_date: date,
    exclude_supplier_id: int | None = None,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Total quantity already given to suppliers per product, for one delivery date — pass the supplier
    currently being edited as exclude_supplier_id so their own lines don't count against themselves."""
    return supplier_order_service.get_assigned_quantities(db, delivery_date, exclude_supplier_id)


@router.get("/admin/assigned-by-branch", response_model=dict[str, float])
def admin_assigned_quantities_by_branch(
    delivery_date: date,
    exclude_supplier_id: int | None = None,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Same as /admin/assigned, broken down per branch (key: "product_id:branch_id") — powers
    each branch column's remaining-quantity placeholder on the Order Builder grid."""
    return supplier_order_service.get_assigned_quantities_by_branch(db, delivery_date, exclude_supplier_id)


@router.get("/admin/assignments", response_model=list[SupplierAssignedProductOut])
def admin_assignments_for_supplier(
    supplier_id: int,
    delivery_date: date,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Products already assigned to this supplier for this delivery date via
    Product Assignment (Order Matrix) — powers "Fill from assignments" on
    the Order Builder grid, so a commitment made there doesn't have to be
    manually re-entered branch by branch here."""
    return assignment_service.get_assignments_for_supplier(db, supplier_id, delivery_date)


@router.get("/admin/prices", response_model=list[SupplierPricePreviewOut])
def admin_supplier_price_preview(
    supplier_id: int,
    delivery_date: date,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """This supplier's resolved prices from their last submitted price list — shown as a reference
    column on the Order Builder while Admin is still deciding quantities, before saving any lines."""
    resolved = supplier_order_service.get_supplier_price_preview(db, supplier_id, delivery_date)
    return [
        SupplierPricePreviewOut(
            product_id=pid, price=r.price, is_estimated=r.is_estimated, as_of=r.as_of, approval_status=r.approval_status
        )
        for pid, r in resolved.items()
    ]


@router.put("/admin", response_model=SupplierOrderAdminOut)
def admin_set_supplier_order(
    supplier_id: int,
    delivery_date: date,
    payload: SetSupplierOrderRequest,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """
    Replaces the full set of order lines for this supplier on this
    delivery date (send the complete list each time, not a diff) — e.g.
    Malabe: Avocado 200, Pineapple 100; Kalubovila: Avocado 300, Pineapple 200.
    """
    return supplier_order_service.set_supplier_order(db, admin, supplier_id, delivery_date, payload)
