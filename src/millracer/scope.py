"""Structured scoped-work metadata shared by benchmark adapters and Millrace intake."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ScopedWorkItem:
    """One selected queue item that Millracer is allowed to delegate."""

    item_id: str
    title: str | None = None
    source_queue: str | None = None
    spec_path: str | None = None
    completion_ref: str | None = None
    constraints: tuple[str, ...] = ()

    @classmethod
    def from_payload(cls, payload: object) -> ScopedWorkItem | None:
        if not isinstance(payload, dict):
            return None
        item_id = payload.get("item_id") or payload.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            return None
        raw_constraints = payload.get("constraints")
        constraints = (
            tuple(
                item.strip()
                for item in raw_constraints
                if isinstance(item, str) and item.strip()
            )
            if isinstance(raw_constraints, list)
            else ()
        )
        return cls(
            item_id=item_id.strip(),
            title=_optional_string(payload.get("title")),
            source_queue=_optional_string(payload.get("source_queue")),
            spec_path=_optional_string(payload.get("spec_path")),
            completion_ref=_optional_string(payload.get("completion_ref")),
            constraints=constraints,
        )

    def to_jsonable(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "source_queue": self.source_queue,
            "spec_path": self.spec_path,
            "completion_ref": self.completion_ref,
            "constraints": list(self.constraints),
        }


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
