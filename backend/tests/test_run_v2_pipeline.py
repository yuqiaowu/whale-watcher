import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import run_v2_pipeline as runner


class RunV2PipelineTests(unittest.TestCase):
    def test_refresh_qlib_enabled_by_default(self):
        with patch.object(
            runner,
            "refresh_qlib_before_decision",
            return_value={"enabled": True, "inference_ok": True},
        ) as mocked_refresh:
            with patch.dict(os.environ, {}, clear=False):
                refreshed = runner._refresh_qlib_if_enabled()

        self.assertTrue(refreshed)
        mocked_refresh.assert_called_once_with()

    def test_refresh_qlib_can_be_disabled(self):
        with patch.object(
            runner,
            "refresh_qlib_before_decision",
            return_value={"enabled": False, "inference_ok": False},
        ) as mocked_refresh:
            with patch.dict(os.environ, {"REFRESH_QLIB_BEFORE_V2": "0"}, clear=False):
                refreshed = runner._refresh_qlib_if_enabled()

        self.assertFalse(refreshed)
        mocked_refresh.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
