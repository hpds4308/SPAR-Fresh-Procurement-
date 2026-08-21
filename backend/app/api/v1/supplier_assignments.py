from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.schemas.assignment import MyAssignmentsOut
from app.services import assignment_service

router = APIRouter(prefix="/assignments", dependencies=[Depends(get_current_user)])


@router.get("/mine", response_model=MyAssignmentsOut)
def my_assignments(
    delivery_date: date | None = None,
    current_user: User = Depends(require_roles("SUPPLIER")),
    db: Session = Depends(get_db),
):
    """A supplier's own confirmed assignments — what Admin has actually assigned to them, and at what price."""
    return assignment_service.get_my_assignments(db, current_user, delivery_date)
