from pydantic import BaseModel, Field


class SettingsOut(BaseModel):
    branch_order_deadline: str
    supplier_price_deadline: str
    support_phone: str


class SettingUpdateRequest(BaseModel):
    value: str = Field(min_length=1, max_length=200)


class MasterDataEmailOut(BaseModel):
    # Kept off the public SettingsOut on purpose — an internal distribution
    # address, only ever read/written by Admin.
    master_data_email: str
