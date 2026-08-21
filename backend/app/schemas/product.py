from pydantic import BaseModel


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
