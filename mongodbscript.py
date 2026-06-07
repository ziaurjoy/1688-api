


import os
from bson import json_util
from pymongo import MongoClient

# MongoDB Atlas URI
MONGO_URI = "mongodb+srv://joypythondev_db_user:8mnFFNkdCTtvPAOj@cluster0.i9ritpt.mongodb.net/"

# Database and Collection
DATABASE_NAME = "1688"

# Folder containing JSON files
JSON_DIRECTORY = "jsondata"

# Connect MongoDB
client = MongoClient(MONGO_URI)

db = client[DATABASE_NAME]

total_uploaded = 0

for file in os.listdir(JSON_DIRECTORY):

    if not file.endswith(".json"):
        continue

    filepath = os.path.join(JSON_DIRECTORY, file)

    # collection name = filename without extension
    collection_name = os.path.splitext(file)[0]

    collection = db[collection_name]

    try:

        with open(filepath, "r", encoding="utf-8") as f:
            data = json_util.loads(f.read())

        inserted = 0

        if isinstance(data, list):

            if data:
                result = collection.insert_many(data)
                inserted = len(result.inserted_ids)

        elif isinstance(data, dict):

            collection.insert_one(data)
            inserted = 1

        else:

            print(f"Skipping {file} (invalid JSON format)")
            continue

        total_uploaded += inserted

        print(
            f"✓ {file} -> Collection '{collection_name}' "
            f"({inserted} documents)"
        )

    except Exception as e:

        print(f"✗ Failed {file}: {e}")

print(f"\nTotal uploaded documents: {total_uploaded}")

client.close()