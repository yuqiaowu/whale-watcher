import sys
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import acceptance_check as ac
import deterministic_pipeline as dp
import execution_reconciliation as er
import position_runtime as pr
import post_trade_review as ptr


class FakeDB:
    def __init__(self, store):
        self.store = deepcopy(store)

    def get_data(self, key, default=None):
        if default is None:
            default = []
        return deepcopy(self.store.get(key, default))

    def save_data(self, key, data):
        self.store[key] = deepcopy(data)


class FakeExecutor:
    def execute_trade(self, **kwargs):
        action = kwargs.get("action", "unknown").lower()
        if "close" in action:
            return "shadow_close_1"
        if "adjust" in action:
            return "shadow_adjust_1"
        return "shadow_open_1"


class AcceptanceCheckTests(unittest.TestCase):
    def test_acceptance_check_passes_on_valid_shadow_cycle(self):
        store = {
            "whale_analysis": {
                "fear_greed": {"value": 22, "value_classification": "Fear"},
                "macro": {
                    "fed_futures": {"change_5d_bps": 2, "trend": "restrictive", "implied_rate": 3.7},
                    "japan_macro": {"price": 144.0, "change_5d_pct": -0.5},
                    "liquidity_monitor": {
                        "dxy": {"price": 105.0, "change_5d_pct": 0.4},
                        "vix": {"price": 21.0, "change_5d_pct": 6.0},
                        "us10y": {"price": 4.15, "change_5d_pct": 0.1},
                    },
                    "global_stable_flow": -45000000,
                },
                "news": {
                    "macro": {"items": [{"title": "Fed remains cautious while dollar stays firm"}]},
                    "calendar": {"items": [{"title": "FOMC minutes due later"}]},
                },
                "btc": {"market": {"price": 65000, "rsi_4h": 42, "adx_14": 29, "volume_ratio": 1.2, "wick_ratio_lower": 35, "wick_ratio_upper": 20}},
                "eth": {"market": {"price": 2400, "rsi_4h": 40, "adx_14": 26, "volume_ratio": 1.1, "wick_ratio_lower": 33, "wick_ratio_upper": 18}},
                "sol": {"market": {"price": 80, "rsi_4h": 39, "adx_14": 24, "volume_ratio": 1.0, "wick_ratio_lower": 31, "wick_ratio_upper": 22}},
                "bnb": {"market": {"price": 600, "rsi_4h": 41, "adx_14": 22, "volume_ratio": 1.0, "wick_ratio_lower": 28, "wick_ratio_upper": 25}},
                "doge": {"market": {"price": 0.1, "rsi_4h": 38, "adx_14": 18, "volume_ratio": 1.0, "wick_ratio_lower": 27, "wick_ratio_upper": 35}},
            },
            "portfolio_state": {"positions": [], "total_equity": 10000},
            "trade_history": [],
        }
        qlib_payload = {
            "coins": [
                {"symbol": "BTC", "qlib_score": -0.005, "rank": 1, "p_up_8h": 0.66, "p_down_8h": 0.14, "p_flat_8h": 0.20, "market_data": {"atr_14": 900, "close": 65000}},
                {"symbol": "ETH", "qlib_score": -0.004, "rank": 2, "p_up_8h": 0.63, "p_down_8h": 0.16, "p_flat_8h": 0.21, "market_data": {"atr_14": 35, "close": 2400}},
                {"symbol": "SOL", "qlib_score": -0.003, "rank": 3, "p_up_8h": 0.45, "p_down_8h": 0.26, "p_flat_8h": 0.29, "market_data": {"atr_14": 2.0, "close": 80}},
                {"symbol": "BNB", "qlib_score": -0.002, "rank": 4, "p_up_8h": 0.20, "p_down_8h": 0.44, "p_flat_8h": 0.36, "market_data": {"atr_14": 8, "close": 600}},
                {"symbol": "DOGE", "qlib_score": -0.006, "rank": 5, "p_up_8h": 0.15, "p_down_8h": 0.69, "p_flat_8h": 0.16, "market_data": {"atr_14": 0.002, "close": 0.1}},
            ]
        }
        fake_db = FakeDB(store)
        patches = [
            patch.object(ac, "db", fake_db),
            patch.object(dp, "db", fake_db),
            patch.object(er, "db", fake_db),
            patch.object(pr, "db", fake_db),
            patch.object(ptr, "db", fake_db),
            patch.object(dp, "_load_qlib_payload", return_value=qlib_payload),
        ]

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            summary = ac.run_acceptance_check(executor=FakeExecutor(), refresh_qlib=False)

        self.assertTrue(summary["passed"])
        self.assertGreaterEqual(summary["record_count"], len(dp.TRACKED_SYMBOLS))
        self.assertTrue(all(item["passed"] for item in summary["checks"]))


if __name__ == "__main__":
    unittest.main()
