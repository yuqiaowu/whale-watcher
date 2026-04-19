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
        with patch.object(runner, "_run_script") as mocked_run:
            with patch.dict(os.environ, {}, clear=False):
                refreshed = runner._refresh_qlib_if_enabled()

        self.assertTrue(refreshed)
        self.assertEqual(mocked_run.call_count, 2)
        mocked_run.assert_any_call("update_qlib_data.py")
        mocked_run.assert_any_call("inference_qlib_model.py")

    def test_refresh_qlib_can_be_disabled(self):
        with patch.object(runner, "_run_script") as mocked_run:
            with patch.dict(os.environ, {"REFRESH_QLIB_BEFORE_V2": "0"}, clear=False):
                refreshed = runner._refresh_qlib_if_enabled()

        self.assertFalse(refreshed)
        mocked_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
