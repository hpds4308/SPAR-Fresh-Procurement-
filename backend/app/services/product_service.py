"""
Admin Product List — the whole fruit & veg catalogue, including items
that were removed. Removing a product never deletes the row: past orders,
prices and purchase orders still point at it. It is marked INACTIVE
instead, which already hides it from branch ordering, supplier price
sheets, the Master Data Sheet and everything else that lists ACTIVE
products. Restoring flips it back.

Admin can also edit a product (code, POS code, description, category,
unit) — nothing else keeps a copy of those, so the change shows on every
page straight away — and give it a 1080x1080 photo.
"""
import struct

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit import write_audit_log
from app.core.errors import ConflictError, NotFoundError, ValidationFailedError
from app.models.product import Product, ProductCategory, ProductImage, ProductUnit
from app.models.user import User
from app.schemas.product import (
    ProductAdminOut,
    ProductCreate,
    ProductImageRef,
    ProductOption,
    ProductOptionsOut,
    ProductUpdate,
)

ACTIVE = "ACTIVE"
INACTIVE = "INACTIVE"


def _out(
    p: Product, categories: dict[int, str], units: dict[int, str], image_versions: dict[int, str] | None = None
) -> ProductAdminOut:
    return ProductAdminOut(
        id=p.id,
        product_code=p.product_code,
        pos_code=p.pos_code,
        description=p.description,
        category_id=p.category_id,
        category_name=categories.get(p.category_id, "—"),
        subcategory=p.subcategory,
        unit_id=p.unit_id,
        unit_code=units.get(p.unit_id, "—"),
        status=p.status,
        created_at=p.created_at,
        image_version=(image_versions or {}).get(p.id),
    )


def _lookups(db: Session) -> tuple[dict[int, str], dict[int, str]]:
    categories = {c.id: c.name for c in db.query(ProductCategory).all()}
    units = {u.id: u.code for u in db.query(ProductUnit).all()}
    return categories, units


def list_all(db: Session) -> list[ProductAdminOut]:
    """Every product, active and removed, in the usual category/name order."""
    categories, units = _lookups(db)
    rows = db.query(Product).order_by(Product.category_id, Product.description).all()
    versions = _image_versions(db)
    return [_out(p, categories, units, versions) for p in rows]


def options(db: Session) -> ProductOptionsOut:
    return ProductOptionsOut(
        categories=[ProductOption(id=c.id, name=c.name) for c in db.query(ProductCategory).order_by(ProductCategory.id)],
        units=[ProductOption(id=u.id, name=u.code) for u in db.query(ProductUnit).order_by(ProductUnit.code)],
    )


def _check_choices(db: Session, payload: ProductCreate) -> None:
    if db.get(ProductCategory, payload.category_id) is None:
        raise ValidationFailedError("Choose a category.")
    if db.get(ProductUnit, payload.unit_id) is None:
        raise ValidationFailedError("Choose a unit.")


def create(db: Session, admin: User, payload: ProductCreate) -> ProductAdminOut:
    _check_choices(db, payload)

    clash = db.query(Product).filter(func.lower(Product.product_code) == payload.product_code.lower()).first()
    if clash:
        if clash.status != ACTIVE:
            raise ConflictError(
                f'Product code {payload.product_code} belongs to "{clash.description}", which was removed. '
                "Restore it from the list instead of adding it again."
            )
        raise ConflictError(f'Product code {payload.product_code} is already used by "{clash.description}".')

    row = Product(
        product_code=payload.product_code,
        pos_code=payload.pos_code,
        # Matches how the seed import flags items that came without a POS code.
        pos_code_flag=None if payload.pos_code else "MISSING",
        description=payload.description,
        category_id=payload.category_id,
        subcategory=payload.subcategory,
        unit_id=payload.unit_id,
        status=ACTIVE,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError(f"Product code {payload.product_code} is already used by another product.")
    db.refresh(row)

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="PRODUCT_CREATED",
        entity_type="product",
        entity_id=row.id,
        description=f'Product "{row.description}" ({row.product_code}) added.',
    )
    return _out(row, *_lookups(db))


def _get(db: Session, product_id: int) -> Product:
    row = db.get(Product, product_id)
    if row is None:
        raise NotFoundError("That product no longer exists.")
    return row


def _one_out(db: Session, row: Product) -> ProductAdminOut:
    return _out(row, *_lookups(db), _image_versions(db, row.id))


def update(db: Session, admin: User, product_id: int, payload: ProductUpdate) -> ProductAdminOut:
    """Edits a product in place; orders, prices and POs pick it up by id."""
    row = _get(db, product_id)
    _check_choices(db, payload)

    clash = (
        db.query(Product)
        .filter(func.lower(Product.product_code) == payload.product_code.lower(), Product.id != row.id)
        .first()
    )
    if clash:
        removed = " (a removed product)" if clash.status != ACTIVE else ""
        raise ConflictError(f'Product code {payload.product_code} is already used by "{clash.description}"{removed}.')

    before = f"{row.description} ({row.product_code})"
    row.product_code = payload.product_code
    if payload.pos_code != row.pos_code:
        row.pos_code = payload.pos_code
        row.pos_code_flag = None if payload.pos_code else "MISSING"
    row.description = payload.description
    row.category_id = payload.category_id
    row.subcategory = payload.subcategory
    row.unit_id = payload.unit_id
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ConflictError(f"Product code {payload.product_code} is already used by another product.")
    db.refresh(row)

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="PRODUCT_UPDATED",
        entity_type="product",
        entity_id=row.id,
        description=f'Product "{before}" edited — now "{row.description}" ({row.product_code}).',
    )
    return _one_out(db, row)


