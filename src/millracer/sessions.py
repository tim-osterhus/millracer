"""Minimal Millracer operator session persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SessionRecord:
    session_id: str
    client_name: str
    selected_workspace_id: str | None = None
    selected_mode: str | None = None
    recent_request_ids: tuple[str, ...] = ()
    last_warning_codes: tuple[str, ...] = ()

    def to_jsonable(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "client_name": self.client_name,
            "selected_workspace_id": self.selected_workspace_id,
            "selected_mode": self.selected_mode,
            "recent_request_ids": list(self.recent_request_ids),
            "last_warning_codes": list(self.last_warning_codes),
        }


@dataclass(slots=True)
class SessionStore:
    path: Path
    max_recent_requests: int = 20

    def get_or_create(self, client_name: str) -> SessionRecord:
        sessions = self._load()
        for session in sessions.values():
            if session.client_name == client_name:
                return session
        session = SessionRecord(session_id=client_name, client_name=client_name)
        sessions[session.session_id] = session
        self._save(sessions)
        return session

    def update_selection(
        self,
        session_id: str,
        *,
        workspace_id: str | None,
        mode: str | None,
    ) -> SessionRecord:
        sessions = self._load()
        session = sessions.get(session_id)
        if session is None:
            session = SessionRecord(session_id=session_id, client_name=session_id)
        updated = SessionRecord(
            session_id=session.session_id,
            client_name=session.client_name,
            selected_workspace_id=workspace_id,
            selected_mode=mode,
            recent_request_ids=session.recent_request_ids,
            last_warning_codes=session.last_warning_codes,
        )
        sessions[session_id] = updated
        self._save(sessions)
        return updated

    def record_request(
        self,
        session_id: str,
        *,
        request_id: str,
        warning_codes: tuple[str, ...] = (),
    ) -> SessionRecord:
        sessions = self._load()
        session = sessions.get(session_id)
        if session is None:
            session = SessionRecord(session_id=session_id, client_name=session_id)
        recent = (*session.recent_request_ids, request_id)[-self.max_recent_requests :]
        updated = SessionRecord(
            session_id=session.session_id,
            client_name=session.client_name,
            selected_workspace_id=session.selected_workspace_id,
            selected_mode=session.selected_mode,
            recent_request_ids=recent,
            last_warning_codes=warning_codes,
        )
        sessions[session_id] = updated
        self._save(sessions)
        return updated

    def list_sessions(self) -> tuple[SessionRecord, ...]:
        sessions = self._load()
        return tuple(session for _, session in sorted(sessions.items()))

    def _load(self) -> dict[str, SessionRecord]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        if not isinstance(payload, dict):
            return {}
        sessions: dict[str, SessionRecord] = {}
        for session_id, raw_session in payload.get("sessions", {}).items():
            if not isinstance(session_id, str) or not isinstance(raw_session, dict):
                continue
            sessions[session_id] = SessionRecord(
                session_id=session_id,
                client_name=_string_or(raw_session.get("client_name"), session_id),
                selected_workspace_id=_optional_string(
                    raw_session.get("selected_workspace_id")
                ),
                selected_mode=_optional_string(raw_session.get("selected_mode")),
                recent_request_ids=_tuple_strings(raw_session.get("recent_request_ids")),
                last_warning_codes=_tuple_strings(raw_session.get("last_warning_codes")),
            )
        return sessions

    def _save(self, sessions: dict[str, SessionRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sessions": {
                session_id: session.to_jsonable()
                for session_id, session in sorted(sessions.items())
            }
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _string_or(value: object, default: str) -> str:
    return _optional_string(value) or default


def _tuple_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
