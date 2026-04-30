import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, Iterable, List
from urllib.parse import urlparse

import certifi
from dotenv import load_dotenv
from pymongo import MongoClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "frontend" / "data"

SINGLETON_COLLECTIONS = {
    "portfolio_state",
    "whale_analysis",
    "latest_trade_decision_record",
    "latest_decision_cycle_v2",
    "latest_system_run",
}

DEFAULT_COLLECTIONS = [
    "portfolio_state",
    "trade_history",
    "trade_decision_records",
    "decision_cycles_v2",
    "latest_trade_decision_record",
    "latest_decision_cycle_v2",
    "nav_history",
    "whale_analysis",
    "agent_decision_log",
    "agent_decisions",
    "macro_history",
    "system_run_history",
    "latest_system_run",
]


def _db_name_from_uri(uri: str) -> str:
    explicit_name = os.getenv("MONGODB_DB_NAME", "").strip()
    if explicit_name:
        return explicit_name
    parsed = urlparse(uri)
    db_name = parsed.path.strip("/")
    return db_name or "whale_watcher"


def _client() -> MongoClient:
    load_dotenv(PROJECT_ROOT / ".env")
    uri = os.getenv("MONGODB_URI")
    if not uri:
        raise RuntimeError("MONGODB_URI is not set")
    return MongoClient(
        uri,
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=5000,
        socketTimeoutMS=15000,
        tlsCAFile=certifi.where(),
    )


def _local_path(collection: str) -> Path:
    return DATA_DIR / f"{collection}.json"


def _load_local(collection: str) -> Any:
    path = _local_path(collection)
    if not path.exists():
        return {} if collection in SINGLETON_COLLECTIONS else []
    return json.loads(path.read_text(encoding="utf-8"))


def _write_local(collection: str, data: Any) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _local_path(collection).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _safe_doc(item: Dict[str, Any]) -> Dict[str, Any]:
    safe = dict(item)
    safe.pop("_id", None)
    return safe


def _load_mongo(db, collection: str) -> Any:
    coll = db[collection]
    if collection in SINGLETON_COLLECTIONS:
        doc = coll.find_one({"_id": "current_state"}, {"_id": 0})
        return doc or {}
    return list(coll.find({}, {"_id": 0}))


def _write_mongo(db, collection: str, data: Any) -> None:
    coll = db[collection]
    if collection in SINGLETON_COLLECTIONS:
        safe_data = dict(data) if isinstance(data, dict) else {"value": data}
        safe_data["_id"] = "current_state"
        coll.replace_one({"_id": "current_state"}, safe_data, upsert=True)
        return

    coll.delete_many({})
    if isinstance(data, list) and data:
        coll.insert_many([_safe_doc(item) if isinstance(item, dict) else {"value": item} for item in data])


def _count(data: Any) -> int:
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict):
        return 1 if data else 0
    return 0


def _latest_marker(data: Any) -> str:
    keys = ("created_at", "generated_at", "completed_at", "updated_at", "exitTime", "timestamp")
    items: Iterable[Any]
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]
    else:
        items = []
    markers: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in keys:
            value = item.get(key)
            if value:
                markers.append(str(value))
                break
    return max(markers) if markers else ""


def _collections_arg(value: str) -> List[str]:
    if value == "default":
        return DEFAULT_COLLECTIONS
    if value == "all-local":
        return sorted(path.stem for path in DATA_DIR.glob("*.json") if not path.stem.endswith(".bak"))
    return [item.strip() for item in value.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync frontend/data JSON files with MongoDB.")
    parser.add_argument(
        "--direction",
        choices=["status", "local-to-mongo", "mongo-to-local"],
        default="status",
    )
    parser.add_argument("--collections", default="default")
    parser.add_argument("--write", action="store_true", help="Actually write data. Without this, runs dry-run only.")
    args = parser.parse_args()

    client = _client()
    client.admin.command("ping")
    db_name = _db_name_from_uri(os.environ["MONGODB_URI"])
    db = client[db_name]
    collections = _collections_arg(args.collections)

    report = {
        "db_name": db_name,
        "direction": args.direction,
        "write": args.write,
        "collections": [],
    }

    for collection in collections:
        local_data = _load_local(collection)
        mongo_data = _load_mongo(db, collection)
        row = {
            "collection": collection,
            "local_count": _count(local_data),
            "mongo_count": _count(mongo_data),
            "local_latest": _latest_marker(local_data),
            "mongo_latest": _latest_marker(mongo_data),
            "action": "none",
        }

        if args.direction == "local-to-mongo":
            row["action"] = "would_write_local_to_mongo"
            if args.write:
                _write_mongo(db, collection, local_data)
                row["action"] = "wrote_local_to_mongo"
        elif args.direction == "mongo-to-local":
            row["action"] = "would_write_mongo_to_local"
            if args.write:
                _write_local(collection, mongo_data)
                row["action"] = "wrote_mongo_to_local"

        report["collections"].append(row)

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
