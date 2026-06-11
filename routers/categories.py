import hashlib
from math import ceil

from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Query, HTTPException, Header, Request
from bson import ObjectId

from database import db
from models.products import Product

from scriping_files.scriping_pages import playwright_main

from models.users import User
from utils import users as users_utils


router = APIRouter(prefix="/categories", tags=["Categories"])


def convert_objectid(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, dict):
        return {k: convert_objectid(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_objectid(item) for item in obj]
    else:
        return obj


@router.get("/")
async def get_categories(request: Request):

    user = await users_utils.find_credentials(request)

    categories = await db.categories.find().to_list(length=None)
    # print('---categories', categories)
    categories = convert_objectid(categories)
    return categories[0] if categories else {}
