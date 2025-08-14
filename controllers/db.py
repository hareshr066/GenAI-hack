# backend/controllers/db.py
import os, json, threading, uuid
from typing import Any, Dict, List

# Optional .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

MONGO_URI = (os.getenv("MONGO_URI") or "").strip()

# Use local JSON store if URI missing or contains placeholders
USE_LOCAL = (
    not MONGO_URI
    or "<cluster>" in MONGO_URI
    or "<user>" in MONGO_URI
    or "<password>" in MONGO_URI
)

class _LocalCollection:
    def __init__(self, path="local_store.json"):
        self.path = path
        self.lock = threading.Lock()
        if not os.path.exists(self.path):
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"files": []}, f)

    def _read(self):
        with open(self.path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    def insert_one(self, doc: Dict[str, Any]):
        doc.setdefault("_id", str(uuid.uuid4()))
        with self.lock:
            data = self._read()
            data["files"].append(doc)
            self._write(data)
        class _Result: inserted_id = doc["_id"]
        return _Result()

    def find(self, _filter: Dict[str, Any] | None = None):
        data = self._read()
        return data["files"]

    def delete_many(self, _filter: Dict[str, Any] | None = None):
        with self.lock:
            data = self._read()
            deleted = len(data["files"])
            data["files"] = []
            self._write(data)
        class _Result: deleted_count = deleted
        return _Result()

if not USE_LOCAL:
    # Real Mongo (only if you set a valid MONGO_URI)
    from pymongo import MongoClient
    client = MongoClient(MONGO_URI)
    db = client[os.getenv("MONGO_DB", "genai")]
    files_collection = db[os.getenv("MONGO_COLLECTION", "files")]
else:
    files_collection = _LocalCollection(os.getenv("LOCAL_DB_PATH", "local_store.json"))
