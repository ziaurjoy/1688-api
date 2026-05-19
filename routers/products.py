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



# @router.get("/")
# async def list_products(
#     request: Request,
#     searching: str | None = Query(None, description="Search keyword"),
#     page: int = Query(1, ge=1),
#     limit: int = Query(10, ge=1, le=100),

# ):

#     user = await users_utils.find_credentials(request)

#     skip = (page - 1) * limit

#     query = {}
#     if searching:
#         query = {
#             "$or": [
#                 # {"details.extract_product_title_and_cart.productTitle.title": {"$regex": searching, "$options": "i"}},
#                 # {"category": {"$regex": searching, "$options": "i"}},
#                 {"product_name": {"$regex": searching, "$options": "i"}},
#             ]
#         }

#     total = await db.products.count_documents(query)



#     await users_utils.count_api_hit('/products', user)


#     if total == 0 and searching:
#         try:
#             await playwright_main(searching, request)
#         except Exception as e:
#             pass

#         cursor = (db.products.find(query).skip(skip).limit(limit).sort("_id", -1))

#         products = []
#         async for product in cursor:
#             product["_id"] = str(product["_id"])



#             products.append(product)

#         return {
#             "page": page,
#             "limit": limit,
#             "total": total,
#             "total_pages": ceil(total / limit),
#             "results": products,
#         }

#     cursor = (db.products.find(query).skip(skip).limit(limit).sort("_id", -1))

#     products = []
#     async for product in cursor:

#         # if not product.get("image", None).startswith("http"):
#         #     product["image"] = 'http://localhost:8001/assets/images/' + product["image"]
#         image = product.get("image")

#         product["image"] = (
#             f"{request.base_url}{image}"
#             if image and image.startswith("assets")
#             else image.replace("http://localhost:8001", "http://192.168.68.118:8001")
#             if image
#             else None
#         )

#         product["_id"] = str(product["_id"])
#         products.append(product)

#     return {
#         "page": page,
#         "limit": limit,
#         "total": total,
#         "total_pages": ceil(total / limit),
#         "results": products,
#     }



from math import ceil
from fastapi import APIRouter, Query, Request
from enum import Enum

class SortOption(str, Enum):
    price_low  = "price-low"
    price_high = "price-high"
    rating     = "rating"
    newest     = "newest"


from pydantic import BaseModel

class AttributeWithValues(BaseModel):
    attribute_name: str
    values: list[str]


class CategoryAttributesResponse(BaseModel):
    category_name: str
    attributes: list[AttributeWithValues]


