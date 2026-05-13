"""Small JSON boundary for external Millracer callers."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from millracer.agent import RunResult
from millracer.intake import normalize_intake_kind
from millracer.ops_models import (
    SCHEMA_VERSION,
    OpsRequest,
    OpsResult,
    SourceRef,
    WorkspaceRef,
    render_ops_result,
)
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


def parse_legacy_request_as_ops(raw: str, *, request_id: str | None = None) -> OpsRequest:
    payload = json.loads(raw)
    request = parse_benchmark_request(raw)
    metadata = dict(request.metadata)
    metadata["legacy_request"] = payload if isinstance(payload, dict) else {}
    return OpsRequest(
        schema_version=SCHEMA_VERSION,
        request_id=request_id or f"req-legacy-{uuid4()}",
        action="enqueue",
        workspace_ref=WorkspaceRef(
            root_path=None if request.workspace is None else str(request.workspace),
        ),
        source=SourceRef(kind="benchmark_compat"),
        input={
            "kind": "legacy_benchmark",
            "text": request.task,
        },
        route_preference="millrace",
        intake_preference=request.intake_kind or "auto",
        scoped_work_item=request.scoped_work_item,
        metadata=metadata,
    )


def ops_result_to_legacy_json(result: OpsResult) -> str:
    return json.dumps(render_ops_result(result), indent=2, sort_keys=True)
