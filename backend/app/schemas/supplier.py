from pydantic import BaseModel, Field


class SupplierOut(BaseModel):
    id: int
    supplier_code: str
    supplier_name: str
    contact_person: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    status: str

    class Config:
        from_attributes = True


class SupplierCreate(BaseModel):
    # If omitted, the next sequential code (SUP17, SUP18, ...) is
    # generated to match the existing SUP01..SUP16 convention from
    # seed_master_data.py — Admin can still override it if they want a
    # specific code.
    supplier_code: str | None = Field(default=None, max_length=20)
    supplier_name: str = Field(min_length=1, max_length=150)
    contact_person: str | None = Field(default=None, max_length=100)
    phone: str | None = Field(default=None, max_length=30)
    email: str | None = Field(default=None, max_length=120)
    address: str | None = None
