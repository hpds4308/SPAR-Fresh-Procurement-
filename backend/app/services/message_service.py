"""
Chat between Admin and Supplier, between Admin and Branch, and directly
between a supplier and a branch.

One Admin thread per supplier (or per branch), shared by every Admin user
and every user of that supplier/branch; plus one thread per supplier +
branch pair. Sending and reading are both scoped through here so the API
layer never has to reason about who's allowed to see what — a supplier
user can only ever touch their own supplier_id's threads, a branch user
only their own branch_id's; Admin can touch any Admin thread and read
(but not post in) every supplier<->branch thread. Admin is notified of
supplier<->branch messages too (unread badge), and opening one of those
chats marks it read for Admin only.
"""
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, PermissionDeniedError, ValidationFailedError
from app.core.security import get_user_roles
from app.models.branch import Branch
from app.models.message import Message, MessageAttachment
from app.models.supplier import Supplier
from app.models.user import User
from app.services import notification_service
from app.schemas.message import (
    AttachmentOut,
    BranchThreadOut,
    ContactThreadOut,
    MessageOut,
    PairConversationOut,
    SupplierThreadOut,
    UnreadCountOut,
)

# Which thread a message belongs to (see models/message.py).
_ADMIN_SUPPLIER = Message.branch_id.is_(None)
_ADMIN_BRANCH = Message.supplier_id.is_(None)
_SUPPLIER_BRANCH = and_(Message.supplier_id.isnot(None), Message.branch_id.isnot(None))


def _to_out(msg: Message, username: str, attachments: list[MessageAttachment] | None = None) -> MessageOut:
    return MessageOut(
        id=msg.id,
        supplier_id=msg.supplier_id,
        branch_id=msg.branch_id,
        sender_role=msg.sender_role,
        sender_username=username,
        body=msg.body,
        created_at=msg.created_at,
        attachments=[_attachment_out(a) for a in attachments or []],
    )


def _preview(msg: Message) -> str:
    """What a conversation list shows for its last message."""
    return msg.body or "📎 Attachment"


def _many_out(db: Session, messages: list[Message]) -> list[MessageOut]:
    names = _usernames(db, messages)
    by_message: dict[int, list[MessageAttachment]] = {}
    if messages:
        for a in (
            db.query(MessageAttachment)
            .filter(MessageAttachment.message_id.in_([m.id for m in messages]))
            .order_by(MessageAttachment.id)
        ):
            by_message.setdefault(a.message_id, []).append(a)
    return [_to_out(m, names.get(m.sender_user_id, "—"), by_message.get(m.id)) for m in messages]


def _save(db: Session, msg: Message, sender: User, attachment_ids: list[int] | None) -> MessageOut:
    """Saves a new message with the sender's uploaded attachments linked to it."""
    if not msg.body.strip() and not attachment_ids:
        raise ValidationFailedError("Write a message or attach a file.")
    db.add(msg)
    db.flush()
    attachments = _claim_attachments(db, sender, msg, attachment_ids or [])
    db.commit()
    db.refresh(msg)
    notification_service.on_message(db, msg, len(attachments))
    return _to_out(msg, sender.username, attachments)


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


def send_as_admin(db: Session, admin: User, supplier_id: int, body: str, attachment_ids: list[int] | None = None) -> MessageOut:
    _require_supplier_exists(db, supplier_id)
    msg = Message(
        supplier_id=supplier_id,
        sender_role="ADMIN",
        sender_user_id=admin.id,
        body=body,
        # Admin sent it, so it's implicitly "read" on the admin side already.
        read_by_admin_at=datetime.now(timezone.utc),
    )
    return _save(db, msg, admin, attachment_ids)


def send_as_admin_to_branch(db: Session, admin: User, branch_id: int, body: str, attachment_ids: list[int] | None = None) -> MessageOut:
    _require_branch_exists(db, branch_id)
    msg = Message(
        branch_id=branch_id,
        sender_role="ADMIN",
        sender_user_id=admin.id,
        body=body,
        read_by_admin_at=datetime.now(timezone.utc),
    )
    return _save(db, msg, admin, attachment_ids)


def send_as_supplier(db: Session, supplier_user: User, body: str, attachment_ids: list[int] | None = None) -> MessageOut:
    if not supplier_user.supplier_id:
        raise PermissionDeniedError("Only supplier accounts can send messages here.")
    msg = Message(
        supplier_id=supplier_user.supplier_id,
        sender_role="SUPPLIER",
        sender_user_id=supplier_user.id,
        body=body,
        read_by_supplier_at=datetime.now(timezone.utc),
    )
    return _save(db, msg, supplier_user, attachment_ids)


