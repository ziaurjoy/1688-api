# run_once_migration.py
import asyncio
from database import db

async def migrate():
    async for product in db.products.find({}):
        try:
            amount = product.get("price", {}).get("amount", "0")
            unit   = product.get("price", {}).get("unit", "")
            # unit is like ".80" or "" — combine and cast
            price_float = float(str(amount) + str(unit))
            await db.products.update_one(
                {"_id": product["_id"]},
                {"$set": {"price_float": price_float}}
            )
        except Exception as e:
            print(f"Skipped {product['_id']}: {e}")
    print("Migration done")

asyncio.run(migrate())