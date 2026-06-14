import sys
import unittest
from copy import deepcopy
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db_client import DBClient
from pymongo.errors import ConnectionFailure


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = deepcopy(docs or [])
        self.renamed = False

    def bulk_write(self, operations, ordered=False):
        for operation in operations:
            identity_field, identity_value = next(iter(operation._filter.items()))
            self.docs = [
                doc
                for doc in self.docs
                if doc.get(identity_field) != identity_value
            ]
            self.docs.append(deepcopy(operation._doc))

    def delete_many(self, query):
        if not query:
            deleted = len(self.docs)
            self.docs = []
            return deleted

        field, condition = next(iter(query.items()))
        if "$nin" in condition:
            keep_values = set(condition["$nin"])
            self.docs = [doc for doc in self.docs if doc.get(field) in keep_values]
        return 0

    def insert_many(self, docs):
        self.docs.extend(deepcopy(docs))

    def insert_one(self, doc):
        if any(existing.get("_id") == doc.get("_id") for existing in self.docs):
            from pymongo.errors import DuplicateKeyError
            raise DuplicateKeyError("duplicate")
        self.docs.append(deepcopy(doc))

    def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return deepcopy(doc)
        return None

    def find(self, query, projection=None):
        docs = deepcopy(self.docs)
        if projection and projection.get("_id") == 0:
            for doc in docs:
                doc.pop("_id", None)
        return FakeCursor(docs)

    def rename(self, *args, **kwargs):
        self.renamed = True
        raise AssertionError("renameCollection should not be used for list saves")


class DBClientListSaveTests(unittest.TestCase):
    def setUp(self):
        self.client = DBClient.__new__(DBClient)

    def test_trade_decision_records_preserve_unrelated_records_on_save(self):
        collection = FakeCollection([
            {"decisionId": "old", "symbol": "ETH-USDT"},
            {"decisionId": "keep", "symbol": "BTC-USDT", "updated_at": "old"},
        ])

        self.client._save_identified_list_to_mongo(
            "trade_decision_records",
            collection,
            [
                {"decisionId": "keep", "symbol": "BTC-USDT", "updated_at": "new"},
                {"decisionId": "new", "symbol": "SOL-USDT"},
            ],
        )

        by_id = {doc["decisionId"]: doc for doc in collection.docs}
        self.assertEqual(set(by_id), {"old", "keep", "new"})
        self.assertEqual(by_id["keep"]["updated_at"], "new")
        self.assertFalse(collection.renamed)

    def test_decision_cycles_use_cycle_id_upsert(self):
        collection = FakeCollection([
            {"cycleId": "cycle_old"},
            {"cycleId": "cycle_keep", "generated_at": "old"},
        ])

        self.client._save_identified_list_to_mongo(
            "decision_cycles_v2",
            collection,
            [
                {"cycleId": "cycle_keep", "generated_at": "new"},
                {"cycleId": "cycle_new", "generated_at": "newer"},
            ],
        )

        by_id = {doc["cycleId"]: doc for doc in collection.docs}
        self.assertEqual(set(by_id), {"cycle_keep", "cycle_new"})
        self.assertEqual(by_id["cycle_keep"]["generated_at"], "new")

    def test_unidentified_lists_still_replace_contents(self):
        collection = FakeCollection([{"value": "old"}])

        self.client._save_identified_list_to_mongo(
            "unknown_history",
            collection,
            [{"value": "new"}],
        )

        self.assertEqual(collection.docs, [{"value": "new"}])

    def test_identified_lists_replace_when_items_lack_identity(self):
        collection = FakeCollection([{"symbol": "old"}])

        self.client._save_identified_list_to_mongo(
            "trade_history",
            collection,
            [{"symbol": "new"}],
        )

        self.assertEqual(collection.docs, [{"symbol": "new"}])


class FakeDB(dict):
    def __getitem__(self, name):
        return super().__getitem__(name)


