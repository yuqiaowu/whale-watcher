import os
import json
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from datetime import datetime
from dotenv import load_dotenv
import certifi
from urllib.parse import urlparse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(PROJECT_ROOT, ".env"))

SINGLETON_COLLECTIONS = {
    "portfolio_state",
    "whale_analysis",
    "latest_trade_decision_record",
    "latest_decision_cycle_v2",
    "latest_system_run",
}

class DBClient:
    def __init__(self):
        self.uri = os.getenv("MONGODB_URI")
        self.db_name = self._resolve_db_name(self.uri)
        self.client = None
        self.db = None
        self.is_connected = False
        
        if self.uri and "mongodb+srv://<" not in self.uri and "<password>" not in self.uri:
            try:
                # Disable SSL warnings for local dev sometimes, but SRV needs it
                self.client = MongoClient(
                    self.uri,
                    serverSelectionTimeoutMS=5000,
                    connectTimeoutMS=5000,
                    socketTimeoutMS=15000,
                    timeoutMS=20000,
                    tlsCAFile=certifi.where(),
                )
                # Verify connection
                self.client.admin.command('ping')
                self.db = self.client[self.db_name]
                self.is_connected = True
                self._ensure_indexes()
                print(f"✅ [MongoDB] Safely connected to Cloud Database! db={self.db_name}")
            except Exception as e:
                print(f"⚠️ [MongoDB] Connection Failed: {e}. Falling back to local JSON.")
        else:
            print("⚠️ [MongoDB] Missing or invalid MONGODB_URI. Falling back to local JSON files.")

    def _resolve_db_name(self, uri):
        explicit_name = os.getenv("MONGODB_DB_NAME", "").strip()
        if explicit_name:
            return explicit_name
        if uri:
            try:
                parsed = urlparse(uri)
                db_name = parsed.path.strip("/")
                if db_name:
                    return db_name
            except Exception:
                pass
        return "whale_watcher"

    def _ensure_indexes(self):
        try:
            self._ensure_collection_indexes("trade_decision_records", self.db["trade_decision_records"])
            self._ensure_collection_indexes("decision_cycles_v2", self.db["decision_cycles_v2"])
        except Exception as e:
            print(f"⚠️ [MongoDB Index Error] {e}")

    def _ensure_collection_indexes(self, collection_name, collection):
        if collection_name == "trade_decision_records":
            collection.create_index([("created_at", -1)], background=True)
        elif collection_name == "decision_cycles_v2":
            collection.create_index([("generated_at", -1)], background=True)

    def _get_local_path(self, collection_name):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_dir, "frontend", "data", f"{collection_name}.json")

    def _normalize_local_list_for_runtime(self, collection_name, data):
        if not isinstance(data, list):
            return data
        if collection_name in ["trade_decision_records", "decision_cycles_v2"]:
            field = "created_at" if collection_name == "trade_decision_records" else "generated_at"
            return sorted(
                data,
                key=lambda item: str(item.get(field) or item.get("cycleId") or ""),
                reverse=True,
            )
        return data

    def _normalize_list_for_local_storage(self, collection_name, data):
        if not isinstance(data, list):
            return data
        if collection_name in ["trade_decision_records", "decision_cycles_v2"]:
            field = "created_at" if collection_name == "trade_decision_records" else "generated_at"
            # Keep historical JSON files chronologically ordered so opening the
            # file directly is not misleading.
            return sorted(
                data,
                key=lambda item: str(item.get(field) or item.get("cycleId") or ""),
            )
        return data

    # --- Read / Get ---
    def get_data(self, collection_name, default_value=None):
        if default_value is None:
            default_value = {} if collection_name in SINGLETON_COLLECTIONS else []

        if self.is_connected:
            try:
                collection = self.db[collection_name]
                if collection_name in SINGLETON_COLLECTIONS:
                    # Fetch the latest state document
                    doc = collection.find_one({"_id": "current_state"})
                    if doc:
                        doc.pop("_id", None)
                        return doc
                    # If MongoDB is empty for this, fall through to local fallback
                else:
                    # Array-like collections: histories, decision cycles, ledgers
                    cursor = collection.find({}, {"_id": 0})
                    if collection_name == "trade_decision_records":
                        cursor = cursor.sort("created_at", -1)
                    elif collection_name == "decision_cycles_v2":
                        cursor = cursor.sort("generated_at", -1)
                    
                    data = list(cursor)
                    if data:
                        return data
                    # If empty list, fall through to local fallback
            except Exception as e:
                print(f"⚠️ [MongoDB Fetch Error] {collection_name}: {e}. Falling back to local.")
        
        # Fallback to local
        path = self._get_local_path(collection_name)
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
                    return self._normalize_local_list_for_runtime(collection_name, data)
            except:
                pass
        return default_value

    # --- Write / Save ---
    def save_data(self, collection_name, data):
        # 1. Always save to local json as backup / fast read for frontend
        path = self._get_local_path(collection_name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w") as f:
                json.dump(self._normalize_list_for_local_storage(collection_name, data), f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to write local json {collection_name}: {e}")

        # 2. Sync to MongoDB if connected
        if self.is_connected:
            try:
                collection = self.db[collection_name]
                if collection_name in SINGLETON_COLLECTIONS:
                    # Update a single master document
                    safe_data = data.copy() if isinstance(data, dict) else {"value": data}
                    safe_data["_id"] = "current_state"
                    collection.replace_one({"_id": "current_state"}, safe_data, upsert=True)
                else:
                    # Replace array-like collections atomically. The old
                    # delete-then-insert path could leave Mongo empty if a
                    # large history write failed after delete_many({}).
                    if isinstance(data, list):
                        if not data:
                            collection.delete_many({})
                        else:
                            safe_data = []
                            for item in data:
                                safe_item = item.copy() if isinstance(item, dict) else {"value": item}
                                safe_item.pop("_id", None)
                                safe_data.append(safe_item)

                            temp_name = f"__tmp_replace_{collection_name}"
                            temp_collection = self.db[temp_name]
                            temp_collection.drop()
                            try:
                                for idx in range(0, len(safe_data), 100):
                                    temp_collection.insert_many(safe_data[idx:idx + 100])
                                self._ensure_collection_indexes(collection_name, temp_collection)
                                temp_collection.rename(collection_name, dropTarget=True)
                            except Exception:
                                temp_collection.drop()
                                raise
            except Exception as e:
                print(f"⚠️ [MongoDB Sync Error] {collection_name}: {e}")

# Singleton Instance
db = DBClient()
