"""Small JSON boundary for benchmark adapters such as EvoClaw."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from millracer.agent import RunResult


@dataclass(frozen=True, slots=True)
class BenchmarkRequest:
    task: str
    workspace: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def parse_benchmark_request(raw: str) -> BenchmarkRequest:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("benchmark request must be a JSON object")
    task = payload.get("task") or payload.get("prompt") or payload.get("instructions")
    if not isinstance(task, str) or not task.strip():
        raise ValueError(
            "benchmark request requires a non-empty task, prompt, or instructions field"
        )
    workspace = payload.get("workspace")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    return BenchmarkRequest(
        task=task,
        workspace=Path(workspace) if isinstance(workspace, str) and workspace else None,
        metadata=metadata,
    )


def render_benchmark_result(result: RunResult) -> str:
    return json.dumps(result.to_jsonable(), indent=2, sort_keys=True)