class FakeCursor(list):
    def sort(self, field, direction):
        return FakeCursor(sorted(
            self,
            key=lambda item: str(item.get(field) or ""),
            reverse=direction < 0,
        ))


class DBClientLiveSafetyTests(unittest.TestCase):
    def setUp(self):
        self.client = DBClient.__new__(DBClient)
        self.client.is_connected = True
        self.client.db = FakeDB({
            "latest_decision_cycle_v2": FakeCollection([
                {"_id": "current_state", "cycleId": "cycle_2026-06-03_2000"},
            ]),
            "decision_cycle_execution_locks": FakeCollection(),
        })

    def test_strict_singleton_read_uses_live_mongo(self):
        result = self.client.get_singleton_strict("latest_decision_cycle_v2")

        self.assertEqual(result["cycleId"], "cycle_2026-06-03_2000")
        self.assertNotIn("_id", result)

    def test_strict_singleton_read_fails_when_mongo_unavailable(self):
        self.client.is_connected = False

        with self.assertRaises(ConnectionFailure):
            self.client.get_singleton_strict("latest_decision_cycle_v2")

    def test_claim_once_is_atomic(self):
        self.assertTrue(self.client.claim_once(
            "decision_cycle_execution_locks",
            "cycle_2026-06-03_2000",
            {"version": "first"},
        ))
        self.assertFalse(self.client.claim_once(
            "decision_cycle_execution_locks",
            "cycle_2026-06-03_2000",
            {"version": "second"},
        ))

    def test_strict_list_read_uses_live_mongo_and_sorting(self):
        self.client.db["macro_history"] = FakeCollection([
            {"timestamp": "2026-06-04T00:00:00Z", "fear_greed": 12},
            {"timestamp": "2026-05-30T00:00:00Z", "fear_greed": 23},
        ])

        result = self.client.get_list_strict("macro_history", sort_field="timestamp")

        self.assertEqual([item["fear_greed"] for item in result], [23, 12])

    def test_strict_list_save_writes_mongo_without_local_storage(self):
        collection = FakeCollection([
            {"timestamp": "2026-05-30T00:00:00Z", "fear_greed": 23},
        ])
        self.client.db["macro_history"] = collection

        self.client.save_list_strict("macro_history", [
            {"timestamp": "2026-06-04T00:00:00Z", "fear_greed": 12},
        ])

        self.assertEqual(collection.docs, [
            {"timestamp": "2026-06-04T00:00:00Z", "fear_greed": 12},
        ])

    def test_strict_list_save_fails_when_mongo_unavailable(self):
        self.client.is_connected = False

        with self.assertRaises(ConnectionFailure):
            self.client.save_list_strict("macro_history", [])

    def test_strict_list_upsert_preserves_records_from_other_instances(self):
        collection = FakeCollection([
            {"timestamp": "2026-05-30T00:00:00Z", "fear_greed": 23},
            {"timestamp": "2026-06-04T00:00:00Z", "fear_greed": 12},
        ])
        self.client.db["macro_history"] = collection

        self.client.upsert_list_strict("macro_history", [
            {"timestamp": "2026-05-30T00:00:00Z", "fear_greed": 22},
        ])

        by_timestamp = {doc["timestamp"]: doc for doc in collection.docs}
        self.assertEqual(by_timestamp, {
            "2026-05-30T00:00:00Z": {
                "timestamp": "2026-05-30T00:00:00Z",
                "fear_greed": 22,
            },
            "2026-06-04T00:00:00Z": {
                "timestamp": "2026-06-04T00:00:00Z",
                "fear_greed": 12,
            },
        })

    def test_strict_list_upsert_fails_when_mongo_unavailable(self):
        self.client.is_connected = False

        with self.assertRaises(ConnectionFailure):
            self.client.upsert_list_strict("macro_history", [])


if __name__ == "__main__":
    unittest.main()
