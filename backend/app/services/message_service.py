"""
Chat between Admin and Supplier, and separately between Admin and Branch.

One thread per supplier (or per branch), shared by every Admin user and
every user of that supplier/branch. Sending and reading are both scoped
through here so the API layer never has to reason about who's allowed to
see what — a supplier user can only ever touch their own supplier_id's
thread, a branch user only their own branch_id's thread; Admin can touch
any of them.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.errors import PermissionDeniedError, NotFoundError
from app.models.branch import Branch
from app.models.message import Message
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.message import BranchThreadOut, MessageOut, SupplierThreadOut


def _to_out(msg: Message, username: str) -> MessageOut:
    return MessageOut(
        id=msg.id,
        supplier_id=msg.supplier_id,
        branch_id=msg.branch_id,
        sender_role=msg.sender_role,
        sender_username=username,
        body=msg.body,
        created_at=msg.created_at,
    )


def _usernames(db: Session, messages: list[Message]) -> dict[int, str]:
    user_ids = {m.sender_user_id for m in messages}
    if not user_ids:
        return {}
    return {u.id: u.username for u in db.query(User).filter(User.id.in_(user_ids)).all()}


def _require_supplier_exists(db: Session, supplier_id: int) -> Supplier:
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise NotFoundError("Supplier not found.")
    return supplier


def _require_branch_exists(db: Session, branch_id: int) -> Branch:
    branch = db.query(Branch).filter(Branch.id == branch_id).first()
    if not branch:
        raise NotFoundError("Branch not found.")
    return branch


def send_as_admin(db: Session, admin: User, supplier_id: int, body: str) -> MessageOut:
    _require_supplier_exists(db, supplier_id)
    msg = Message(
        supplier_id=supplier_id,
        sender_role="ADMIN",
        sender_user_id=admin.id,
        body=body,
        # Admin sent it, so it's implicitly "read" on the admin side already.
        read_by_admin_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return _to_out(msg, admin.username)


def send_as_admin_to_branch(db: Session, admin: User, branch_id: int, body: str) -> MessageOut:
    _require_branch_exists(db, branch_id)
    msg = Message(
        branch_id=branch_id,
        sender_role="ADMIN",
        sender_user_id=admin.id,
        body=body,
        read_by_admin_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return _to_out(msg, admin.username)


def send_as_supplier(db: Session, supplier_user: User, body: str) -> MessageOut:
    if not supplier_user.supplier_id:
        raise PermissionDeniedError("Only supplier accounts can send messages here.")
    msg = Message(
        supplier_id=supplier_user.supplier_id,
        sender_role="SUPPLIER",
        sender_user_id=supplier_user.id,
        body=body,
        read_by_supplier_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return _to_out(msg, supplier_user.username)


def send_as_branch(db: Session, branch_user: User, body: str) -> MessageOut:
    if not branch_user.branch_id:
        raise PermissionDeniedError("Only branch accounts can send messages here.")
    msg = Message(
        branch_id=branch_user.branch_id,
        sender_role="BRANCH",
        sender_user_id=branch_user.id,
        body=body,
        read_by_branch_at=datetime.now(timezone.utc),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return _to_out(msg, branch_user.username)


def list_for_admin(db: Session, supplier_id: int, mark_read: bool = True) -> list[MessageOut]:
    _require_supplier_exists(db, supplier_id)
    messages = (
        db.query(Message)
        .filter(Message.supplier_id == supplier_id)
        .order_by(Message.created_at)
        .all()
    )
    if mark_read:
        unread = [m for m in messages if m.sender_role == "SUPPLIER" and m.read_by_admin_at is None]
        if unread:
            now = datetime.now(timezone.utc)
            for m in unread:
                m.read_by_admin_at = now
            db.commit()
    names = _usernames(db, messages)
    return [_to_out(m, names.get(m.sender_user_id, "—")) for m in messages]


def list_for_admin_branch(db: Session, branch_id: int, mark_read: bool = True) -> list[MessageOut]:
    _require_branch_exists(db, branch_id)
    messages = (
        db.query(Message)
        .filter(Message.branch_id == branch_id)
        .order_by(Message.created_at)
        .all()
    )
    if mark_read:
        unread = [m for m in messages if m.sender_role == "BRANCH" and m.read_by_admin_at is None]
        if unread:
            now = datetime.now(timezone.utc)
            for m in unread:
                m.read_by_admin_at = now
            db.commit()
    names = _usernames(db, messages)
    return [_to_out(m, names.get(m.sender_user_id, "—")) for m in messages]


def list_for_supplier(db: Session, supplier_user: User, mark_read: bool = True) -> list[MessageOut]:
    if not supplier_user.supplier_id:
        raise PermissionDeniedError("Only supplier accounts can view messages here.")
    messages = (
        db.query(Message)
        .filter(Message.supplier_id == supplier_user.supplier_id)
        .order_by(Message.created_at)
        .all()
    )
    if mark_read:
        unread = [m for m in messages if m.sender_role == "ADMIN" and m.read_by_supplier_at is None]
        if unread:
            now = datetime.now(timezone.utc)
            for m in unread:
                m.read_by_supplier_at = now
            db.commit()
    names = _usernames(db, messages)
    return [_to_out(m, names.get(m.sender_user_id, "—")) for m in messages]


def list_for_branch(db: Session, branch_user: User, mark_read: bool = True) -> list[MessageOut]:
    if not branch_user.branch_id:
        raise PermissionDeniedError("Only branch accounts can view messages here.")
    messages = (
        db.query(Message)
        .filter(Message.branch_id == branch_user.branch_id)
        .order_by(Message.created_at)
        .all()
    )
    if mark_read:
        unread = [m for m in messages if m.sender_role == "ADMIN" and m.read_by_branch_at is None]
        if unread:
            now = datetime.now(timezone.utc)
            for m in unread:
                m.read_by_branch_at = now
            db.commit()
    names = _usernames(db, messages)
    return [_to_out(m, names.get(m.sender_user_id, "—")) for m in messages]


def list_admin_threads(db: Session) -> list[SupplierThreadOut]:
    """One row per supplier — every active supplier gets a row even with
    zero messages yet, so Admin can start a conversation with anyone."""
    suppliers = db.query(Supplier).filter(Supplier.status == "ACTIVE").order_by(Supplier.supplier_name).all()
    if not suppliers:
        return []

    all_messages = (
        db.query(Message)
        .filter(Message.supplier_id.in_([s.id for s in suppliers]))
        .order_by(Message.created_at)
        .all()
    )
    by_supplier: dict[int, list[Message]] = {}
    for m in all_messages:
        by_supplier.setdefault(m.supplier_id, []).append(m)

    threads = []
    for s in suppliers:
        msgs = by_supplier.get(s.id, [])
        last = msgs[-1] if msgs else None
        unread = sum(1 for m in msgs if m.sender_role == "SUPPLIER" and m.read_by_admin_at is None)
        threads.append(
            SupplierThreadOut(
                supplier_id=s.id,
                supplier_code=s.supplier_code,
                supplier_name=s.supplier_name,
                last_message_body=last.body if last else None,
                last_message_at=last.created_at if last else None,
                unread_count=unread,
            )
        )
    # Most recent activity first; suppliers with no messages yet sort to
    # the bottom, alphabetically among themselves.
    threads.sort(key=lambda t: t.supplier_name)
    threads.sort(key=lambda t: t.last_message_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    threads.sort(key=lambda t: t.last_message_at is None)
    return threads


def list_admin_branch_threads(db: Session) -> list[BranchThreadOut]:
    """One row per branch — every active branch gets a row even with zero
    messages yet, so Admin can start a conversation with anyone."""
    branches = db.query(Branch).filter(Branch.status == "ACTIVE").order_by(Branch.branch_name).all()
    if not branches:
        return []

    all_messages = (
        db.query(Message)
        .filter(Message.branch_id.in_([b.id for b in branches]))
        .order_by(Message.created_at)
        .all()
    )
    by_branch: dict[int, list[Message]] = {}
    for m in all_messages:
        by_branch.setdefault(m.branch_id, []).append(m)

    threads = []
    for b in branches:
        msgs = by_branch.get(b.id, [])
        last = msgs[-1] if msgs else None
        unread = sum(1 for m in msgs if m.sender_role == "BRANCH" and m.read_by_admin_at is None)
        threads.append(
            BranchThreadOut(
                branch_id=b.id,
                branch_code=b.branch_code,
                branch_name=b.branch_name,
                last_message_body=last.body if last else None,
                last_message_at=last.created_at if last else None,
                unread_count=unread,
            )
        )
    threads.sort(key=lambda t: t.branch_name)
    threads.sort(key=lambda t: t.last_message_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    threads.sort(key=lambda t: t.last_message_at is None)
    return threads


def admin_unread_count(db: Session) -> int:
    """Combined across both supplier and branch threads — Admin sees one
    unread badge, not one per counterparty type."""
    return (
        db.query(Message)
        .filter(Message.sender_role.in_(["SUPPLIER", "BRANCH"]), Message.read_by_admin_at.is_(None))
        .count()
    )


def supplier_unread_count(db: Session, supplier_user: User) -> int:
    if not supplier_user.supplier_id:
        return 0
    return (
        db.query(Message)
        .filter(
            Message.supplier_id == supplier_user.supplier_id,
            Message.sender_role == "ADMIN",
            Message.read_by_supplier_at.is_(None),
        )
        .count()
    )


def branch_unread_count(db: Session, branch_user: User) -> int:
    if not branch_user.branch_id:
        return 0
    return (
        db.query(Message)
        .filter(
            Message.branch_id == branch_user.branch_id,
            Message.sender_role == "ADMIN",
            Message.read_by_branch_at.is_(None),
        )
        .count()
    )
