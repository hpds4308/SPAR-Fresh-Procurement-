from fastapi import APIRouter

from app.api.v1 import (
    health,
    auth,
    users,
    products,
    orders,
    pricing,
    supplier_assignments,
    supplier_orders,
    suppliers,
    reports,
    messages,
    master_data,
    audit_logs,
    settings,
    branches,
    safety_stock,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(products.router, tags=["products"])
api_router.include_router(orders.router, tags=["orders"])
api_router.include_router(pricing.router, tags=["pricing"])
api_router.include_router(supplier_assignments.router, tags=["assignments"])
api_router.include_router(supplier_orders.router, tags=["supplier-orders"])
api_router.include_router(suppliers.router, tags=["suppliers"])
api_router.include_router(reports.router, tags=["reports"])
api_router.include_router(messages.router, tags=["messages"])
api_router.include_router(master_data.router, tags=["master-data"])
api_router.include_router(audit_logs.router, tags=["audit-logs"])
api_router.include_router(settings.router, tags=["settings"])
api_router.include_router(branches.router, tags=["branches"])
api_router.include_router(safety_stock.router, tags=["safety-stock"])
