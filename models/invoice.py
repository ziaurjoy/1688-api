
from typing import List

from pydantic import BaseModel, Field
from typing import Optional
from decimal import Decimal
from datetime import datetime
from bson import ObjectId

class PackageSubscriptionInvoiceStatus(str):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    VOID = "void"

class SubscribeInvoiceRequest(BaseModel):
    package_id: str


class PackageSubscriptionInvoice(BaseModel):

    invoice_number: str
    user_id: str
    package_id: str

    # items: List[InvoiceItem]

    subtotal: Decimal
    tax: Decimal = 0
    discount: Decimal = 0
    total: Decimal

    currency: str = "USD"

    status: str = PackageSubscriptionInvoiceStatus.DRAFT

    paid_at: Optional[datetime] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
