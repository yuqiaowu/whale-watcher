import os
import json
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from datetime import datetime
from dotenv import load_dotenv
import certifi

load_dotenv()

class DBClient:
    def __init__(self):
        self.uri = os.getenv("MONGODB_URI")
        self.client = None
        self.db = None
        self.is_connected = False
        
        if self.uri and "mongodb+srv://<" not in self.uri and "<password>" not in self.uri:
            try:
                # Disable SSL warnings for local dev sometimes, but SRV needs it
                self.client = MongoClient(self.uri, serverSelectionTimeoutMS=5000, tlsCAFile=certifi.where())
                # Verify connection
                self.client.admin.command('ping')
                self.db = self.client.whale_watcher # Database name
                self.is_connected = True
                print("✅ [MongoDB] Safely connected to Cloud Database!")
            except Exception as e:
                print(f"⚠️ [MongoDB] Connection Failed: {e}. Falling back to local JSON.")
        else:
            print("⚠️ [MongoDB] Missing or invalid MONGODB_URI. Falling back to local JSON files.")

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
            default_value = [] if collection_name != "portfolio_state" else {}

        if self.is_connected:
            try:
                collection = self.db[collection_name]
                if collection_name in ["portfolio_state", "whale_analysis"]:
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
                if collection_name == "portfolio_state":
                    # Update a single master document
                    data["_id"] = "current_state" 
                    collection.replace_one({"_id": "current_state"}, data, upsert=True)
                else:
                    # For arrays (logs, history), if we pass the whole array, we'd need to clear and insert
                    # Or better: just replace everything. Since array sizes are small right now.
                    # A better way for large arrays is to use insert_one when a new log arrives, 
                    # but since the current architecture dumps the whole list, we drop and insert many.
                    if isinstance(data, list) and len(data) > 0:
                        collection.delete_many({})
                        # MongoDB modification: Ensure no internal `_id` conflicts
                        safe_data = []
                        for item in data:
                            safe_item = item.copy()
                            safe_item.pop("_id", None)
                            safe_data.append(safe_item)
                        collection.insert_many(safe_data)
            except Exception as e:
                print(f"⚠️ [MongoDB Sync Error] {collection_name}: {e}")

# Singleton Instance
db = DBClient()
