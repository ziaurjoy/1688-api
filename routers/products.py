import hashlib
from math import ceil

from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Query, HTTPException, Header, Request

from database import db
from models.products import Product

from scriping_files.scriping_pages import playwright_main
from scriping_files.details_scriping_page import playwright_main_details
from models.users import User
from utils import users as users_utils


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
    request: Request,
    searching: str | None = Query(None, description="Search keyword"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),

):

    user = await users_utils.fiend_credentials(request)

    skip = (page - 1) * limit

    query = {}
    if searching:
        query = {
            "$or": [
                # {"details.extract_product_title_and_cart.productTitle.title": {"$regex": searching, "$options": "i"}},
                # {"category": {"$regex": searching, "$options": "i"}},
                {"product_name": {"$regex": searching, "$options": "i"}},
            ]
        }

    total = await db.products.count_documents(query)



    await users_utils.count_api_hit('/products', user)


    if total == 0 and searching:
        try:
            await playwright_main(searching)
        except Exception as e:
            pass

        cursor = (db.products.find(query).skip(skip).limit(limit).sort("_id", -1))

        products = []
        async for product in cursor:
            product["_id"] = str(product["_id"])
            products.append(product)

        return {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": ceil(total / limit),
            "results": products,
        }

    cursor = (db.products.find(query).skip(skip).limit(limit).sort("_id", -1))

    products = []
    async for product in cursor:
        product["_id"] = str(product["_id"])
        products.append(product)

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "total_pages": ceil(total / limit),
        "results": products,
    }


@router.get("/{product_id}")
async def get_product(product_id):

    product = await db.products.find_one({"offer_id": product_id})
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    product_details = product.get("details", None)
    if product_details is None:
        product_id = product.get('offer_id')
        details_link = product.get('url')

        await playwright_main_details(details_link, product_id)
        product = await db.products.find_one({"offer_id": product_id})

        product["_id"] = str(product["_id"])
        return {"updated": True, "product": product}

    # Return updated document
    product["_id"] = str(product["_id"])
    return {"updated": True, "product": product}

