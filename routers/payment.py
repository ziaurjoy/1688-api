


from bson import ObjectId
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from database import db
from utils import users as user_utils
from models import users as users_models
from models.subscription import SubscribeRequest
from models.payment import SubscribePaymentRequest


router = APIRouter(prefix="/payment", tags=["payment"])



@router.post("/subscribe/create/")
async def create_subscription_payment(
    payload: SubscribePaymentRequest,
    current_user: Annotated[
        users_models.User,
        Depends(user_utils.get_current_active_user)
    ],
):
    print('payload==', payload.invoice_id)
    user_id = ObjectId(current_user["_id"])
    invoice_object_id = payload.invoice_id

    invoice = await db.subscription_invoices.find_one(
        {"invoice_number": invoice_object_id}
    )

    if not invoice:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found"
        )

    amount = float(invoice.get("total", 0))
    package_id = ObjectId(invoice.get("package_id", 0))

    invoice = {
        "user_id": user_id,
        "invoice_id": invoice_object_id,
        "package_id": package_id,
        "amount": amount,
        "currency": "BDT",
        "payment_method": 'Bkash',
        "transaction_id": "transaction_id",
        "status": "pending",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db.payment_subscribe_invoices.insert_one(invoice)

    # 🔥 Fetch inserted document
    payment_subscribe_invoice = await db.payment_subscribe_invoices.find_one(
        {"_id": result.inserted_id}
    )

    # Convert ObjectId to string
    payment_subscribe_invoice["_id"] = str(payment_subscribe_invoice["_id"])
    payment_subscribe_invoice["user_id"] = str(payment_subscribe_invoice["user_id"])
    payment_subscribe_invoice["package_id"] = str(payment_subscribe_invoice["package_id"])
    payment_subscribe_invoice["status"] = str(payment_subscribe_invoice["status"])

    return payment_subscribe_invoice


@router.get("/user/features/")
async def get_user_features(
    current_user: Annotated[
        users_models.User,
        Depends(user_utils.get_current_active_user)
    ],
):
    user_id = ObjectId(current_user["_id"])

    subscription = await db.user_subscription.find_one(
        {"user_id": user_id}
    )

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User subscription not found"
        )

    subscription["_id"] = str(subscription["_id"])
    subscription["user_id"] = str(subscription["user_id"])
    subscription["package_id"] = str(subscription["package_id"])

    return subscription



@router.get("/packages/")
async def get_packages_with_features():
    """
    Returns all subscription packages along with their features.
    """

    packages_cursor = db.subscription_package.find({})
    packages = await packages_cursor.to_list(length=None)

    result = []

    for package in packages:
        package_id = package["_id"]

        features = await db.subscription_features.find_one({"package_id": package_id})

        # Convert ObjectIds to strings for JSON serialization
        package["_id"] = str(package["_id"])
        features_dict = {}
        if features:
            features_dict = {k: v for k, v in features.items() if k not in ["_id", "package_id"]}
            features_dict["package_id"] = str(features["package_id"])
            features_dict["_id"] = str(features["_id"])

        result.append({
            "package": package,
            "features": features_dict
        })

    return result
