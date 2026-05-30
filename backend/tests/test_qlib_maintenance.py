import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import qlib_maintenance as qm


class QlibMaintenanceTests(unittest.TestCase):
    def test_retrain_needed_when_train_end_lags_latest_csv_even_if_model_file_is_recent(self):
        model_stat = MagicMock()
        model_stat.st_mtime = datetime(2026, 5, 30, 0, 6, 31).timestamp()
        model_path = MagicMock()
        model_path.exists.return_value = True
        model_path.stat.return_value = model_stat

        with patch.dict(os.environ, {"QLIB_RETRAIN_POLICY": "weekly"}, clear=False), \
             patch.object(qm, "MODEL_PATH", model_path), \
             patch.object(qm, "_load_model_meta", return_value={"train_end": "2026-05-20"}), \
             patch.object(qm, "_latest_csv_datetime", return_value="2026-05-30 16:00:00"):
            report = qm.qlib_retrain_needed(now=datetime(2026, 5, 30, 22, 5, 0))

        self.assertTrue(report["needed"])
        self.assertIn("model_train_lag_exceeded", report["reasons"])
        self.assertEqual(report["model_train_lag_days"], 10)
        self.assertEqual(report["model_train_lag_reason"], "train_end_too_old")

    def test_retrain_not_needed_when_train_end_is_within_allowed_lag(self):
        model_stat = MagicMock()
        model_stat.st_mtime = datetime(2026, 5, 30, 0, 6, 31).timestamp()
        model_path = MagicMock()
        model_path.exists.return_value = True
        model_path.stat.return_value = model_stat

        with patch.dict(os.environ, {"QLIB_RETRAIN_POLICY": "weekly"}, clear=False), \
             patch.object(qm, "MODEL_PATH", model_path), \
             patch.object(qm, "_load_model_meta", return_value={"train_end": "2026-05-25"}), \
             patch.object(qm, "_latest_csv_datetime", return_value="2026-05-30 16:00:00"):
            report = qm.qlib_retrain_needed(now=datetime(2026, 5, 30, 22, 5, 0))

        self.assertFalse(report["needed"])
        self.assertEqual(report["reasons"], [])
        self.assertEqual(report["model_train_lag_days"], 5)
        self.assertEqual(report["model_train_lag_reason"], "ok")


if __name__ == "__main__":
    unittest.main()
