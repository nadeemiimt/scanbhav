#!/usr/bin/env python3
"""CLI wrapper — refresh Nifty 500 universe from NSE archives."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from universe_refresh import refresh_universe_from_nse  # noqa: E402


def main() -> None:
    meta = refresh_universe_from_nse()
    print("Refreshed:", meta)


if __name__ == "__main__":
    main()
