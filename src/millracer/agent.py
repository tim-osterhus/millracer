"""Outer Millracer agent orchestration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from millracer.decision import Decision, parse_decision
from millracer.intake import IntakeKind, choose_intake_kind
from millracer.monitor import MonitorEvent
from millracer.prompts import decision_prompt, direct_prompt, finalization_prompt, progress_prompt
from millracer.scope import ScopedWorkItem


class PiLike(Protocol):
    def complete(self, prompt: str, *, cwd: Path, timeout_seconds: int | None = None) -> str: ...


class MillraceLike(Protocol):
    def initialize(self) -> None: ...

    def validate(self) -> None: ...

    def enqueue(
        self,
        intake_kind: IntakeKind | str,
        task: str,
        scoped_work_item: ScopedWorkItem | None = None,
    ) -> Path: ...

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
    intake: str = "auto"
    notify_terminal_stages: bool = True


@dataclass(frozen=True, slots=True)
class RunResult:
    route: str
    decision: Decision
    output: str
    intake_kind: str | None = None
    intake_signals: tuple[str, ...] = ()
    event: MonitorEvent | None = None
    task_path: Path | None = None
    status: dict[str, object] | None = None
    warnings: tuple[str, ...] = ()
    scoped_work_item: ScopedWorkItem | None = None
    progress_events: tuple[MonitorEvent, ...] = ()
    outcome: str = "incomplete"
    scoped_completion: bool = False
    completion_evidence: tuple[dict[str, str], ...] = ()

    def to_jsonable(self) -> dict[str, object]:
        return {
            "route": self.route,
            "intake_kind": self.intake_kind,
            "intake_signals": list(self.intake_signals),
            "decision": {
                "route": self.decision.route,
                "intake_kind": self.decision.intake_kind,
                "why": self.decision.why,
                "mode": self.decision.mode,
                "custom_loop_needed": self.decision.custom_loop_needed,
                "signals": list(self.decision.signals or self.intake_signals),
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
            "outcome": self.outcome,
            "scoped_completion": self.scoped_completion,
            "completion_evidence": list(self.completion_evidence),
            "scoped_work_item": None
            if self.scoped_work_item is None
            else self.scoped_work_item.to_jsonable(),
            "progress_events": [
                {
                    "kind": event.kind,
                    "workspace": event.workspace,
                    "reason": event.reason,
                }
                for event in self.progress_events
            ],
        }


@dataclass(slots=True)
class MillracerAgent:
    pi: PiLike
    millrace: MillraceLike
    monitor: MonitorLike

    def run(self, task: str, *, options: RunOptions) -> RunResult:
        decision = self._decision_for(task, options=options)
        intake_decision = choose_intake_kind(task, requested=options.intake, decision=decision)
        intake_kind = intake_decision.intake_kind.value
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
                intake_kind=intake_kind,
                intake_signals=intake_decision.signals,
                outcome="completed",
                warnings=warnings,
                scoped_work_item=options.scoped_work_item,
            )

        set_mode = getattr(self.millrace, "set_mode", None)
        if callable(set_mode):
            set_mode(decision.mode)
        self.millrace.initialize()
        self.millrace.validate()
        existing_blocked = self._existing_blocked_scoped_result(
            task=task,
            decision=decision,
            intake_kind=intake_kind,
            intake_signals=intake_decision.signals,
            warnings=warnings,
            options=options,
        )
        if existing_blocked is not None:
            return existing_blocked

        task_path = _existing_scoped_intake_path(self.millrace, options.scoped_work_item)
        if task_path is None:
            task_path = self.millrace.enqueue(
                intake_decision.intake_kind,
                task,
                scoped_work_item=options.scoped_work_item,
            )
        self.millrace.start_daemon()
        event, progress_events = self._wait_for_terminal_event(
            task=task,
            intake_kind=intake_kind,
            options=options,
        )
        if not options.keep_daemon:
            self.millrace.stop_daemon()
        status = self.millrace.status()
        outcome, scoped_completion, completion_evidence = _outcome_for_event(event)
        output = self.pi.complete(
            finalization_prompt(
                task=task,
                workspace=str(options.workspace),
                route="millrace",
                intake_kind=intake_kind,
                outcome=outcome,
                scoped_completion=scoped_completion,
                completion_evidence_json=json.dumps(
                    list(completion_evidence),
                    indent=2,
                    sort_keys=True,
                ),
                event_kind=event.kind,
                event_reason=event.reason,
                status_json=json.dumps(status, indent=2, sort_keys=True),
                warnings=warnings,
                scoped_work_json=_scoped_work_json(options.scoped_work_item),
                progress_events_json=json.dumps(
                    [
                        {
                            "kind": progress_event.kind,
                            "workspace": progress_event.workspace,
                            "reason": progress_event.reason,
                        }
                        for progress_event in progress_events
                    ],
                    indent=2,
                    sort_keys=True,
                ),
            ),
            cwd=options.cwd,
            timeout_seconds=options.pi_timeout_seconds,
        )
        return RunResult(
            route="millrace",
            decision=decision,
            output=output,
            intake_kind=intake_kind,
            intake_signals=intake_decision.signals,
            event=event,
            task_path=task_path,
            status=status,
            warnings=warnings,
            scoped_work_item=options.scoped_work_item,
            progress_events=progress_events,
            outcome=outcome,
            scoped_completion=scoped_completion,
            completion_evidence=completion_evidence,
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

    def _wait_for_terminal_event(
        self,
        *,
        task: str,
        intake_kind: str,
        options: RunOptions,
    ) -> tuple[MonitorEvent, tuple[MonitorEvent, ...]]:
        restarts = 0
        progress_events: list[MonitorEvent] = []
        while True:
            event = self.monitor.wait(timeout_seconds=options.daemon_timeout_seconds)
            if event.kind == "stage_progress":
                if options.notify_terminal_stages:
                    progress_events.append(event)
                    self.pi.complete(
                        progress_prompt(
                            task=task,
                            workspace=str(options.workspace),
                            intake_kind=intake_kind,
                            event_kind=event.kind,
                            event_reason=event.reason,
                        ),
                        cwd=options.cwd,
                        timeout_seconds=options.pi_timeout_seconds,
                    )
                continue
            if event.kind != "restart_needed":
                return event, tuple(progress_events)
            if restarts >= options.max_daemon_restarts:
                return event, tuple(progress_events)
            self.millrace.restart_daemon()
            restarts += 1

    def _existing_blocked_scoped_result(
        self,
        *,
        task: str,
        decision: Decision,
        intake_kind: str,
        intake_signals: tuple[str, ...],
        warnings: tuple[str, ...],
        options: RunOptions,
    ) -> RunResult | None:
        task_path = _existing_scoped_intake_path(self.millrace, options.scoped_work_item)
        if task_path is None:
            return None
        status = self.millrace.status()
        failure_class = status.get("current_failure_class")
        latest_error = status.get("latest_runtime_error_report_path")
        if not failure_class and not latest_error:
            return None
        reason = str(failure_class or "latest runtime error")
        event = MonitorEvent(
            kind="blocked",
            workspace=str(status.get("workspace") or options.workspace),
            reason=reason,
        )
        output = self.pi.complete(
            finalization_prompt(
                task=task,
                workspace=str(options.workspace),
                route="millrace",
                intake_kind=intake_kind,
                outcome="blocked",
                scoped_completion=False,
                completion_evidence_json="[]",
                event_kind=event.kind,
                event_reason=event.reason,
                status_json=json.dumps(status, indent=2, sort_keys=True),
                warnings=warnings,
                scoped_work_json=_scoped_work_json(options.scoped_work_item),
                progress_events_json="[]",
            ),
            cwd=options.cwd,
            timeout_seconds=options.pi_timeout_seconds,
        )
        return RunResult(
            route="millrace",
            decision=decision,
            output=output,
            intake_kind=intake_kind,
            intake_signals=intake_signals,
            event=event,
            task_path=task_path,
            status=status,
            warnings=warnings,
            scoped_work_item=options.scoped_work_item,
            outcome="blocked",
            scoped_completion=False,
        )


def _warnings_for_decision(decision: Decision) -> tuple[str, ...]:
    if not decision.custom_loop_needed:
        return ()
    return (
        "Pi indicated that a custom Millrace loop may be needed; Millracer will still use "
        f"`{decision.mode}` unless the caller passes a different --millrace-mode.",
    )


def _existing_scoped_intake_path(
    millrace: MillraceLike,
    scoped_work_item: ScopedWorkItem | None,
) -> Path | None:
    if scoped_work_item is None:
        return None
    finder = getattr(millrace, "find_existing_scoped_intake", None)
    if not callable(finder):
        return None
    found = finder(scoped_work_item)
    return found if isinstance(found, Path) else None


def _outcome_for_event(event: MonitorEvent) -> tuple[str, bool, tuple[dict[str, str], ...]]:
    if event.kind in {"arbiter_complete", "scoped_complete"}:
        return (
            "completed",
            True,
            (
                {
                    "kind": event.kind,
                    "workspace": event.workspace,
                    "reason": event.reason,
                },
            ),
        )
    if event.kind == "blocked":
        return "blocked", False, ()
    if event.kind == "restart_needed":
        return "restart_needed", False, ()
    if event.kind == "crashed":
        return "crashed", False, ()
    return "incomplete", False, ()


def _scoped_work_json(scoped_work_item: ScopedWorkItem | None) -> str | None:
    if scoped_work_item is None:
        return None
    return json.dumps(scoped_work_item.to_jsonable(), indent=2, sort_keys=True)
