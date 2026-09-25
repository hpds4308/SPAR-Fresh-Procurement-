from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.schemas.promotion import PromotionOut, PromotionSave
from app.services import promotion_service

router = APIRouter(prefix="/promotions", dependencies=[Depends(get_current_user)])


@router.get("/active", response_model=list[PromotionOut])
def list_active_promotions(db: Session = Depends(get_db)):
    """Promotions running today — shown to branches as labels by the product name."""
    return promotion_service.list_active(db)


@router.get("", response_model=list[PromotionOut])
def list_promotions(
    _admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Every saved promotion, including upcoming and ended ones."""
    return promotion_service.list_all(db)


@router.put("", response_model=list[PromotionOut])
def save_promotions(
    payload: PromotionSave,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Replaces the whole list; an empty list clears every promotion."""
    return promotion_service.save_all(db, admin, payload)
