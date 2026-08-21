from datetime import date
from pydantic import BaseModel


class DailyReportRow(BaseModel):
    delivery_date: date
    orders_count: int
    assigned_orders_count: int
    branches_count: int
    spend: float


class SupplierSpendRow(BaseModel):
    supplier_id: int
    supplier_code: str
    supplier_name: str
    spend: float
    lines_count: int


class CategorySpendRow(BaseModel):
    category_name: str
    spend: float
    lines_count: int


class TopProductRow(BaseModel):
    product_id: int
    product_code: str
    description: str
    category_name: str
    unit_code: str
    total_quantity: float
    total_spend: float
    order_count: int


class ReportTotals(BaseModel):
    total_orders: int
    assigned_orders: int
    fulfillment_rate: float  # assigned_orders / total_orders, 0..1
    total_spend: float
    days_count: int


class AdminReportOut(BaseModel):
    start_date: date
    end_date: date
    totals: ReportTotals
    daily: list[DailyReportRow]
    by_supplier: list[SupplierSpendRow]
    by_category: list[CategorySpendRow]
    top_products: list[TopProductRow]
