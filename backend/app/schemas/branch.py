from pydantic import BaseModel, Field


class BranchOut(BaseModel):
    id: int
    branch_code: str
    branch_name: str
    location: str | None = None
    status: str

    class Config:
        from_attributes = True


class BranchCreate(BaseModel):
    # If omitted, the next sequential code (BR14, BR15, ...) is generated
    # to match the existing BR01..BR13 convention from seed_master_data.py
    # — Admin can still override it if they want a specific code.
    branch_code: str | None = Field(default=None, max_length=20)
    branch_name: str = Field(min_length=1, max_length=100)
    location: str | None = Field(default=None, max_length=200)