@router.get("/")
async def list_products(
    request: Request,
    searching:  str | None   = Query(None),
    category:   str | None   = Query(None),
    min_price:  float | None = Query(None, ge=0),
    max_price:  float | None = Query(None, ge=0),
    discount:   bool | None  = Query(None),      # true → promotion != null
    sort:       SortOption   = Query(SortOption.newest),
    page:       int          = Query(1, ge=1),
    limit:      int          = Query(10, ge=1, le=100),
):
    user = await users_utils.find_credentials(request)
    skip = (page - 1) * limit

    # ── Build query ────────────────────────────────────────────────
    query = {}

    if searching:
        query["$or"] = [
            {"product_name": {"$regex": searching, "$options": "i"}},
            {"title":        {"$regex": searching, "$options": "i"}},
        ]

    if category:
        query["category"] = category

    # price.amount is stored as a string (e.g. "13"), so cast at query time
    # If you can store it as a number this becomes simpler — but this works as-is.
    # price_filter = {}
    # if min_price is not None:
    #     price_filter["$gte"] = str(int(min_price))   # string comparison
    # if max_price is not None:
    #     price_filter["$lte"] = str(int(max_price))
    # if price_filter:
    #     query["price.amount"] = price_filter

    # if discount is True:
    #     query["promotion"] = {"$ne": None}

    # AFTER (correct — numeric comparison on combined float field)
    price_filter = {}
    if min_price is not None:
        price_filter["$gte"] = min_price        # already a float from FastAPI Query()
    if max_price is not None:
        price_filter["$lte"] = max_price
    if price_filter:
        query["price_float"] = price_filter     # query the new numeric field

    # ── Sort ───────────────────────────────────────────────────────
    # sort_map = {
    #     SortOption.price_low:  [("price.amount",  1)],
    #     SortOption.price_high: [("price.amount", -1)],
    #     SortOption.rating:     [("rating",        -1)],
    #     SortOption.newest:     [("_id",           -1)],
    # }

    sort_map = {
        SortOption.price_low:  [("price_float",  1)],   # was "price.amount"
        SortOption.price_high: [("price_float", -1)],   # was "price.amount"
        SortOption.rating:     [("rating",       -1)],
        SortOption.newest:     [("_id",          -1)],
    }

    mongo_sort = sort_map[sort]

    # ── Count + fetch ─────────────────────────────────────────────
    total = await db.products.count_documents(query)

    await users_utils.count_api_hit('/products', user)

    if total == 0 and searching:
        try:
            await playwright_main(searching, request)
        except Exception:
            pass

    cursor = db.products.find(query).skip(skip).limit(limit).sort(mongo_sort)

    products = []
    async for product in cursor:
        image = product.get("image")
        product["image"] = (
            f"{request.base_url}{image}"
            if image and image.startswith("assets")
            else image.replace("http://localhost:8001", "http://192.168.68.118:8001")
            if image
            else None
        )
        product["_id"] = str(product["_id"])
        products.append(product)

        import re

        # searching = "Fashion Accessories & Jewelry"
        if searching:


            search_words = [word for word in re.split(r'[\s&,]+', searching) if len(word) > 2]
            pattern = '|'.join(re.escape(word) for word in search_words)

            # Query MongoDB with case-insensitive regex on the keys
            categories_doc = await db.attribute_value.find_one({})
            print('======categories_doc', categories_doc)

            matched = None
            if categories_doc:
                for key in categories_doc:
                    if re.search(pattern, key, re.IGNORECASE):
                        matched = categories_doc[key]
                        break

            # categories_doc = await db.attribute_value.find_one({})
            # print('======categories_doc', categories_doc)
            # matched = categories_doc.get(searching) if categories_doc else None


            # if not matched:
            #     lower = searching.lower()
            #     if categories_doc:
            #         for key, value in categories_doc.items():
            #             if key != '_id' and key.lower() == lower:
            #                 matched = value
            #                 searching = key
            #                 break

            # if not matched:
            #     available_categories = [
            #         key for key in categories_doc.keys() if key != '_id'
            #     ] if categories_doc else []
            #     raise HTTPException(
            #         status_code=404,
            #         detail={
            #             "message": f"Category '{searching}' not found.",
            #             "available_categories": available_categories,
            #         },
            #     )
            if matched:
                filter = CategoryAttributesResponse(
                    category_name=searching,
                    attributes=[
                        AttributeWithValues(attribute_name=attr, values=vals)
                        for attr, vals in matched.items()
                    ],
                )
                print('======filter', filter)


    return {
        "page":        page,
        "limit":       limit,
        "total":       total,
        "total_pages": ceil(total / limit),
        "results":     products,
        "filters": filter.dict() if searching and matched else None,  # include filter info only if searching
    }


@router.get("/{product_id}")
async def get_product(request: Request, product_id: str):

    await users_utils.find_credentials(request)

    product = await db.products.find_one({"offer_id": product_id})
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")
    product_details = product.get("details", None)
    if product_details is None:
        product_id = product.get('offer_id')
        details_link = product.get('url')

        await playwright_main_details(details_link, product_id, request)
        product = await db.products.find_one({"offer_id": product_id})

        product["_id"] = str(product["_id"])
        return {"updated": True, "product": product}

    # Return updated document
    product["_id"] = str(product["_id"])
    return {"updated": True, "product": product}





@router.get("/category")
async def products_category(request: Request):

    user = await users_utils.find_credentials(request)

    categories = await db.categories.find().to_list(length=None)

    return {
        "categories": categories
    }