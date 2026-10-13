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

    class Config:
        from_attributes = True


class ProductAdminOut(ProductOut):
    """One row of the admin Product List — includes removed items."""
    pos_code: str | None = None
    category_id: int
    unit_id: int
    created_at: datetime | None = None


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
