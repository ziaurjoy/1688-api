import os
import sys

# Ensure project root is on sys.path so local packages like `routers` import reliably
BASE_DIR = os.path.dirname(__file__)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI
from routers.products import router as product_router
app = FastAPI()

app.include_router(product_router)

# @app.get("/")
# async def root():
#     return {"message": "Hello World"}