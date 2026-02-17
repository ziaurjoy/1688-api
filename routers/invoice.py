


from bson import ObjectId
from datetime import datetime
import fastapi.encoders
from typing import Annotated
from fastapi.encoders import jsonable_encoder

from fastapi import APIRouter, Depends, HTTPException, status

from database import db
from models.invoice import SubscribeInvoiceRequest
from utils import users as user_utils
from models import users as users_models
from models.invoice import SubscribeInvoiceRequest


router = APIRouter(prefix="/invoice", tags=["invoice"])



@router.post("/subscription/create/")
async def create_invoice(
    payload: SubscribeInvoiceRequest,
    current_user: Annotated[
        users_models.User,
        Depends(user_utils.get_current_active_user)
    ],
):
    user_id = ObjectId(current_user["_id"])
    package_object_id = ObjectId(payload.package_id)

    subscription = await db.subscription_package.find_one(
        {"_id": package_object_id}
    )

    if not subscription:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription package not found"
        )

    price = float(subscription["price"])
    discount = float(subscription.get("discount", 0))
    total = price - discount

    invoice = {
        "invoice_number": f"INV-{int(datetime.utcnow().timestamp())}",
        "user_id": user_id,
        "package_id": package_object_id,
        "price": price,
        "discount": discount,
        "total": total,
        "currency": "BDT",
        "status": "draft",
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = await db.subscription_invoices.insert_one(invoice)

    # 🔥 Fetch inserted document
    created_invoice = await db.subscription_invoices.find_one(
        {"_id": result.inserted_id}
    )

    # Convert ObjectId to string
    created_invoice["_id"] = str(created_invoice["_id"])
    created_invoice["user_id"] = str(created_invoice["user_id"])
    created_invoice["package_id"] = str(created_invoice["package_id"])

    return created_invoice



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
