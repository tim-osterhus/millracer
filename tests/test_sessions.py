from __future__ import annotations

from pathlib import Path

from millracer.sessions import SessionStore


def test_session_store_remembers_selected_workspace(tmp_path: Path) -> None:
    store = SessionStore(path=tmp_path / "sessions.json")
    session = store.get_or_create("local")

    store.update_selection(
        session.session_id,
        workspace_id="millrace-os",
        mode="learning_codex",
    )
    loaded = store.get_or_create("local")

    assert loaded.selected_workspace_id == "millrace-os"
    assert loaded.selected_mode == "learning_codex"


def test_session_store_tracks_recent_request_ids_without_runtime_truth(tmp_path: Path) -> None:
    store = SessionStore(path=tmp_path / "sessions.json")
    session = store.get_or_create("mission-control")

    store.record_request(
        session.session_id,
        request_id="req-001",
        warning_codes=("workspace_stale",),
    )
    loaded = store.get_or_create("mission-control")
    raw = (tmp_path / "sessions.json").read_text(encoding="utf-8")

    assert loaded.recent_request_ids == ("req-001",)
    assert loaded.last_warning_codes == ("workspace_stale",)
    assert "queue_depth" not in raw
    assert "terminal_outcome" not in raw
    assert "trace" not in raw


def test_session_store_keeps_recent_request_ids_bounded(tmp_path: Path) -> None:
    store = SessionStore(path=tmp_path / "sessions.json", max_recent_requests=2)
    session = store.get_or_create("local")

    store.record_request(session.session_id, request_id="req-001")
    store.record_request(session.session_id, request_id="req-002")
    store.record_request(session.session_id, request_id="req-003")
    loaded = store.get_or_create("local")

    assert loaded.recent_request_ids == ("req-002", "req-003")


def test_session_store_lists_sessions(tmp_path: Path) -> None:
    store = SessionStore(path=tmp_path / "sessions.json")
    store.get_or_create("local")
    store.get_or_create("mission-control")

    sessions = store.list_sessions()

    assert tuple(session.client_name for session in sessions) == ("local", "mission-control")
