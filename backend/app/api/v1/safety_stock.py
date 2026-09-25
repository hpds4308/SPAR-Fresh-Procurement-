from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.schemas.safety_stock import SafetyStockOut, SafetyStockSave
from app.services import safety_stock_service

router = APIRouter(prefix="/safety-stock", dependencies=[Depends(get_current_user)])


@router.get("/mine", response_model=SafetyStockOut)
def get_my_safety_stock(
    current_user: User = Depends(require_roles("BRANCH")),
    db: Session = Depends(get_db),
):
    """The branch's saved safety-stock quantities, {product_id: quantity}."""
    return safety_stock_service.get_for_branch(db, current_user)


@router.put("/mine", response_model=SafetyStockOut)
def save_my_safety_stock(
    payload: SafetyStockSave,
    current_user: User = Depends(require_roles("BRANCH")),
    db: Session = Depends(get_db),
):
    """Replaces the whole list; an empty list clears every quantity."""
    return safety_stock_service.save_for_branch(db, current_user, payload)
