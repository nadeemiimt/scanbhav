import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "screen_checkpoint",
    _ROOT / "routes" / "screen_checkpoint.py",
)
ck = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ck)


@pytest.fixture
def checkpoint_dir(tmp_path, monkeypatch):
    cache = tmp_path / "screen_cache"
    cache.mkdir()
    monkeypatch.setattr(ck, "CHECKPOINT_PATH", cache / "checkpoint.json")
    monkeypatch.setattr(ck, "META_PATH", cache / "checkpoint_meta.json")
    return cache


def test_save_checkpoint_writes_slim_rows_and_meta(checkpoint_dir):
    fat = {
        "symbol": "RELIANCE.NSE",
        "bucket": "large",
        "price": 2500,
        "as_of": "2026-08-17",
        "bars": {"ohlc": [1, 2, 3]},
        "technicals": {"rsi": 55, "series": list(range(1000))},
        "ratings": {"composite_score": 72, "horizons": {"1m": {"score": 72}}},
        "extended": {"plan": "x" * 5000},
    }
    ck.save_checkpoint(
        request={"limit": 500, "horizon": "1m", "bucket": None, "provider": "auto", "batch_strategy": "round_robin"},
        results=[fat],
        error_map={},
        universe_size=500,
        started_at="2026-08-17T00:00:00+00:00",
    )
    saved = json.loads(ck.CHECKPOINT_PATH.read_text())
    row = saved["results"][0]
    assert "technicals" not in row
    assert "bars" not in row
    assert row["ratings"]["composite_score"] == 72
    meta = ck.checkpoint_summary()
    assert meta["available"] is True
    assert meta["scored"] == 1
    assert meta["universe_size"] == 500


def test_slim_existing_checkpoint_shrinks_file(checkpoint_dir):
    payload = {
        "version": 1,
        "started_at": "2026-08-17T00:00:00+00:00",
        "updated_at": "2026-08-17T00:00:00+00:00",
        "request": {"limit": 500, "horizon": "1m"},
        "universe_size": 500,
        "scored": 1,
        "failed": 0,
        "results": [{
            "symbol": "TCS.NSE",
            "bucket": "large",
            "price": 4000,
            "as_of": "2026-08-17",
            "technicals": {"blob": "x" * 20000},
            "ratings": {"composite_score": 60, "horizons": {"1m": {"score": 60}}},
            "extended": {"y": "z" * 5000},
        }],
        "errors": [],
    }
    ck.CHECKPOINT_PATH.write_text(json.dumps(payload), encoding="utf-8")
    before = ck.CHECKPOINT_PATH.stat().st_size
    out = ck.slim_existing_checkpoint()
    after = ck.CHECKPOINT_PATH.stat().st_size
    assert out["slimmed"] is True
    assert after < before
    assert ck.load_checkpoint_meta()["scored"] == 1


def test_checkpoint_summary_reads_meta_only(checkpoint_dir):
    ck.META_PATH.write_text(json.dumps({
        "available": True,
        "scored": 250,
        "failed": 0,
        "universe_size": 500,
        "request": {"limit": 500, "horizon": "1m"},
    }), encoding="utf-8")
    summary = ck.checkpoint_summary()
    assert summary["scored"] == 250
    assert summary["available"] is True
