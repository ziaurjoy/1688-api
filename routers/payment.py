


from bson import ObjectId
from datetime import datetime
import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Query

from database import db
from utils import users as user_utils
from models import users as users_models
from models.subscription import SubscribeRequest
from models.payment import StripeSubscribePaymentRequest, SubscribePaymentRequest


router = APIRouter(prefix="/payment", tags=["payment"])



@router.post("/subscribe/create/")
async def create_subscription_payment(
    payload: SubscribePaymentRequest,
    current_user: Annotated[
        users_models.User,
        Depends(user_utils.get_current_active_user)
    ],
):
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




@router.post("/stripe/create/", response_model=dict)
async def create_stripe_subscription_payment(
    payload: StripeSubscribePaymentRequest,
    current_user: Annotated[users_models.User, Depends(user_utils.get_current_active_user)],
):
    """
    Create subscription invoice + payment record after Stripe webhook / frontend confirmation
    """
    user_id = ObjectId(current_user["_id"])

    # ────────────────────────────────────────────────
    # 1. Prevent duplicate transaction (very important!)
    # ────────────────────────────────────────────────
    existing = await db.payment_subscribe_invoices.find_one(
        {"transaction_id": payload.transaction_id},
        projection={"_id": 1}
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Payment with this transaction_id already exists"
        )

    now = datetime.utcnow()

    # ────────────────────────────────────────────────
    # 2. Prepare invoice document
    # ────────────────────────────────────────────────
    discount = payload.discounts or 0.0
    total = float(float(payload.amount) - discount)

    invoice = {
        "invoice_number": f"INV-{int(now.timestamp())}",
        "user_id": user_id,
        "package_id": payload.package_id,
        "price": float(payload.amount),
        "discount": discount,
        "total": total,
        "currency": payload.currency.upper(),
        "status": payload.status,
        "created_at": now,
        "updated_at": now,
    }

    # ────────────────────────────────────────────────
    # 3. Atomic insert → get invoice _id
    # ────────────────────────────────────────────────
    invoice_result = await db.subscription_invoices.insert_one(invoice)
    invoice_id = invoice_result.inserted_id

    # ────────────────────────────────────────────────
    # 4. Prepare payment document
    # ────────────────────────────────────────────────
    payment = {
        "user_id": user_id,
        "invoice_id": invoice_id,
        "package_id": payload.package_id,
        "amount": float(payload.amount),
        "currency": payload.currency.upper(),
        "payment_method": payload.payment_method,
        "transaction_id": payload.transaction_id,
        "status": payload.status,
        "created_at": now,
        "updated_at": now,
    }

    # ────────────────────────────────────────────────
    # 5. Insert payment record
    # ────────────────────────────────────────────────
    await db.payment_subscribe_invoices.insert_one(payment)

    features = await db.subscription_features.find_one(
        {"package_id": ObjectId(payload.package_id)}
    )

    # 3️⃣ Prepare user subscription document
    doc = {
        "user_id": user_id,
        "package_id": payload.package_id,
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

    # Optional: you could also create a combined response
    return {
        "status": "created",
        "invoice_id": str(invoice_id),
        "invoice_number": invoice["invoice_number"],
        "transaction_id": payload.transaction_id,
        "total_paid": total,
        "currency": payload.currency.upper()
    }




@router.get("/transaction/read/")
async def get_user_payments(
    current_user: Annotated[dict, Depends(user_utils.get_current_active_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    try:
        # Safely get the user_id
        user_id = ObjectId(current_user["_id"])
    except Exception:
        raise HTTPException(status_code=500, detail="Invalid User ID")

    skip = (page - 1) * limit
    query = {"user_id": user_id}

    # 1. Get total count
    total = await db.payment_subscribe_invoices.count_documents(query)

    # 2. Fetch documents
    cursor = db.payment_subscribe_invoices.find(query).sort("_id", -1).skip(skip).limit(limit)

    payment_data = []
    async for doc in cursor:
        # --- THE FIX STARTS HERE ---
        # Convert the main ID
        doc["id"] = str(doc.pop("_id"))

        package_id = doc.get("package_id")
        if package_id:
            package_data = await db.subscription_package.find_one({"_id": ObjectId(package_id)})
            if package_data:
                # Convert package ObjectIds to strings
                package_data["_id"] = str(package_data["_id"])
                # Append the package object to the invoice document
                doc["package"] = package_data

        # Convert any other ObjectIds found in the document keys
        for key, value in doc.items():
            if isinstance(value, ObjectId):
                doc[key] = str(value)
        # --- THE FIX ENDS HERE ---

        payment_data.append(doc)

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": math.ceil(total / limit) if limit > 0 else 0,
        "results": payment_data,
    }


@router.get("/transaction/details/{payment_id}")
async def get_user_payments_details(
    current_user: Annotated[dict, Depends(user_utils.get_current_active_user)],
    payment_id: str,
):
    try:
        # Safely get the user_id
        user_id = ObjectId(current_user["_id"])
    except Exception:
        raise HTTPException(status_code=500, detail="Invalid User ID")

    # Find the specific payment record by payment_id and user_id
    payment = await db.payment_subscribe_invoices.find_one({
        "_id": ObjectId(payment_id),
        "user_id": user_id
    })

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    # Convert the main ID
    payment["id"] = str(payment.pop("_id"))

    package_id = payment.get("package_id")
    if package_id:
        package_data = await db.subscription_package.find_one({"_id": ObjectId(package_id)})
        if package_data:
            # Convert package ObjectIds to strings
            package_data["_id"] = str(package_data["_id"])
            # Append the package object to the invoice document
            payment["package"] = package_data

    # Convert any other ObjectIds found in the document keys
    for key, value in payment.items():
        if isinstance(value, ObjectId):
            payment[key] = str(value)

    return {
        "result": payment,
    }