from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal
from datetime import datetime
from bson import ObjectId
from utils.object_id import PyObjectId


class PaymentStatus(str):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"

class SubscribePaymentRequest(BaseModel):
    invoice_id: str


class PackageSubscribePayment(BaseModel):
    id: Optional[str] = Field(alias="_id")

    user_id: PyObjectId = Field(...)
    invoice_id: PyObjectId = Field(...)
    package_id: PyObjectId = Field(...)

    amount: Decimal
    currency: str = "USD"

    payment_method: Optional[str] = None
    transaction_id: Optional[str] = None

    status: str = PaymentStatus.PENDING

    gateway_response: Optional[dict] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
