"""Small JSON boundary for external Millracer callers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from millracer.agent import RunResult
from millracer.intake import normalize_intake_kind
from millracer.scope import ScopedWorkItem


@dataclass(frozen=True, slots=True)
class BenchmarkRequest:
    task: str
    workspace: Path | None = None
    intake_kind: str | None = None
    scoped_work_item: ScopedWorkItem | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def parse_benchmark_request(raw: str) -> BenchmarkRequest:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("external request must be a JSON object")
    task = payload.get("task") or payload.get("prompt") or payload.get("instructions")
    if not isinstance(task, str) or not task.strip():
        raise ValueError(
            "external request requires a non-empty task, prompt, or instructions field"
        )
    workspace = payload.get("workspace")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    scoped_payload = (
        payload.get("scoped_work_item")
        or payload.get("work_item")
        or payload.get("scope")
        or metadata.get("scoped_work_item")
    )
    intake_kind = normalize_intake_kind(
        payload.get("intake_kind") or metadata.get("intake_kind"),
        allow_auto=False,
    )
    return BenchmarkRequest(
        task=task,
        workspace=Path(workspace) if isinstance(workspace, str) and workspace else None,
        intake_kind=None if intake_kind is None else intake_kind.value,
        scoped_work_item=ScopedWorkItem.from_payload(scoped_payload),
        metadata=metadata,
    )


def render_benchmark_result(result: RunResult) -> str:
    return json.dumps(result.to_jsonable(), indent=2, sort_keys=True)
