"""
Import every model module here so that Base.metadata is fully populated
for Alembic autogenerate and for create_all() in local/dev scripts.
"""
from app.models.user import Role, User, UserRole  # noqa: F401
from app.models.branch import Branch  # noqa: F401
from app.models.supplier import Supplier  # noqa: F401
from app.models.product import ProductCategory, ProductUnit, Product  # noqa: F401
from app.models.order import Order, OrderLine  # noqa: F401
from app.models.pricing import SupplierPrice  # noqa: F401
from app.models.assignment import SupplierAssignment  # noqa: F401
from app.models.supplier_order import SupplierOrderItem  # noqa: F401
from app.models.message import Message  # noqa: F401
from app.models.market_reference_price import MarketReferencePrice  # noqa: F401
from app.models.system import SystemSetting, AuditLog  # noqa: F401
