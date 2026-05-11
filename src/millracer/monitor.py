"""Millrace daemon status polling and terminal-event classification."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MonitorEvent:
    kind: str
    workspace: str
    reason: str


def classify_status(payload: dict[str, Any]) -> MonitorEvent | None:
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

    if _has_zero_work(payload) and str(payload.get("active_stage") or "none") == "none":
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

    def wait(self, *, timeout_seconds: float) -> MonitorEvent:
        deadline = time.monotonic() + timeout_seconds
        last_status: dict[str, Any] | None = None
        while True:
            last_status = self.status_loader()
            event = classify_status(last_status)
            if event is not None:
                return event
            if time.monotonic() >= deadline:
                workspace = str(last_status.get("workspace") or "")
                raise TimeoutError(f"timed out waiting for Millrace daemon event in {workspace}")
            self.sleep(self.poll_interval_seconds)


def _has_zero_work(payload: dict[str, Any]) -> bool:
    keys = (
        "active_run_count",
        "execution_queue_depth",
        "planning_queue_depth",
        "learning_queue_depth",
    )
    return all(_int(payload.get(key)) == 0 for key in keys)


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
