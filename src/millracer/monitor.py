"""Millrace daemon status polling and terminal-event classification."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MonitorEvent:
    kind: str
    workspace: str
    reason: str


def classify_status(
    payload: dict[str, Any],
    *,
    notify_terminal_stages: bool = True,
) -> MonitorEvent | None:
    workspace = str(payload.get("workspace") or "")
    failure_class = payload.get("current_failure_class")
    if payload.get("blocked_idle") is True or failure_class:
        return MonitorEvent(
            kind="blocked",
            workspace=workspace,
            reason=str(failure_class or "blocked idle"),
        )

    if payload.get("process_running") is False and _queued_work(payload) > 0:
        stale = payload.get("runtime_ownership_lock") == "stale"
        reason = "daemon stopped with queued work"
        if stale:
            reason += " and stale runtime ownership lock"
        return MonitorEvent(kind="restart_needed", workspace=workspace, reason=reason)

    planning_marker = str(payload.get("planning_status_marker") or "")
    if planning_marker.strip() == "### ARBITER_COMPLETE":
        return MonitorEvent(kind="arbiter_complete", workspace=workspace, reason="arbiter marker")

    if payload.get("closure_target_root_spec_id") and payload.get("closure_target_open") is False:
        return MonitorEvent(
            kind="arbiter_complete",
            workspace=workspace,
            reason="closure target closed",
        )

    execution_marker = str(payload.get("execution_status_marker") or "")
    if (
        notify_terminal_stages
        and execution_marker.strip() == "### UPDATE_COMPLETE"
        and not _is_globally_drained(payload)
    ):
        return MonitorEvent(
            kind="stage_progress",
            workspace=workspace,
            reason="updater update complete",
        )

    if _is_globally_drained(payload):
        return MonitorEvent(kind="complete", workspace=workspace, reason="daemon idle with no work")

    if payload.get("process_running") is False and _int(payload.get("active_run_count")) > 0:
        return MonitorEvent(
            kind="crashed",
            workspace=workspace,
            reason="daemon stopped with active runs",
        )

    return None


@dataclass(slots=True)
class DaemonMonitor:
    status_loader: Callable[[], dict[str, Any]]
    poll_interval_seconds: float = 2.0
    sleep: Callable[[float], None] = time.sleep
    notify_terminal_stages: bool = True
    _last_progress_key: tuple[str, str, str, str, str, str] | None = field(
        default=None,
        init=False,
    )

    def wait(self, *, timeout_seconds: float) -> MonitorEvent:
        deadline = time.monotonic() + timeout_seconds
        last_status: dict[str, Any] | None = None
        while True:
            last_status = self.status_loader()
            event = classify_status(
                last_status,
                notify_terminal_stages=self.notify_terminal_stages,
            )
            if event is not None:
                if event.kind == "stage_progress" and self._already_seen_progress(
                    last_status,
                    event,
                ):
                    event = None
                else:
                    return event
            else:
                self._last_progress_key = None
            if time.monotonic() >= deadline:
                workspace = str(last_status.get("workspace") or "")
                raise TimeoutError(f"timed out waiting for Millrace daemon event in {workspace}")
            self.sleep(self.poll_interval_seconds)

    def _already_seen_progress(self, payload: dict[str, Any], event: MonitorEvent) -> bool:
        key = (
            event.kind,
            event.workspace,
            event.reason,
            str(payload.get("active_work_item_id") or ""),
            str(_queued_work(payload)),
            str(payload.get("closure_target_root_spec_id") or ""),
        )
        if key == self._last_progress_key:
            return True
        self._last_progress_key = key
        return False


def _has_zero_work(payload: dict[str, Any]) -> bool:
    keys = (
        "active_run_count",
        "execution_queue_depth",
        "planning_queue_depth",
        "learning_queue_depth",
    )
    return all(_int(payload.get(key)) == 0 for key in keys)


def _is_globally_drained(payload: dict[str, Any]) -> bool:
    if not _has_zero_work(payload):
        return False
    if str(payload.get("active_stage") or "none") != "none":
        return False
    return payload.get("closure_target_open") is not True


def _queued_work(payload: dict[str, Any]) -> int:
    return sum(
        _int(payload.get(key))
        for key in (
            "execution_queue_depth",
            "planning_queue_depth",
            "learning_queue_depth",
        )
    )


def _int(value: object) -> int:
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0