def _set_status(db: Session, admin: User, product_id: int, status: str) -> ProductAdminOut:
    row = _get(db, product_id)
    if row.status != status:
        row.status = status
        db.commit()
        db.refresh(row)
        removed = status == INACTIVE
        write_audit_log(
            db,
            user_id=admin.id,
            role="ADMIN",
            action="PRODUCT_REMOVED" if removed else "PRODUCT_RESTORED",
            entity_type="product",
            entity_id=row.id,
            description=f'Product "{row.description}" ({row.product_code}) {"removed" if removed else "restored"}.',
        )
    return _one_out(db, row)


def remove(db: Session, admin: User, product_id: int) -> ProductAdminOut:
    return _set_status(db, admin, product_id, INACTIVE)


def restore(db: Session, admin: User, product_id: int) -> ProductAdminOut:
    return _set_status(db, admin, product_id, ACTIVE)


# ---- Photos ----

IMAGE_SIZE = 1080  # photos must be exactly IMAGE_SIZE x IMAGE_SIZE
MAX_IMAGE_BYTES = 5 * 1024 * 1024
# The list thumbnail is drawn by the browser from the photo (the server
# has no image library); anything bigger than this isn't a thumbnail.
MAX_THUMB_BYTES = 200 * 1024
MAX_THUMB_SIZE = 400


def _version(updated_at) -> str:
    return str(int(updated_at.timestamp() * 1000)) if updated_at else "1"


def _image_versions(db: Session, product_id: int | None = None) -> dict[int, str]:
    q = db.query(ProductImage.product_id, ProductImage.updated_at)
    if product_id is not None:
        q = q.filter(ProductImage.product_id == product_id)
    return {pid: _version(at) for pid, at in q.all()}


def image_refs(db: Session) -> list[ProductImageRef]:
    """Every product's code and photo version, for every page that shows photos."""
    versions = _image_versions(db)
    return [
        ProductImageRef(product_id=pid, product_code=code, version=versions.get(pid))
        for pid, code in db.query(Product.id, Product.product_code).all()
    ]


def _image_type_and_size(data: bytes) -> tuple[str, int, int] | None:
    """(content type, width, height) read from a JPEG/PNG/WebP header, or None."""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24 and data[12:16] == b"IHDR":
        w, h = struct.unpack(">II", data[16:24])
        return "image/png", w, h
    if data.startswith(b"\xff\xd8"):
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                return None
            marker = data[i + 1]
            if marker == 0xFF:  # fill byte
                i += 1
                continue
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            (length,) = struct.unpack(">H", data[i + 2 : i + 4])
            # Start-of-frame markers carry the size (C4 DHT, C8 JPG, CC DAC don't).
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                return "image/jpeg", w, h
            i += 2 + length
        return None
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8X":
            w = 1 + int.from_bytes(data[24:27], "little")
            h = 1 + int.from_bytes(data[27:30], "little")
            return "image/webp", w, h
        if chunk == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            w, h = struct.unpack("<HH", data[26:30])
            return "image/webp", w & 0x3FFF, h & 0x3FFF
        if chunk == b"VP8L" and data[20] == 0x2F:
            b = int.from_bytes(data[21:25], "little")
            return "image/webp", (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
    return None


def set_image(db: Session, admin: User, product_id: int, data: bytes, thumb: bytes) -> ProductAdminOut:
    row = _get(db, product_id)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValidationFailedError("That photo is too large. Use one under 5 MB.")
    info = _image_type_and_size(data)
    if info is None:
        raise ValidationFailedError("That file isn't a photo. Use a JPG, PNG or WebP image.")
    content_type, w, h = info
    if (w, h) != (IMAGE_SIZE, IMAGE_SIZE):
        raise ValidationFailedError(
            f"The photo must be exactly {IMAGE_SIZE} x {IMAGE_SIZE} pixels (this one is {w} x {h})."
        )
    thumb_info = _image_type_and_size(thumb) if len(thumb) <= MAX_THUMB_BYTES else None
    if thumb_info is None or max(thumb_info[1], thumb_info[2]) > MAX_THUMB_SIZE:
        raise ValidationFailedError("Could not prepare the photo's thumbnail. Please try again.")

    img = db.get(ProductImage, row.id)
    if img is None:
        img = ProductImage(product_id=row.id)
        db.add(img)
    img.content_type = content_type
    img.data = data
    img.thumb_content_type = thumb_info[0]
    img.thumb = thumb
    img.size_bytes = len(data)
    img.uploaded_by = admin.id
    img.updated_at = func.now()  # set explicitly so a replaced photo always gets a new version
    db.commit()

    write_audit_log(
        db,
        user_id=admin.id,
        role="ADMIN",
        action="PRODUCT_IMAGE_SET",
        entity_type="product",
        entity_id=row.id,
        description=f'Photo uploaded for "{row.description}" ({row.product_code}).',
    )
    return _one_out(db, row)


def remove_image(db: Session, admin: User, product_id: int) -> ProductAdminOut:
    row = _get(db, product_id)
    img = db.get(ProductImage, row.id)
    if img is not None:
        db.delete(img)
        db.commit()
        write_audit_log(
            db,
            user_id=admin.id,
            role="ADMIN",
            action="PRODUCT_IMAGE_REMOVED",
            entity_type="product",
            entity_id=row.id,
            description=f'Photo removed from "{row.description}" ({row.product_code}).',
        )
    return _one_out(db, row)


def get_image(db: Session, product_id: int, thumb: bool) -> tuple[bytes, str]:
    img = db.get(ProductImage, product_id)
    if img is None:
        raise NotFoundError("This product has no photo.")
    return (img.thumb, img.thumb_content_type) if thumb else (img.data, img.content_type)
