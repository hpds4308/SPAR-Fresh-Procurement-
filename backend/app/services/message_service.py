"""
Chat between Admin and Supplier, between Admin and Branch, and directly
between a supplier and a branch.

One Admin thread per supplier (or per branch), shared by every Admin user
and every user of that supplier/branch; plus one thread per supplier +
branch pair. Sending and reading are both scoped through here so the API
layer never has to reason about who's allowed to see what — a supplier
user can only ever touch their own supplier_id's threads, a branch user
only their own branch_id's; Admin can touch any Admin thread and read
(but not post in) every supplier<->branch thread.
"""
from datetime import datetime, timezone

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.errors import PermissionDeniedError, NotFoundError
from app.models.branch import Branch
from app.models.message import Message
from app.models.supplier import Supplier
from app.models.user import User
from app.schemas.message import (
    BranchThreadOut,
    ContactThreadOut,
    MessageOut,
    PairConversationOut,
    SupplierThreadOut,
)

# Which thread a message belongs to (see models/message.py).
_ADMIN_SUPPLIER = Message.branch_id.is_(None)
_ADMIN_BRANCH = Message.supplier_id.is_(None)
_SUPPLIER_BRANCH = and_(Message.supplier_id.isnot(None), Message.branch_id.isnot(None))


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
        .filter(Message.supplier_id == supplier_id, _ADMIN_SUPPLIER)
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
        .filter(Message.branch_id == branch_id, _ADMIN_BRANCH)
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
        .filter(Message.supplier_id == supplier_user.supplier_id, _ADMIN_SUPPLIER)
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
        .filter(Message.branch_id == branch_user.branch_id, _ADMIN_BRANCH)
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
        .filter(Message.supplier_id.in_([s.id for s in suppliers]), _ADMIN_SUPPLIER)
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
        .filter(Message.branch_id.in_([b.id for b in branches]), _ADMIN_BRANCH)
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
    unread badge, not one per counterparty type. Supplier<->branch chats
    don't count: Admin only looks in on those."""
    return (
        db.query(Message)
        .filter(
            Message.sender_role.in_(["SUPPLIER", "BRANCH"]),
            Message.read_by_admin_at.is_(None),
            or_(_ADMIN_SUPPLIER, _ADMIN_BRANCH),
        )
        .count()
    )


def supplier_unread_count(db: Session, supplier_user: User) -> int:
    if not supplier_user.supplier_id:
        return 0
    # Admin's messages, plus branches' messages in supplier<->branch chats.
    return (
        db.query(Message)
        .filter(
            Message.supplier_id == supplier_user.supplier_id,
            Message.sender_role.in_(["ADMIN", "BRANCH"]),
            Message.read_by_supplier_at.is_(None),
        )
        .count()
    )


def branch_unread_count(db: Session, branch_user: User) -> int:
    if not branch_user.branch_id:
        return 0
    # Admin's messages, plus suppliers' messages in supplier<->branch chats.
    return (
        db.query(Message)
        .filter(
            Message.branch_id == branch_user.branch_id,
            Message.sender_role.in_(["ADMIN", "SUPPLIER"]),
            Message.read_by_branch_at.is_(None),
        )
        .count()
    )


# ---- Supplier <-> branch chats ----


def _peer_ids(user: User, other_id: int) -> tuple[int, int]:
    """(supplier_id, branch_id) of the chat between `user` and the other party."""
    if user.supplier_id:
        return user.supplier_id, other_id
    if user.branch_id:
        return other_id, user.branch_id
    raise PermissionDeniedError("Only supplier and branch accounts can chat with each other.")


def _require_active_peer(db: Session, user: User, other_id: int) -> None:
    """A supplier chats with any active branch; a branch with any active supplier."""
    if user.supplier_id:
        other = db.query(Branch).filter(Branch.id == other_id, Branch.status == "ACTIVE").first()
        if not other:
            raise NotFoundError("Branch not found.")
    else:
        other = db.query(Supplier).filter(Supplier.id == other_id, Supplier.status == "ACTIVE").first()
        if not other:
            raise NotFoundError("Supplier not found.")


def _pair_messages(db: Session, supplier_id: int, branch_id: int) -> list[Message]:
    return (
        db.query(Message)
        .filter(Message.supplier_id == supplier_id, Message.branch_id == branch_id)
        .order_by(Message.created_at, Message.id)
        .all()
    )


