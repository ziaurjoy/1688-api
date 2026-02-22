


from bson import ObjectId
from datetime import datetime
import fastapi.encoders
import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query

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



@router.get("/subscription/read/")
async def get_user_invoices(
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
    total = await db.subscription_invoices.count_documents(query)

    # 2. Fetch documents
    cursor = db.subscription_invoices.find(query).sort("_id", -1).skip(skip).limit(limit)

    invoices = []
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

        invoices.append(doc)

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": math.ceil(total / limit) if limit > 0 else 0,
        "results": invoices,
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




from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from weasyprint import HTML
from io import BytesIO
from datetime import datetime
import jinja2


# app.mount("/static", StaticFiles(directory="static"), name="static")


templates = Jinja2Templates(directory="templates")




@router.get("/generate-invoice-pdf/{invoice_id}")
async def generate_invoice_pdf(
    invoice_id: str,
    current_user: Annotated[
        users_models.User,
        Depends(user_utils.get_current_active_user)
    ],
):
    try:
        user_id = ObjectId(current_user["_id"])
        invoice = await db.subscription_invoices.find_one(
            {"_id": ObjectId(invoice_id), "user_id": user_id}
        )
        user = await db.User.find_one({"_id": user_id})
        package_data = await db.subscription_package.find_one({"_id": ObjectId(invoice["package_id"])})

        html_content = templates.get_template("invoice.html").render(
            invoice=invoice,
            user=user,
            package_data=package_data
        )

        pdf_bytes = HTML(string=html_content).write_pdf()

        filename = f"invoice-{invoice['invoice_number']}.pdf"

        return StreamingResponse(
            BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")