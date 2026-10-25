"""Clear past session history without touching active desks."""
from __future__ import annotations


def test_delete_session_history_skips_active(tmp_path, monkeypatch):
    from trading import session_autopilot as sa
    from trading import session_history as sh
    from trading import session_report as sr

    sessions_path = tmp_path / "sessions.json"
    events_path = tmp_path / "session_events.json"
    reports_dir = tmp_path / "session_reports"
    reports_dir.mkdir()
    monkeypatch.setattr(sa, "SESSION_PATH", sessions_path)
    monkeypatch.setattr(sh, "EVENTS_PATH", events_path)
    monkeypatch.setattr(sr, "REPORTS_DIR", reports_dir)

    sa._save_store({
        "active_session_id": "sess-active",
        "active_session_ids": ["sess-active"],
        "sessions": [
            {"id": "sess-active", "status": "active", "pick_mode": "agent_auto"},
            {"id": "sess-old", "status": "stopped", "pick_mode": "curated_list"},
            {"id": "sess-gone", "status": "stopped", "pick_mode": "agent_auto"},
        ],
    })
    (reports_dir / "sess-old.json").write_text('{"session_id":"sess-old"}', encoding="utf-8")
    (reports_dir / "sess-gone.json").write_text('{"session_id":"sess-gone"}', encoding="utf-8")
    sh._save_events_store({
        "events": [
            {"session_id": "sess-active", "at": "2026-10-20T01:00:00+00:00"},
            {"session_id": "sess-old", "at": "2026-10-19T01:00:00+00:00"},
            {"session_id": "sess-gone", "at": "2026-10-18T01:00:00+00:00"},
        ]
    })

    out = sr.delete_session_history(session_ids=["sess-old", "sess-active"])
    assert out["removed_sessions"] == 1
    assert out["skipped_active"] == ["sess-active"]
    store = sa._load_store()
    ids = {s["id"] for s in store["sessions"]}
    assert ids == {"sess-active", "sess-gone"}
    assert not (reports_dir / "sess-old.json").exists()
    assert (reports_dir / "sess-gone.json").exists()

    out_all = sr.delete_session_history(clear_all=True)
    assert out_all["removed_sessions"] == 1
    assert out_all["skipped_active"] == ["sess-active"]
    store = sa._load_store()
    assert [s["id"] for s in store["sessions"]] == ["sess-active"]
    events = sh._load_events_store()["events"]
    assert [e["session_id"] for e in events] == ["sess-active"]
