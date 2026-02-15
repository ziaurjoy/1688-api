


from bson import ObjectId
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from database import db
from utils import users as user_utils
from models import users as users_models
from models.subscription import SubscribeRequest


router = APIRouter(prefix="/subscription", tags=["subscription"])



@router.post("/user/")
async def subscribe_user(
    payload: SubscribeRequest,
    current_user: Annotated[
        users_models.User,
        Depends(user_utils.get_current_active_user)
    ],
):
    user_id = ObjectId(current_user["_id"])
    package_object_id = ObjectId(payload.package_id)

    # 1️⃣ Check if package exists
    package = await db.subscription_package.find_one(
        {"_id": package_object_id}
    )

    if not package:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription package not found"
        )

    # 2️⃣ Get package features
    features = await db.subscription_features.find_one(
        {"package_id": package_object_id}
    )

    if not features:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription features not found"
        )

    # 3️⃣ Prepare user subscription document
    doc = {
        "user_id": user_id,
        "package_id": package_object_id,
        "product_query_limit": features.get("product_query_limit", 0),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    # 4️⃣ Upsert (one subscription per user)
    await db.user_subscription.update_one(
        {"user_id": user_id},
        {"$set": doc},
        upsert=True
    )

    return {
        "message": "Subscription activated successfully",
        "product_query_limit": doc["product_query_limit"]
    }



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