def send_as_branch(db: Session, branch_user: User, body: str, attachment_ids: list[int] | None = None) -> MessageOut:
    if not branch_user.branch_id:
        raise PermissionDeniedError("Only branch accounts can send messages here.")
    msg = Message(
        branch_id=branch_user.branch_id,
        sender_role="BRANCH",
        sender_user_id=branch_user.id,
        body=body,
        read_by_branch_at=datetime.now(timezone.utc),
    )
    return _save(db, msg, branch_user, attachment_ids)


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
    return _many_out(db, messages)


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
    return _many_out(db, messages)


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
    return _many_out(db, messages)


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
    return _many_out(db, messages)


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
                last_message_body=_preview(last) if last else None,
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
                last_message_body=_preview(last) if last else None,
                last_message_at=last.created_at if last else None,
                unread_count=unread,
            )
        )
    threads.sort(key=lambda t: t.branch_name)
    threads.sort(key=lambda t: t.last_message_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    threads.sort(key=lambda t: t.last_message_at is None)
    return threads


def admin_unread_count(db: Session) -> UnreadCountOut:
    """
    Messages Admin hasn't read yet — in their own supplier and branch
    threads, and in supplier<->branch chats (Admin is notified of those
    too). `count` is the one total badge; the rest split it per Messages
    tab, plus who wrote the newest unread supplier<->branch message.
    """
    unread = (
        db.query(Message)
        .filter(Message.sender_role.in_(["SUPPLIER", "BRANCH"]), Message.read_by_admin_at.is_(None))
        .order_by(Message.created_at.desc(), Message.id.desc())
        .all()
    )
    suppliers = sum(1 for m in unread if m.branch_id is None)
    branches = sum(1 for m in unread if m.supplier_id is None)
    pair = [m for m in unread if m.supplier_id is not None and m.branch_id is not None]
    latest = None
    if pair:
        m = pair[0]
        supplier = db.get(Supplier, m.supplier_id)
        branch = db.get(Branch, m.branch_id)
        s_name = supplier.supplier_name if supplier else "Supplier"
        b_name = branch.branch_name if branch else "Branch"
        latest = f"{s_name} → {b_name}" if m.sender_role == "SUPPLIER" else f"{b_name} → {s_name}"
    return UnreadCountOut(
        count=len(unread),
        suppliers=suppliers,
        branches=branches,
        supplier_branch=len(pair),
        latest_supplier_branch=latest,
        latest_supplier_branch_id=pair[0].id if pair else None,
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


def send_to_peer(db: Session, user: User, other_id: int, body: str, attachment_ids: list[int] | None = None) -> MessageOut:
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
    return _save(db, msg, user, attachment_ids)


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
    return _many_out(db, messages)


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
                last_message_body=_preview(last) if last else None,
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
                unread_count=sum(1 for m in msgs if m.read_by_admin_at is None),
                supplier_id=supplier_id,
                supplier_name=suppliers.get(supplier_id, "—"),
                branch_id=branch_id,
                branch_name=branches.get(branch_id, "—"),
                message_count=len(msgs),
                last_message_body=_preview(last),
                last_message_at=last.created_at,
                last_sender_role=last.sender_role,
            )
        )
    out.sort(key=lambda c: c.last_message_at, reverse=True)
    return out


def list_pair_for_admin(db: Session, supplier_id: int, branch_id: int, mark_read: bool = True) -> list[MessageOut]:
    """
    Admin reading one supplier<->branch chat. Marks it read for Admin only
    — never for the supplier or the branch.
    """
    _require_supplier_exists(db, supplier_id)
    _require_branch_exists(db, branch_id)
    messages = _pair_messages(db, supplier_id, branch_id)
    if mark_read:
        unread = [m for m in messages if m.read_by_admin_at is None]
        if unread:
            now = datetime.now(timezone.utc)
            for m in unread:
                m.read_by_admin_at = now
            db.commit()
    return _many_out(db, messages)


# ---- Attachments ----

# Extension -> (served content type, magic-byte prefixes it must start with;
# None = any content). The browser's own content type is never trusted.
_OLE = (b"\xd0\xcf\x11\xe0",)
_ZIP = (b"PK\x03\x04",)
ALLOWED_TYPES: dict[str, tuple[str, tuple[bytes, ...] | None]] = {
    ".jpg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".jpeg": ("image/jpeg", (b"\xff\xd8\xff",)),
    ".png": ("image/png", (b"\x89PNG\r\n\x1a\n",)),
    ".gif": ("image/gif", (b"GIF87a", b"GIF89a")),
    ".webp": ("image/webp", (b"RIFF",)),
    ".pdf": ("application/pdf", (b"%PDF",)),
    ".doc": ("application/msword", _OLE),
    ".xls": ("application/vnd.ms-excel", _OLE),
    ".ppt": ("application/vnd.ms-powerpoint", _OLE),
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", _ZIP),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", _ZIP),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", _ZIP),
    ".csv": ("text/csv", None),
    ".txt": ("text/plain", None),
}
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_ATTACHMENTS_PER_MESSAGE = 5
# The database volume is small (Railway trial: ~430 MB in all), so chat
# files stop being accepted well before they could fill it and take the
# whole app down with them.
MAX_TOTAL_ATTACHMENT_BYTES = 200 * 1024 * 1024
# An upload that's never sent with a message is cleaned up after this.
PENDING_TTL = timedelta(hours=24)


