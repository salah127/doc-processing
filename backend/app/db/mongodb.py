import os
from typing import Optional

from pymongo import MongoClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/hackathon")

_client: Optional[MongoClient] = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client


def get_db():
    """Return the database object derived from MONGO_URI."""
    client = get_client()
    db_name = MONGO_URI.rstrip("/").split("/")[-1]
    return client[db_name]
