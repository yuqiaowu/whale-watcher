import unittest

from backend.backfill_chain_flow_history import aggregate_flow_4h


class BackfillChainFlowHistoryTests(unittest.TestCase):
    def test_aggregate_flow_4h_builds_rolling_24h(self):
        events = [
            {
                "timestamp": "2026-04-18T00:10:00Z",
                "instrument": "ETH",
                "symbol": "WETH",
                "amount_usd": 1000.0,
                "signal": "BULLISH_OUTFLOW",
            },
            {
                "timestamp": "2026-04-18T03:59:00Z",
                "instrument": "ETH",
                "symbol": "USDC",
                "amount_usd": 500.0,
                "signal": "BULLISH_INFLOW",
            },
            {
                "timestamp": "2026-04-18T04:05:00Z",
                "instrument": "ETH",
                "symbol": "WETH",
                "amount_usd": 200.0,
                "signal": "BEARISH_INFLOW",
            },
        ]

        df = aggregate_flow_4h(events)
        self.assertEqual(len(df), 2)

        first = df.iloc[0]
        second = df.iloc[1]

        self.assertEqual(first["token_net_flow_4h"], 1000.0)
        self.assertEqual(first["stablecoin_net_flow_4h"], 500.0)
        self.assertEqual(first["token_net_flow_24h"], 1000.0)
        self.assertEqual(first["stablecoin_net_flow_24h"], 500.0)

        self.assertEqual(second["token_net_flow_4h"], -200.0)
        self.assertEqual(second["stablecoin_net_flow_4h"], 0.0)
        self.assertEqual(second["token_net_flow_24h"], 800.0)
        self.assertEqual(second["stablecoin_net_flow_24h"], 500.0)


if __name__ == "__main__":
    unittest.main()
