"""Millrace CLI controller for delegated Millracer runs."""

from __future__ import annotations

import json
import re
from contextlib import suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from millracer.command import CommandExecutor, ProcessHandle, SubprocessExecutor, require_success


@dataclass(frozen=True, slots=True)
class MillraceConfig:
    command: str = "millrace"
    mode: str = "default_pi"


@dataclass(slots=True)
class MillraceController:
    config: MillraceConfig = field(default_factory=MillraceConfig)
    executor: CommandExecutor = field(default_factory=SubprocessExecutor)
    workspace: Path = field(default_factory=Path.cwd)
    cwd: Path | None = None
    _daemon: ProcessHandle | None = None

    def set_mode(self, mode: str) -> None:
        self.config = replace(self.config, mode=mode)

    def initialize(self) -> None:
        require_success(
            self.executor.run(
                (self.config.command, "init", "--workspace", str(self.workspace)),
                cwd=self.cwd or self.workspace,
            )
        )

    def validate(self) -> None:
        require_success(
            self.executor.run(
                (
                    self.config.command,
                    "compile",
                    "validate",
                    "--workspace",
                    str(self.workspace),
                    "--mode",
                    self.config.mode,
                ),
                cwd=self.cwd or self.workspace,
            )
        )

    def enqueue_task(self, task: str) -> Path:
        task_path = self._write_task_file(task)
        require_success(
            self.executor.run(
                (
                    self.config.command,
                    "queue",
                    "add-task",
                    str(task_path),
                    "--workspace",
                    str(self.workspace),
                ),
                cwd=self.cwd or self.workspace,
            )
        )
        return task_path

    def start_daemon(self) -> ProcessHandle:
        self._daemon = self.executor.start(
            (
                self.config.command,
                "run",
                "daemon",
                "--workspace",
                str(self.workspace),
                "--mode",
                self.config.mode,
                "--monitor",
                "none",
            ),
            cwd=self.cwd or self.workspace,
        )
        return self._daemon

    def stop_daemon(self) -> None:
        require_success(
            self.executor.run(
                (self.config.command, "control", "stop", "--workspace", str(self.workspace)),
                cwd=self.cwd or self.workspace,
            )
        )
        if self._daemon is not None and self._daemon.poll() is None:
            with suppress(ProcessLookupError):
                self._daemon.terminate()

    def status(self) -> dict[str, Any]:
        result = require_success(
            self.executor.run(
                (
                    self.config.command,
                    "status",
                    "--workspace",
                    str(self.workspace),
                    "--format",
                    "json",
                ),
                cwd=self.cwd or self.workspace,
            )
        )
        payload = json.loads(result.stdout or "{}")
        if not isinstance(payload, dict):
            raise ValueError("millrace status JSON must be an object")
        return payload

    def _write_task_file(self, task: str) -> Path:
        now = datetime.now(UTC)
        task_id = _task_id(task, now)
        intake_dir = self.workspace / ".millracer" / "intake"
        intake_dir.mkdir(parents=True, exist_ok=True)
        task_path = intake_dir / f"{task_id}.md"
        task_path.write_text(
            render_task_document(
                task_id=task_id,
                title=_title_from_task(task),
                summary=task.strip(),
                created_at=now.isoformat(),
            ),
            encoding="utf-8",
        )
        return task_path


def render_task_document(
    *,
    task_id: str,
    title: str,
    summary: str,
    created_at: str,
) -> str:
    return f"""\
# {title}

Task-ID: {task_id}
Title: {title}
Summary: {summary}
Created-At: {created_at}
Created-By: millracer

Target-Paths:
- .

Acceptance:
- Complete the requested benchmark task or report the concrete blocker.

Required-Checks:
- Run the relevant verification for the changed work, or explain why no check was possible.

References:
- queued by Millracer

Risk:
- Benchmark adapter task may need follow-up inspection by the outer Millracer agent.
"""


def _task_id(task: str, now: datetime) -> str:
    return f"millracer-{now.strftime('%Y%m%d%H%M%S')}-{_slug(task)[:32]}"


def _title_from_task(task: str) -> str:
    first_line = task.strip().splitlines()[0] if task.strip() else "Millracer task"
    return first_line[:80].strip() or "Millracer task"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "task"
