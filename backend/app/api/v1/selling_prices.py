from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.schemas.selling_price import SellingPriceListOut
from app.services import selling_price_service

router = APIRouter(prefix="/selling-prices", dependencies=[Depends(get_current_user)])


@router.get("", response_model=SellingPriceListOut)
def list_selling_prices(
    on: date | None = None,
    user: User = Depends(require_roles("BRANCH", "ADMIN", "MASTER_DATA")),
    db: Session = Depends(get_db),
):
    """Published selling prices for every active product as they stood on `on` (default today).
    Read-only; suppliers can't see SPAR's retail prices."""
    return selling_price_service.list_selling_prices(db, on)
