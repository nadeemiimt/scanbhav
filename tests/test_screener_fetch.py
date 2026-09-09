import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from routes.helpers import _read_cached_payload, _stale_cache_fallback, raw_path


class StaleCacheFallbackTests(unittest.TestCase):
    def test_read_cached_payload_requires_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.json"
            path.write_text(json.dumps({
                "Time Series (Daily)": {
                    f"2024-01-{d:02d}": {"4. close": "100"} for d in range(1, 35)
                }
            }))
            payload = _read_cached_payload(path, min_rows=30)
            self.assertIsNotNone(payload)

    def test_stale_cache_fallback_marks_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.json"
            path.write_text(json.dumps({
                "Meta Data": {"source": "Yahoo Finance"},
                "Time Series (Daily)": {
                    f"2024-01-{d:02d}": {"4. close": "100"} for d in range(1, 35)
                }
            }))
            out = _stale_cache_fallback(path, RuntimeError("503 Service Unavailable"))
            self.assertIsNotNone(out)
            self.assertTrue(out["Meta Data"]["stale_cache_used"])


if __name__ == "__main__":
    unittest.main()
