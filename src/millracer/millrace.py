"""Millrace CLI controller for delegated Millracer runs."""

from __future__ import annotations

import json
import re
import subprocess
from contextlib import suppress
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from millracer.command import CommandExecutor, ProcessHandle, SubprocessExecutor, require_success
from millracer.scope import ScopedWorkItem


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

    def enqueue_task(self, task: str, scoped_work_item: ScopedWorkItem | None = None) -> Path:
        task_path = self._write_task_file(task, scoped_work_item=scoped_work_item)
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
        self.clear_stale_state_if_needed()
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

    def restart_daemon(self) -> ProcessHandle:
        return self.start_daemon()

    def stop_daemon(self) -> None:
        require_success(
            self.executor.run(
                (self.config.command, "control", "stop", "--workspace", str(self.workspace)),
                cwd=self.cwd or self.workspace,
            )
        )
        self._wait_for_daemon_exit()
        self.clear_stale_state_if_needed()

    def clear_stale_state_if_needed(self) -> bool:
        try:
            payload = self.status()
        except Exception:
            return False
        if payload.get("runtime_ownership_lock") != "stale":
            return False
        self.clear_stale_state()
        return True

    def clear_stale_state(self) -> None:
        require_success(
            self.executor.run(
                (
                    self.config.command,
                    "control",
                    "clear-stale-state",
                    "--workspace",
                    str(self.workspace),
                ),
                cwd=self.cwd or self.workspace,
            )
        )

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

    def _wait_for_daemon_exit(self) -> None:
        if self._daemon is None or self._daemon.poll() is not None:
            return
        try:
            self._daemon.wait(timeout=30.0)
            return
        except (TimeoutError, subprocess.TimeoutExpired):
            pass
        with suppress(ProcessLookupError):
            self._daemon.terminate()
        try:
            self._daemon.wait(timeout=5.0)
            return
        except (TimeoutError, subprocess.TimeoutExpired):
            pass
        with suppress(ProcessLookupError):
            self._daemon.kill()
        with suppress(TimeoutError, subprocess.TimeoutExpired):
            self._daemon.wait(timeout=5.0)

    def _write_task_file(
        self,
        task: str,
        *,
        scoped_work_item: ScopedWorkItem | None = None,
    ) -> Path:
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
                scoped_work_item=scoped_work_item,
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
    scoped_work_item: ScopedWorkItem | None = None,
) -> str:
    scoped_work = _render_scoped_work(scoped_work_item)
    return f"""\
# {title}

Task-ID: {task_id}
Title: {title}
Summary: {summary}
Created-At: {created_at}
Created-By: millracer

{scoped_work}
Target-Paths:
- .

Acceptance:
- Complete the requested benchmark task or report the concrete blocker.
- If this task came from an external queue, complete only the selected scoped work item.

Required-Checks:
- Run the relevant verification for the changed work, or explain why no check was possible.

References:
- queued by Millracer

Scope Contract:
- Treat this document as one scoped work item.
- Do not batch independent queue items into this work item.
- Do not create completion markers, commits, tags, or external signals for any
  work item other than the scoped item named here.
- If the prompt describes a streaming queue but does not identify one selected
  item, report the missing scope instead of processing the whole queue.

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


def _render_scoped_work(scoped_work_item: ScopedWorkItem | None) -> str:
    if scoped_work_item is None:
        return "Scoped-Work:\n- Item-ID: none\n"
    lines = [
        "Scoped-Work:",
        f"- Item-ID: {scoped_work_item.item_id}",
    ]
    if scoped_work_item.title:
        lines.append(f"- Title: {scoped_work_item.title}")
    if scoped_work_item.source_queue:
        lines.append(f"- Source-Queue: {scoped_work_item.source_queue}")
    if scoped_work_item.spec_path:
        lines.append(f"- Spec-Path: {scoped_work_item.spec_path}")
    if scoped_work_item.completion_ref:
        lines.append(f"- Completion-Ref: {scoped_work_item.completion_ref}")
    for constraint in scoped_work_item.constraints:
        lines.append(f"- Constraint: {constraint}")
    return "\n".join(lines) + "\n"