def send_to_peer(db: Session, user: User, other_id: int, body: str) -> MessageOut:
    supplier_id, branch_id = _peer_ids(user, other_id)
    _require_active_peer(db, user, other_id)
    now = datetime.now(timezone.utc)
    msg = Message(
        supplier_id=supplier_id,
        branch_id=branch_id,
        sender_role="SUPPLIER" if user.supplier_id else "BRANCH",
        sender_user_id=user.id,
        body=body,
        # The sender has obviously read it; read_by_admin_at stays unset —
        # Admin only looks in on these chats.
        read_by_supplier_at=now if user.supplier_id else None,
        read_by_branch_at=now if user.branch_id else None,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return _to_out(msg, user.username)


def list_with_peer(db: Session, user: User, other_id: int, mark_read: bool = True) -> list[MessageOut]:
    """The chat between `user` and one branch (for a supplier) or one supplier (for a branch)."""
    supplier_id, branch_id = _peer_ids(user, other_id)
    _require_active_peer(db, user, other_id)
    messages = _pair_messages(db, supplier_id, branch_id)
    if mark_read:
        now = datetime.now(timezone.utc)
        changed = False
        for m in messages:
            if user.supplier_id and m.sender_role == "BRANCH" and m.read_by_supplier_at is None:
                m.read_by_supplier_at = now
                changed = True
            elif user.branch_id and m.sender_role == "SUPPLIER" and m.read_by_branch_at is None:
                m.read_by_branch_at = now
                changed = True
        if changed:
            db.commit()
    names = _usernames(db, messages)
    return [_to_out(m, names.get(m.sender_user_id, "—")) for m in messages]


def list_contacts(db: Session, user: User) -> list[ContactThreadOut]:
    """
    Who `user` can chat with directly — every active branch for a
    supplier, every active supplier for a branch — most recent chat first,
    with an unread count each.
    """
    if user.supplier_id:
        others = [
            (b.id, b.branch_code, b.branch_name)
            for b in db.query(Branch).filter(Branch.status == "ACTIVE").order_by(Branch.branch_name).all()
        ]
        messages = (
            db.query(Message)
            .filter(Message.supplier_id == user.supplier_id, Message.branch_id.isnot(None))
            .order_by(Message.created_at, Message.id)
            .all()
        )
        key = lambda m: m.branch_id  # noqa: E731
        is_unread = lambda m: m.sender_role == "BRANCH" and m.read_by_supplier_at is None  # noqa: E731
    elif user.branch_id:
        others = [
            (s.id, s.supplier_code, s.supplier_name)
            for s in db.query(Supplier).filter(Supplier.status == "ACTIVE").order_by(Supplier.supplier_name).all()
        ]
        messages = (
            db.query(Message)
            .filter(Message.branch_id == user.branch_id, Message.supplier_id.isnot(None))
            .order_by(Message.created_at, Message.id)
            .all()
        )
        key = lambda m: m.supplier_id  # noqa: E731
        is_unread = lambda m: m.sender_role == "SUPPLIER" and m.read_by_branch_at is None  # noqa: E731
    else:
        raise PermissionDeniedError("Only supplier and branch accounts can chat with each other.")

    by_other: dict[int, list[Message]] = {}
    for m in messages:
        by_other.setdefault(key(m), []).append(m)

    threads = []
    for other_id, code, name in others:
        msgs = by_other.get(other_id, [])
        last = msgs[-1] if msgs else None
        threads.append(
            ContactThreadOut(
                id=other_id,
                code=code,
                name=name,
                last_message_body=last.body if last else None,
                last_message_at=last.created_at if last else None,
                unread_count=sum(1 for m in msgs if is_unread(m)),
            )
        )
    threads.sort(key=lambda t: t.last_message_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    threads.sort(key=lambda t: t.last_message_at is None)
    return threads


def list_pair_conversations(db: Session) -> list[PairConversationOut]:
    """Every supplier<->branch chat that has at least one message, most recent first — Admin's read-only view."""
    messages = db.query(Message).filter(_SUPPLIER_BRANCH).order_by(Message.created_at, Message.id).all()
    if not messages:
        return []
    by_pair: dict[tuple[int, int], list[Message]] = {}
    for m in messages:
        by_pair.setdefault((m.supplier_id, m.branch_id), []).append(m)
    suppliers = {
        s.id: s.supplier_name
        for s in db.query(Supplier).filter(Supplier.id.in_({k[0] for k in by_pair})).all()
    }
    branches = {
        b.id: b.branch_name
        for b in db.query(Branch).filter(Branch.id.in_({k[1] for k in by_pair})).all()
    }
    out = []
    for (supplier_id, branch_id), msgs in by_pair.items():
        last = msgs[-1]
        out.append(
            PairConversationOut(
                supplier_id=supplier_id,
                supplier_name=suppliers.get(supplier_id, "—"),
                branch_id=branch_id,
                branch_name=branches.get(branch_id, "—"),
                message_count=len(msgs),
                last_message_body=last.body,
                last_message_at=last.created_at,
                last_sender_role=last.sender_role,
            )
        )
    out.sort(key=lambda c: c.last_message_at, reverse=True)
    return out


def list_pair_for_admin(db: Session, supplier_id: int, branch_id: int) -> list[MessageOut]:
    """Admin reading one supplier<->branch chat. Doesn't mark anything read for either side."""
    _require_supplier_exists(db, supplier_id)
    _require_branch_exists(db, branch_id)
    messages = _pair_messages(db, supplier_id, branch_id)
    names = _usernames(db, messages)
    return [_to_out(m, names.get(m.sender_user_id, "—")) for m in messages]
