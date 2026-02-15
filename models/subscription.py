from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


from enum import Enum

from models.users import ReadOnlyUser
from utils.object_id import PyObjectId
from bson import ObjectId


class VisibilityEnum(str, Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"


class TypeEnum(str, Enum):
    BASIC = "BASIC"
    PREMIUM = "PREMIUM"
    ENTERPRISE = "ENTERPRISE"

class SubscriptionPackageID(BaseModel):
    _id: str


class SubscribeRequest(BaseModel):
    package_id: str


class SubscriptionPackage(BaseModel):
    title: str = Field(..., max_length=500)
    description: Optional[str] = Field(None, max_length=500)

    type: Optional[TypeEnum] = None
    price: int
    discount: Optional[int] = None

    enabled_trial: bool = True
    validity_days: int

    trial_days: int = 7

    is_active: bool = False

    visibility: VisibilityEnum = VisibilityEnum.PUBLIC


class SubscriptionFeatures(BaseModel):

    # One-to-One reference
    package_id: PyObjectId = Field(...)

    # --- Numeric Limits ---
    product_query_limit: int = 0

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class UserSubscriptionFeaturesBase(BaseModel):

    # ---- Relations (store ObjectId reference) ----
    user: str
    # --- Numeric Limits ---
    product_query_limit: int = 0
    is_blocked: bool = False