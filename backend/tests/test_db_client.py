import sys
import unittest
from copy import deepcopy
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from db_client import DBClient


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

    def rename(self, *args, **kwargs):
        self.renamed = True
        raise AssertionError("renameCollection should not be used for list saves")


class DBClientListSaveTests(unittest.TestCase):
    def setUp(self):
        self.client = DBClient.__new__(DBClient)

    def test_trade_decision_records_use_upsert_not_rename(self):
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
        self.assertEqual(set(by_id), {"keep", "new"})
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


if __name__ == "__main__":
    unittest.main()
