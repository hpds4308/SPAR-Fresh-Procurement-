from datetime import date, datetime

from pydantic import BaseModel


class IssuePurchaseOrderRequest(BaseModel):
    supplier_id: int
    delivery_date: date


class PurchaseOrderLineOut(BaseModel):
    product_id: int
    product_code: str
    product_description: str
    unit_code: str
    quantity: float
    unit_price: float
    line_total: float
    # True when the price came from the supplier's quote for a different
    # date (see supplier_order_service._resolve_prices) — still printed,
    # but flagged so nobody mistakes it for a confirmed same-day price.
    price_is_estimated: bool = False
    notes: str | None = None


class BranchPurchaseOrderOut(BaseModel):
    """One branch's share of the PO — printed as its own branch PO."""

    branch_id: int
    branch_code: str
    branch_name: str
    branch_location: str | None
    po_number: str
    lines: list[PurchaseOrderLineOut]
    total: float


class PurchaseOrderSupplierOut(BaseModel):
    supplier_id: int
    supplier_code: str
    supplier_name: str
    contact_person: str | None
    phone: str | None
    email: str | None
    address: str | None
    company_number: str | None


class PurchaseOrderSummaryOut(BaseModel):
    id: int
    po_number: str
    revision: int
    status: str
    supplier_id: int
    supplier_name: str
    delivery_date: date
    branch_count: int
    line_count: int
    total_amount: float
    issued_at: datetime
    issued_by_name: str | None
    cancelled_at: datetime | None


class PurchaseOrderDetailOut(PurchaseOrderSummaryOut):
    supplier: PurchaseOrderSupplierOut
    # Supplier PO: every branch combined, one line per product (and price).
    consolidated_lines: list[PurchaseOrderLineOut]
    branches: list[BranchPurchaseOrderOut]
    # Admin only: the live Supplier Orders lines no longer match this PO.
    is_outdated: bool = False


class PurchaseOrderAdminRowOut(BaseModel):
    """One row per supplier on Admin's Purchase Orders list for a date:
    their saved order, and the PO issued from it (if any)."""

    supplier_id: int
    supplier_name: str
    delivery_date: date
    line_count: int
    order_total: float
    unpriced_line_count: int
    purchase_order: PurchaseOrderSummaryOut | None
    is_outdated: bool
