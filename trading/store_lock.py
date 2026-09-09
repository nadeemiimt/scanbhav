"""Process-wide lock for trading JSON stores (dual desk parallel cycles)."""
from __future__ import annotations

import threading

LOCK = threading.RLock()