def _attachment_out(a: MessageAttachment) -> AttachmentOut:
    return AttachmentOut(id=a.id, filename=a.filename, content_type=a.content_type, size_bytes=a.size_bytes)


def _clean_filename(name: str) -> str:
    name = (name or "").replace("\\", "/").split("/")[-1]
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '<>:"|?*').strip()
    return (name or "file")[-200:]


def upload_attachment(db: Session, user: User, filename: str, data: bytes) -> AttachmentOut:
    """Stores one file for a message the user is about to send."""
    filename = _clean_filename(filename)
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext not in ALLOWED_TYPES:
        raise ValidationFailedError(
            "That type of file can't be attached. Use a photo (JPG, PNG, GIF, WEBP), PDF, Word, Excel, "
            "PowerPoint, CSV or text file."
        )
    if not data:
        raise ValidationFailedError(f"{filename} is empty.")
    if len(data) > MAX_ATTACHMENT_BYTES:
        raise ValidationFailedError(f"{filename} is too large — files can be up to 5 MB.")
    content_type, magic = ALLOWED_TYPES[ext]
    if magic and not any(data.startswith(m) for m in magic):
        raise ValidationFailedError(f"{filename} doesn't look like a real {ext[1:].upper()} file.")
    if ext == ".webp" and data[8:12] != b"WEBP":
        raise ValidationFailedError(f"{filename} doesn't look like a real WEBP file.")

    # Uploads that were never sent with a message.
    db.query(MessageAttachment).filter(
        MessageAttachment.message_id.is_(None),
        MessageAttachment.created_at < datetime.now(timezone.utc) - PENDING_TTL,
    ).delete(synchronize_session=False)

    used = db.query(func.coalesce(func.sum(MessageAttachment.size_bytes), 0)).scalar() or 0
    if used + len(data) > MAX_TOTAL_ATTACHMENT_BYTES:
        raise ValidationFailedError(
            "Chat file storage is full, so new files can't be attached right now. Please tell SPAR Admin."
        )

    attachment = MessageAttachment(
        uploaded_by=user.id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(data),
        data=data,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return _attachment_out(attachment)


def _claim_attachments(db: Session, sender: User, msg: Message, attachment_ids: list[int]) -> list[MessageAttachment]:
    """Links the sender's own not-yet-sent uploads to `msg`. Caller commits."""
    ids = list(dict.fromkeys(attachment_ids))
    if not ids:
        return []
    if len(ids) > MAX_ATTACHMENTS_PER_MESSAGE:
        raise ValidationFailedError(f"A message can have up to {MAX_ATTACHMENTS_PER_MESSAGE} attachments.")
    found = (
        db.query(MessageAttachment)
        .filter(
            MessageAttachment.id.in_(ids),
            MessageAttachment.uploaded_by == sender.id,
            MessageAttachment.message_id.is_(None),
        )
        .all()
    )
    if len(found) != len(ids):
        raise ValidationFailedError("One of the attachments wasn't found — attach it again.")
    for a in found:
        a.message_id = msg.id
    return sorted(found, key=lambda a: a.id)


def _can_see(db: Session, user: User, msg: Message) -> bool:
    if "ADMIN" in get_user_roles(db, user.id):
        return True
    if user.supplier_id:
        return msg.supplier_id == user.supplier_id
    if user.branch_id:
        return msg.branch_id == user.branch_id
    return False


def get_attachment(db: Session, user: User, attachment_id: int) -> MessageAttachment:
    """The file, if `user` can see the message it's on (or uploaded it and hasn't sent it yet)."""
    a = db.get(MessageAttachment, attachment_id)
    if a is not None:
        if a.message_id is None:
            allowed = a.uploaded_by == user.id
        else:
            msg = db.get(Message, a.message_id)
            allowed = msg is not None and _can_see(db, user, msg)
        if allowed:
            return a
    # Someone else's file looks exactly like a missing one.
    raise NotFoundError("That attachment was not found.")


def content_disposition(a: MessageAttachment) -> str:
    """Photos and PDFs open in the browser; anything else downloads."""
    kind = "inline" if a.content_type.startswith("image/") or a.content_type == "application/pdf" else "attachment"
    ascii_name = a.filename.encode("ascii", "ignore").decode() or "file"
    ascii_name = ascii_name.replace('"', "")
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(a.filename)}"
