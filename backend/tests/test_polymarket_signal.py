import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from polymarket_signal import build_prediction_market_signal, delta_label, score_label


def _market(
    market_id,
    question,
    yes_price,
    end_date,
    *,
    volume24hr=20_000,
    liquidity=25_000,
    spread=0.02,
    closed=False,
):
    return {
        "conditionId": market_id,
        "question": question,
        "active": True,
        "closed": closed,
        "enableOrderBook": True,
        "endDate": end_date,
        "updatedAt": "2026-05-16T00:00:00Z",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": f'["{yes_price}", "{1 - yes_price}"]',
        "volume24hr": volume24hr,
        "liquidity": liquidity,
        "volume": 60_000,
        "spread": spread,
    }


class PolymarketSignalTests(unittest.TestCase):
    def test_score_and_delta_labels_are_explicit(self):
        self.assertEqual("MILD_RISK_ON", score_label(0.2))
        self.assertEqual("NEUTRAL", score_label(0.0))
        self.assertEqual("MILD_RISK_OFF", score_label(-0.2))
        self.assertEqual("IMPROVING", delta_label(0.06))
        self.assertEqual("STABLE", delta_label(0.0))
        self.assertEqual("WEAKENING", delta_label(-0.06))

    def test_low_probability_tail_touch_market_is_not_treated_as_risk_off(self):
        now = datetime(2026, 5, 16, 0, 0, tzinfo=timezone.utc)
        events = [
            {
                "id": "event_tail",
                "title": "Bitcoin tail market",
                "markets": [
                    _market("btc-150k", "Will Bitcoin reach $150,000 in May?", 0.02, "2026-06-01T00:00:00Z"),
                ],
            }
        ]

        signal = build_prediction_market_signal(
            now=now,
            fetch_events=lambda: events,
            market_history=[],
            signal_history=[],
            watchlist_market_ids=["btc-150k"],
            persist=False,
        )

        self.assertTrue(signal["available"])
        self.assertEqual(0.0, signal["combined_score"])
        self.assertEqual("NEUTRAL", signal["combined_label"])

    def test_build_signal_filters_markets_and_computes_same_market_deltas(self):
        now = datetime(2026, 5, 16, 0, 0, tzinfo=timezone.utc)
        events = [
            {
                "id": "event_btc",
                "title": "Bitcoin markets",
                "markets": [
                    _market("btc-100k", "Will Bitcoin be above $100,000 on June 30?", 0.64, "2026-07-01T00:00:00Z"),
                    _market("eth-4k", "Will Ethereum be above $4,000 on December 31?", 0.58, "2026-12-31T00:00:00Z"),
                    _market("sol-expired", "Will Solana reach $220 in May?", 0.55, "2026-05-17T00:00:00Z"),
                    _market("btc-closed", "Will Bitcoin be above $200,000 on June 30?", 0.30, "2026-07-01T00:00:00Z", closed=True),
                ],
            }
        ]
        prior_market_history = [
            {
                "market_id": "btc-100k",
                "market_score": 0.18,
                "snapshot_at": "2026-05-15T00:00:00Z",
            },
            {
                "market_id": "eth-4k",
                "market_score": 0.10,
                "snapshot_at": "2026-05-15T00:00:00Z",
            },
        ]
        prior_signal_history = [
            {
                "combined_score": 0.14,
                "composition_hash": "older",
                "market_ids": ["btc-100k", "eth-4k"],
                "snapshot_at": "2026-05-15T00:00:00Z",
            }
        ]

        signal = build_prediction_market_signal(
            now=now,
            fetch_events=lambda: events,
            market_history=prior_market_history,
            signal_history=prior_signal_history,
            watchlist_market_ids=["btc-100k", "eth-4k"],
            persist=False,
        )

        self.assertTrue(signal["available"])
        self.assertEqual("program", signal["calculation_owner"])
        self.assertEqual("prediction_market_expectation_reference_only", signal["interpretation_scope"])
        self.assertEqual(2, signal["eligible_market_count"])
        self.assertEqual(2, signal["stable_market_count"])
        self.assertEqual(2, signal["excluded_market_count"])
        self.assertEqual("MILD_RISK_ON", signal["combined_label"])
        self.assertEqual("IMPROVING", signal["score_delta_24h_label"])
        self.assertEqual("IMPROVING", signal["expectation_momentum_24h_label"])
        self.assertEqual(2, signal["same_market_overlap_24h_count"])
        self.assertTrue(signal["composition_changed_24h"])
        self.assertIn("expiry_too_close", signal["exclude_reason_counts"])
        self.assertIn("closed_market", signal["exclude_reason_counts"])
        self.assertGreater(len(signal["markets_used"]), 0)

    def test_new_markets_are_replacement_candidates_until_stable(self):
        now = datetime(2026, 5, 16, 0, 0, tzinfo=timezone.utc)
        events = [
            {
                "id": "event_new",
                "title": "New crypto market",
                "markets": [
                    _market("btc-new", "Will Bitcoin be above $100,000 on June 30?", 0.66, "2026-07-01T00:00:00Z"),
                ],
            }
        ]

        signal = build_prediction_market_signal(
            now=now,
            fetch_events=lambda: events,
            market_history=[],
            signal_history=[],
            watchlist_market_ids=[],
            persist=False,
        )

        self.assertFalse(signal["available"])
        self.assertEqual("no_stable_reference_markets", signal["missing_reason"])
        self.assertEqual(1, signal["eligible_market_count"])
        self.assertEqual(0, signal["stable_market_count"])
        self.assertEqual(1, signal["candidate_market_count"])
        self.assertEqual("REPLACEMENT_CANDIDATE", signal["replacement_candidates"][0]["reference_status"])

    def test_market_can_become_stable_after_repeated_history(self):
        now = datetime(2026, 5, 16, 0, 0, tzinfo=timezone.utc)
        events = [
            {
                "id": "event_history_stable",
                "title": "Stable crypto market",
                "markets": [
                    _market("btc-stable", "Will Bitcoin be above $100,000 on June 30?", 0.60, "2026-07-01T00:00:00Z"),
                ],
            }
        ]
        market_history = [
            {"market_id": "btc-stable", "market_score": 0.12, "snapshot_at": "2026-05-14T20:00:00Z"},
            {"market_id": "btc-stable", "market_score": 0.16, "snapshot_at": "2026-05-15T00:00:00Z"},
        ]

        signal = build_prediction_market_signal(
            now=now,
            fetch_events=lambda: events,
            market_history=market_history,
            signal_history=[],
            watchlist_market_ids=[],
            persist=False,
        )

        self.assertTrue(signal["available"])
        self.assertEqual(1, signal["stable_market_count"])
        self.assertEqual("HISTORY_STABLE", signal["markets_used"][0]["reference_status"])


if __name__ == "__main__":
    unittest.main()
