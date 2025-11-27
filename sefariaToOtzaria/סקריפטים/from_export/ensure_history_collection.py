#!/usr/bin/env python3
"""
Ensure the MongoDB collection 'history' exists in the 'sefaria' database.

"""
from pymongo import MongoClient, errors


def main() -> None:
    client = MongoClient("mongodb://127.0.0.1:27017")
    db = client["sefaria"]
    try:
        db.create_collection("history")
        print("Created empty 'history' collection.")
    except errors.CollectionInvalid:
        print("'history' collection already exists.")


if __name__ == "__main__":
    main()
