#!/usr/bin/env python3
"""Copy seed data into packaging/bundle_data for PyInstaller (no user caches / raw prices)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "bundle_data"


def _copy_rel(src_rel: str) -> None:
    src = ROOT / src_rel
    dest = OUT / src_rel
    if not src.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, dest)


def _write_json(rel: str, payload: object) -> None:
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    for rel in (
        "data/universe",
        "data/quant_foundation",
        "samples",
        "study-guides",
    ):
        _copy_rel(rel)

    _write_json("data/trading/pick_log.json", {"picks": []})
    _write_json("data/trading/paper_ledger.json", {"positions": [], "orders": [], "halted": False})
    _write_json("data/trading/symbol_day_blocks.json", {})
    _write_json("data/quant_cache/trade_journal.json", {"entries": []})

    (OUT / "data" / "books").mkdir(parents=True, exist_ok=True)
    readme = OUT / "data" / "books" / "README.txt"
    readme.write_text(
        "Drop investment PDFs here, then use Ingest books from the app or run ingest_books.py.\n",
        encoding="utf-8",
    )

    print(f"Bundle seed ready: {OUT}")


if __name__ == "__main__":
    main()
