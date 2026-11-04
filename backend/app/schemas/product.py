from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class ProductOut(BaseModel):
    id: int
    product_code: str
    description: str
    category_name: str
    subcategory: str | None = None
    unit_code: str
    status: str
    # Imported items only: kg in one case of this product.
    case_kg: float | None = None

    class Config:
        from_attributes = True


class ProductAdminOut(ProductOut):
    """One row of the admin Product List — includes removed items."""
    pos_code: str | None = None
    category_id: int
    unit_id: int
    created_at: datetime | None = None
    # Changes whenever the photo is replaced; None = no photo yet.
    image_version: str | None = None


class ProductOption(BaseModel):
    id: int
    name: str


class ProductOptionsOut(BaseModel):
    categories: list[ProductOption]
    units: list[ProductOption]


class ProductCreate(BaseModel):
    product_code: str = Field(max_length=30)
    pos_code: str | None = Field(default=None, max_length=30)
    description: str = Field(max_length=200)
    category_id: int
    subcategory: str | None = Field(default=None, max_length=100)
    unit_id: int
    # Required for (and only kept on) Imported items: 1 case = case_kg kg.
    case_kg: float | None = Field(default=None, gt=0, le=10000)

    @field_validator("product_code", "description")
    @classmethod
    def required_text(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("This field is required.")
        return v

    @field_validator("pos_code", "subcategory")
    @classmethod
    def optional_text(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = " ".join(v.split())
        return v or None


class ProductUpdate(ProductCreate):
    """Admin's edit of an existing product — the same fields as adding one."""


class ProductImageRef(BaseModel):
    """
    One product's photo info for thumbnails: version is set (and changes
    on every replace) when Admin uploaded a photo; without one, pages fall
    back to the older photo file named by product_code, if there is one.
    """
    product_id: int
    product_code: str
    version: str | None = None
    # Imported items only: kg in one case, so every page can show
    # "case (12 kg)" next to the product.
    case_kg: float | None = None
