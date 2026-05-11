"""Outer Millracer agent orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from millracer.decision import Decision, parse_decision
from millracer.monitor import MonitorEvent
from millracer.prompts import decision_prompt, direct_prompt, finalization_prompt
from millracer.scope import ScopedWorkItem


class PiLike(Protocol):
    def complete(self, prompt: str, *, cwd: Path, timeout_seconds: int | None = None) -> str: ...


class MillraceLike(Protocol):
    def initialize(self) -> None: ...

    def validate(self) -> None: ...

    def enqueue_task(self, task: str, scoped_work_item: ScopedWorkItem | None = None) -> Path: ...

    def start_daemon(self): ...

    def restart_daemon(self): ...

    def stop_daemon(self) -> None: ...

    def status(self) -> dict[str, object]: ...


class MonitorLike(Protocol):
    def wait(self, *, timeout_seconds: float) -> MonitorEvent: ...


@dataclass(frozen=True, slots=True)
class RunOptions:
    workspace: Path
    cwd: Path
    route: str = "auto"
    daemon_timeout_seconds: float = 7200.0
    pi_timeout_seconds: int | None = None
    keep_daemon: bool = False
    scoped_work_item: ScopedWorkItem | None = None
    max_daemon_restarts: int = 1


@dataclass(frozen=True, slots=True)
class RunResult:
    route: str
    decision: Decision
    output: str
    event: MonitorEvent | None = None
    task_path: Path | None = None
    status: dict[str, object] | None = None
    warnings: tuple[str, ...] = ()
    scoped_work_item: ScopedWorkItem | None = None

    def to_jsonable(self) -> dict[str, object]:
        return {
            "route": self.route,
            "decision": {
                "route": self.decision.route,
                "why": self.decision.why,
                "mode": self.decision.mode,
                "custom_loop_needed": self.decision.custom_loop_needed,
                "notes": self.decision.notes,
            },
            "output": self.output,
            "event": (
                None
                if self.event is None
                else {
                    "kind": self.event.kind,
                    "workspace": self.event.workspace,
                    "reason": self.event.reason,
                }
            ),
            "task_path": None if self.task_path is None else str(self.task_path),
            "status": self.status,
            "warnings": list(self.warnings),
            "scoped_work_item": None
            if self.scoped_work_item is None
            else self.scoped_work_item.to_jsonable(),
        }


@dataclass(slots=True)
class MillracerAgent:
    pi: PiLike
    millrace: MillraceLike
    monitor: MonitorLike

    def run(self, task: str, *, options: RunOptions) -> RunResult:
        decision = self._decision_for(task, options=options)
        warnings = _warnings_for_decision(decision)
        if decision.route == "direct":
            output = self.pi.complete(
                direct_prompt(task),
                cwd=options.cwd,
                timeout_seconds=options.pi_timeout_seconds,
            )
            return RunResult(
                route="direct",
                decision=decision,
                output=output,
                warnings=warnings,
                scoped_work_item=options.scoped_work_item,
            )

        set_mode = getattr(self.millrace, "set_mode", None)
        if callable(set_mode):
            set_mode(decision.mode)
        self.millrace.initialize()
        self.millrace.validate()
        task_path = self.millrace.enqueue_task(task, scoped_work_item=options.scoped_work_item)
        self.millrace.start_daemon()
        event = self._wait_for_terminal_event(options=options)
        if not options.keep_daemon:
            self.millrace.stop_daemon()
        status = self.millrace.status()
        output = self.pi.complete(
            finalization_prompt(
                task=task,
                workspace=str(options.workspace),
                event_kind=event.kind,
                event_reason=event.reason,
                status_json=json.dumps(status, indent=2, sort_keys=True),
                warnings=warnings,
            ),
            cwd=options.cwd,
            timeout_seconds=options.pi_timeout_seconds,
        )
        return RunResult(
            route="millrace",
            decision=decision,
            output=output,
            event=event,
            task_path=task_path,
            status=status,
            warnings=warnings,
            scoped_work_item=options.scoped_work_item,
        )

    def _decision_for(self, task: str, *, options: RunOptions) -> Decision:
        route = options.route.strip().lower()
        if route in {"direct", "millrace"}:
            return Decision(route=route, why=f"route forced by --route {route}")
        raw_decision = self.pi.complete(
            decision_prompt(task),
            cwd=options.cwd,
            timeout_seconds=options.pi_timeout_seconds,
        )
        return parse_decision(raw_decision)

    def _wait_for_terminal_event(self, *, options: RunOptions) -> MonitorEvent:
        restarts = 0
        while True:
            event = self.monitor.wait(timeout_seconds=options.daemon_timeout_seconds)
            if event.kind != "restart_needed":
                return event
            if restarts >= options.max_daemon_restarts:
                return event
            self.millrace.restart_daemon()
            restarts += 1


def _warnings_for_decision(decision: Decision) -> tuple[str, ...]:
    if not decision.custom_loop_needed:
        return ()
    return (
        "Pi indicated that a custom Millrace loop may be needed; Millracer will still use "
        f"`{decision.mode}` unless the caller passes a different --millrace-mode.",
    )
