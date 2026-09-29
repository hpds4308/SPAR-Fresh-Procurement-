from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.schemas.promotion import PromotionOut, PromotionSave, PromotionTypeIn, PromotionTypeOut
from app.services import promotion_service

router = APIRouter(prefix="/promotions", dependencies=[Depends(get_current_user)])


@router.get("/active", response_model=list[PromotionOut])
def list_active_promotions(db: Session = Depends(get_db)):
    """Promotions running today — shown to branches as labels by the product name."""
    return promotion_service.list_active(db)


@router.get("/types", response_model=list[PromotionTypeOut])
def list_promotion_types(
    _admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Every promotion Admin has created, with how many products use each."""
    return promotion_service.list_types(db)


@router.post("/types", response_model=PromotionTypeOut, status_code=201)
def create_promotion_type(
    payload: PromotionTypeIn,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    return promotion_service.create_type(db, admin, payload)


@router.delete("/types/{type_id}", status_code=204)
def delete_promotion_type(
    type_id: int,
    admin: User = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    """Deletes the promotion and removes it from every product it was set on."""
    promotion_service.delete_type(db, admin, type_id)
    return Response(status_code=204)


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
