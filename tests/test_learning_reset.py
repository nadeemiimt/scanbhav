"""Learning / RAG reset."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from trading.learning_reset import reset_learning_json_files, run_learning_reset


def test_run_learning_reset_requires_confirm():
    out = run_learning_reset(confirm=False)
    assert out["ok"] is False
    assert "confirm" in out["error"]


def test_reset_learning_json_files(tmp_path, monkeypatch):
    trading = tmp_path / "trading"
    quant = tmp_path / "quant_cache"
    trading.mkdir()
    quant.mkdir()
    (trading / "pick_log.json").write_text(json.dumps({"picks": [{"id": "x"}]}), encoding="utf-8")

    monkeypatch.setattr("trading.learning_reset.TRADING_DIR", trading)
    monkeypatch.setattr("trading.learning_reset.QUANT_CACHE", quant)

    result = reset_learning_json_files()
    assert result["pick_log"] == "cleared"
    data = json.loads((trading / "pick_log.json").read_text(encoding="utf-8"))
    assert data["picks"] == []


def test_run_learning_reset_clears_pick_log(tmp_path, monkeypatch):
    trading = tmp_path / "trading"
    quant = tmp_path / "quant_cache"
    reports = trading / "session_reports"
    trading.mkdir()
    quant.mkdir()
    reports.mkdir()
    (trading / "pick_log.json").write_text(json.dumps({"picks": [{"id": "old"}]}), encoding="utf-8")
    (reports / "sess-test.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr("trading.learning_reset.TRADING_DIR", trading)
    monkeypatch.setattr("trading.learning_reset.QUANT_CACHE", quant)
    monkeypatch.setattr("trading.learning_reset.SESSION_REPORTS_DIR", reports)
    monkeypatch.setattr(
        "trading.learning_reset.clear_chroma_insights",
        lambda: {"deleted": True, "entries_before": 5},
    )

    out = run_learning_reset(confirm=True, wipe_session_reports=True)
    assert out["ok"] is True
    assert json.loads((trading / "pick_log.json").read_text())["picks"] == []
    assert not list(reports.glob("*.json"))
