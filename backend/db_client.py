import os
import json
from pymongo import MongoClient
from pymongo import ReplaceOne
from pymongo.errors import ConnectionFailure, DuplicateKeyError
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

LIST_IDENTITY_FIELDS = {
    "trade_decision_records": "decisionId",
    "decision_cycles_v2": "cycleId",
    "system_run_history": "runId",
    "trade_history": "id",
    "nav_history": "timestamp",
    "macro_history": "timestamp",
}

PRESERVE_IDENTIFIED_LIST_SAVE_RECORDS = {
    "trade_decision_records",
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
            self._ensure_collection_indexes("trade_audit_ledger", self.db["trade_audit_ledger"])
            self._ensure_collection_indexes("macro_history", self.db["macro_history"])
        except Exception as e:
            print(f"⚠️ [MongoDB Index Error] {e}")

    def _ensure_collection_indexes(self, collection_name, collection):
        if collection_name == "trade_decision_records":
            collection.create_index([("created_at", -1)], background=True)
            collection.create_index([("decisionId", 1)], background=True)
        elif collection_name == "decision_cycles_v2":
            collection.create_index([("generated_at", -1)], background=True)
            collection.create_index([("cycleId", 1)], background=True)
        elif collection_name == "trade_audit_ledger":
            collection.create_index([("event_at", -1)], background=True)
            collection.create_index([("decisionId", 1), ("event_at", -1)], background=True)
            collection.create_index([("cycleId", 1), ("symbol", 1)], background=True)
        elif collection_name == "macro_history":
            collection.create_index([("timestamp", 1)], unique=True, background=True)

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

    def _list_identity_field(self, collection_name):
        return LIST_IDENTITY_FIELDS.get(collection_name)

    def _safe_list_items(self, data):
        safe_data = []
        for item in data:
            safe_item = item.copy() if isinstance(item, dict) else {"value": item}
            safe_item.pop("_id", None)
            safe_data.append(safe_item)
        return safe_data

    def _save_identified_list_to_mongo(self, collection_name, collection, data):
        identity_field = self._list_identity_field(collection_name)
        safe_data = self._safe_list_items(data)
        if not safe_data:
            collection.delete_many({})
            return

        if not identity_field:
            collection.delete_many({})
            collection.insert_many(safe_data)
            return

        operations = []
        incoming_ids = []
        fallback_items = []
        for item in safe_data:
            identity_value = item.get(identity_field)
            if identity_value is None or identity_value == "":
                fallback_items.append(item)
                continue
            incoming_ids.append(identity_value)
            operations.append(
                ReplaceOne(
                    {identity_field: identity_value},
                    item,
                    upsert=True,
                )
            )

        if operations:
            collection.bulk_write(operations, ordered=False)

        # Keep bounded history semantics for collections that callers save as a
        # complete list, without using renameCollection privileges. Trade
        # decision records are audit/replay evidence and may be written by
        # multiple runtime steps, so saving a partial list must never delete
        # unrelated decisions.
        if incoming_ids and collection_name not in PRESERVE_IDENTIFIED_LIST_SAVE_RECORDS:
            collection.delete_many({identity_field: {"$nin": incoming_ids}})
        elif fallback_items:
            collection.delete_many({})

        if fallback_items:
            collection.insert_many(fallback_items)

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
                    return default_value
                else:
                    # Array-like collections: histories, decision cycles, ledgers
                    cursor = collection.find({}, {"_id": 0})
                    if collection_name == "trade_decision_records":
                        cursor = cursor.sort("created_at", -1)
                    elif collection_name == "decision_cycles_v2":
                        cursor = cursor.sort("generated_at", -1)
                    elif collection_name == "trade_audit_ledger":
                        cursor = cursor.sort("event_at", -1)
                    
                    data = list(cursor)
                    if data:
                        return data
                    # If empty list, fall through to local fallback
            except Exception as e:
                print(f"⚠️ [MongoDB Fetch Error] {collection_name}: {e}. Falling back to local.")
                if collection_name in SINGLETON_COLLECTIONS:
                    return default_value
        
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

    def get_singleton_strict(self, collection_name):
        """Read live singleton state without falling back to local JSON."""
        if collection_name not in SINGLETON_COLLECTIONS:
            raise ValueError(f"{collection_name} is not a singleton collection")
        if not self.is_connected or self.db is None:
            raise ConnectionFailure("MongoDB is unavailable for strict singleton read")

        doc = self.db[collection_name].find_one({"_id": "current_state"})
        if doc:
            doc.pop("_id", None)
        return doc or {}

    def get_list_strict(self, collection_name, sort_field=None, descending=False):
        """Read live list state without falling back to local JSON."""
        if not self.is_connected or self.db is None:
            raise ConnectionFailure("MongoDB is unavailable for strict list read")

        cursor = self.db[collection_name].find({}, {"_id": 0})
        if sort_field:
            cursor = cursor.sort(sort_field, -1 if descending else 1)
        return list(cursor)

    def save_list_strict(self, collection_name, data):
        """Persist a complete live list to MongoDB without relying on local JSON."""
        if not self.is_connected or self.db is None:
            raise ConnectionFailure("MongoDB is unavailable for strict list save")
        if not isinstance(data, list):
            raise ValueError("Strict list save requires list data")

        collection = self.db[collection_name]
        self._save_identified_list_to_mongo(collection_name, collection, data)

    def upsert_list_strict(self, collection_name, data):
        """Upsert live list records without deleting records written by another instance."""
        if not self.is_connected or self.db is None:
            raise ConnectionFailure("MongoDB is unavailable for strict list upsert")
        if not isinstance(data, list):
            raise ValueError("Strict list upsert requires list data")

        identity_field = self._list_identity_field(collection_name)
        if not identity_field:
            raise ValueError(f"{collection_name} has no configured list identity field")

        operations = []
        for item in self._safe_list_items(data):
            identity_value = item.get(identity_field)
            if identity_value is None or identity_value == "":
                raise ValueError(f"{collection_name} item is missing {identity_field}")
            operations.append(
                ReplaceOne(
                    {identity_field: identity_value},
                    item,
                    upsert=True,
                )
            )
        if operations:
            self.db[collection_name].bulk_write(operations, ordered=False)

    def claim_once(self, collection_name, claim_id, payload=None):
        """Atomically claim a live-only operation. Returns False if already claimed."""
        if not self.is_connected or self.db is None:
            raise ConnectionFailure("MongoDB is unavailable for atomic claim")

        claim = dict(payload or {})
        claim["_id"] = str(claim_id)
        try:
            self.db[collection_name].insert_one(claim)
            return True
        except DuplicateKeyError:
            return False

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
                    if isinstance(data, list):
                        self._save_identified_list_to_mongo(collection_name, collection, data)
            except Exception as e:
                print(f"⚠️ [MongoDB Sync Error] {collection_name}: {e}")

    def append_data(self, collection_name, item, max_local_records=1000):
        """Append one immutable record.

        Array-like save_data() intentionally replaces bounded frontend-facing
        collections. Audit ledgers need insert semantics so later reconciliations
        cannot overwrite the original decision evidence.
        """
        if not isinstance(item, dict):
            item = {"value": item}

        path = self._get_local_path(collection_name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            local_data = []
            if os.path.exists(path):
                with open(path, "r") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, list):
                        local_data = loaded
            item_id = item.get("_id") or item.get("event_id")
            already_exists = any(
                (existing.get("_id") or existing.get("event_id")) == item_id
                for existing in local_data
                if isinstance(existing, dict)
            )
            if not item_id or not already_exists:
                local_data.append(item.copy())
                if max_local_records and len(local_data) > max_local_records:
                    local_data = local_data[-max_local_records:]
                with open(path, "w") as f:
                    json.dump(self._normalize_list_for_local_storage(collection_name, local_data), f, indent=2)
        except Exception as e:
            print(f"⚠️ Failed to append local json {collection_name}: {e}")

        if self.is_connected:
            try:
                safe_item = item.copy()
                collection = self.db[collection_name]
                collection.insert_one(safe_item)
            except DuplicateKeyError:
                pass
            except Exception as e:
                print(f"⚠️ [MongoDB Append Error] {collection_name}: {e}")

# Singleton Instance
db = DBClient()
