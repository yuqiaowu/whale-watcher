import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from okx_executor import OKXExecutor


class OKXExecutorTests(unittest.TestCase):
    def test_shadow_open_returns_unique_like_id(self):
        executor = OKXExecutor(shadow_mode=True)
        executor.trading_mode = "SHADOW"
        executor.get_market_ticker = lambda inst_id: {"last": "100", "askPx": "101", "bidPx": "99"}
        executor.calculate_position_size = lambda inst_id, amount_usd, price: 1
        executor.get_account_equity = lambda: 10000.0
        executor._load_shadow_state = lambda: {"cash": 10000.0, "total_equity": 10000.0, "positions": []}
        executor._save_shadow_state = lambda state: None

        with patch.object(executor, "_new_shadow_id", return_value="shadow_open_123"):
            order_id = executor.execute_trade(
                symbol="ETH",
                action="open_long",
                amount_usd=100.0,
                leverage=2.0,
                stop_loss=95.0,
                take_profit=110.0,
                pos_side="long",
            )

        self.assertEqual(order_id, "shadow_open_123")

    def test_shadow_adjust_returns_unique_like_id(self):
        executor = OKXExecutor(shadow_mode=True)
        executor.trading_mode = "SHADOW"
        executor.get_market_ticker = lambda inst_id: {"last": "100", "askPx": "101", "bidPx": "99"}
        executor._load_shadow_state = lambda: {
            "cash": 10000.0,
            "total_equity": 10000.0,
            "positions": [{"symbol": "ETH", "type": "long", "stop_loss": 95.0, "take_profit": 110.0}],
        }
        executor._save_shadow_state = lambda state: None

        with patch.object(executor, "_new_shadow_id", return_value="shadow_adjust_456"):
            order_id = executor.execute_trade(
                symbol="ETH",
                action="adjust_sl_tp",
                amount_usd=0.0,
                leverage=1.0,
                stop_loss=96.0,
                take_profit=112.0,
                pos_side="long",
            )

        self.assertEqual(order_id, "shadow_adjust_456")


if __name__ == "__main__":
    unittest.main()
