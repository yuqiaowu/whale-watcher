import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from okx_executor import OKXExecutor


class OKXExecutorTests(unittest.TestCase):
    def test_shadow_grid_create_returns_unique_like_id(self):
        executor = OKXExecutor(shadow_mode=True)
        executor.trading_mode = "SHADOW"

        with patch.object(executor, "_new_shadow_id", return_value="shadow_grid_789"):
            algo_id = executor.execute_grid_bot(
                symbol="ETH",
                amount_usd=500.0,
                leverage=3.0,
                grid_config={
                    "range_lower_bound": 2300.0,
                    "range_upper_bound": 2500.0,
                    "grid_count": 8,
                },
            )

        self.assertEqual(algo_id, "shadow_grid_789")

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

    def test_live_grid_create_uses_contract_grid_endpoint(self):
        executor = OKXExecutor(shadow_mode=False)
        executor.trading_mode = "DEMO"
        executor.get_instrument_info = lambda inst_id: {"tickSz": 0.1}

        with patch.object(
            executor,
            "_request",
            return_value={"code": "0", "data": [{"algoId": "grid_algo_1", "sCode": "0", "sMsg": ""}]},
        ) as mock_request:
            algo_id = executor.execute_grid_bot(
                symbol="ETH",
                amount_usd=500.0,
                leverage=3.0,
                grid_config={
                    "range_lower_bound": 2300.12,
                    "range_upper_bound": 2500.19,
                    "grid_count": 8,
                    "grid_mode": "ARITHMETIC",
                },
            )

        self.assertEqual(algo_id, "grid_algo_1")
        method, path, body = mock_request.call_args.args
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/api/v5/tradingBot/grid/order-algo")
        self.assertEqual(body["instId"], "ETH-USDT-SWAP")
        self.assertEqual(body["algoOrdType"], "contract_grid")
        self.assertEqual(body["direction"], "neutral")
        self.assertEqual(body["basePos"], False)
        self.assertEqual(body["runType"], "1")
        self.assertEqual(body["gridNum"], "8")
        self.assertEqual(body["minPx"], "2300.1")
        self.assertEqual(body["maxPx"], "2500.2")
        self.assertEqual(body["lever"], "3")
        self.assertEqual(body["sz"], "500")
        self.assertEqual(body["triggerParams"], [{"triggerAction": "start", "triggerStrategy": "instant"}])

    def test_live_grid_stop_uses_stop_endpoint(self):
        executor = OKXExecutor(shadow_mode=False)
        executor.trading_mode = "DEMO"

        with patch.object(
            executor,
            "_request",
            return_value={"code": "0", "data": [{"algoId": "grid_algo_1", "sCode": "0", "sMsg": ""}]},
        ) as mock_request:
            result = executor.stop_grid_bot(symbol="ETH", algo_id="grid_algo_1")

        self.assertEqual(result, "grid_algo_1")
        method, path, body = mock_request.call_args.args
        self.assertEqual(method, "POST")
        self.assertEqual(path, "/api/v5/tradingBot/grid/stop-order-algo")
        self.assertEqual(body, [{
            "algoId": "grid_algo_1",
            "algoOrdType": "contract_grid",
            "instId": "ETH-USDT-SWAP",
            "stopType": "1",
        }])


if __name__ == "__main__":
    unittest.main()
