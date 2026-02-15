import os
import sys

# Ensure project root is on sys.path so local packages like `routers` import reliably
BASE_DIR = os.path.dirname(__file__)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI
from routers.products import router as product_router
from routers.users import router as users_router
from routers.subscription import router as subscription_router
app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware


origins = [
    "http://192.168.68.118:3000",
    "http://localhost",
    "http://localhost:8080",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(product_router)
app.include_router(users_router)
app.include_router(subscription_router)

# @app.get("/")
# async def root():
#     return {"message": "Hello World"}














