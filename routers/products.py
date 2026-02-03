from fastapi import APIRouter, Query
from math import ceil
from fastapi.encoders import jsonable_encoder
# from app.database import db
from database import db
from bson import ObjectId

from models.products import Product
from scriping_files.scriping_pages1 import playwright_main

router = APIRouter(prefix="/products", tags=["Products"])

@router.post("/")
async def create_product(product: Product):
    # Convert Pydantic model to a JSON-serializable dict that Mongo can store
    data = jsonable_encoder(product)

    # Insert is async with Motor, so await the result and return the new id
    result = await db.products.insert_one(data)
    return {"id": str(result.inserted_id)}



@router.get("/")
async def list_products(
    searching: str | None = Query(None, description="Search keyword"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
):
    skip = (page - 1) * limit

    query = {}
    if searching:
        query = {
            "$or": [
                # {"details.extract_product_title_and_cart.productTitle.title": {"$regex": searching, "$options": "i"}},
                # {"category": {"$regex": searching, "$options": "i"}},
                {"item": {"$regex": searching, "$options": "i"}},
            ]
        }

    total = await db.products.count_documents(query)

    cursor = (db.products.find(query).skip(skip).limit(limit).sort("_id", -1))

    products = []
    async for product in cursor:
        product["_id"] = str(product["_id"])
        products.append(product)

    if len(products) == 0:
        await playwright_main(searching)

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": ceil(total / limit),
        "results": products,
    }
