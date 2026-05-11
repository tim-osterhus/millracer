from millracer.monitor import DaemonMonitor, MonitorEvent, classify_status


def test_classify_status_detects_arbiter_complete_marker() -> None:
    event = classify_status(
        {
            "workspace": "/tmp/ws",
            "process_running": True,
            "planning_status_marker": "### ARBITER_COMPLETE",
            "active_run_count": 0,
        }
    )

    assert event == MonitorEvent(
        kind="arbiter_complete",
        workspace="/tmp/ws",
        reason="arbiter marker",
    )


def test_classify_status_detects_closed_closure_target() -> None:
    event = classify_status(
        {
            "workspace": "/tmp/ws",
            "process_running": True,
            "closure_target_root_spec_id": "spec-001",
            "closure_target_open": False,
            "active_run_count": 0,
        }
    )

    assert event == MonitorEvent(
        kind="arbiter_complete",
        workspace="/tmp/ws",
        reason="closure target closed",
    )


def test_classify_status_detects_blocked_runtime() -> None:
    event = classify_status(
        {
            "workspace": "/tmp/ws",
            "blocked_idle": True,
            "current_failure_class": "runner_timeout",
        }
    )

    assert event == MonitorEvent(kind="blocked", workspace="/tmp/ws", reason="runner_timeout")


def test_classify_status_detects_running_daemon_with_drained_work() -> None:
    event = classify_status(
        {
            "workspace": "/tmp/ws",
            "process_running": True,
            "active_stage": "none",
            "active_run_count": 0,
            "execution_queue_depth": 0,
            "planning_queue_depth": 0,
            "learning_queue_depth": 0,
            "execution_status_marker": "### UPDATE_COMPLETE",
        }
    )

    assert event == MonitorEvent(kind="complete", workspace="/tmp/ws", reason="daemon idle with no work")


def test_monitor_wait_returns_first_terminal_event() -> None:
    statuses = iter(
        [
            {"workspace": "/tmp/ws", "process_running": True, "active_run_count": 1},
            {"workspace": "/tmp/ws", "planning_status_marker": "### ARBITER_COMPLETE"},
        ]
    )
    monitor = DaemonMonitor(
        status_loader=lambda: next(statuses),
        poll_interval_seconds=0.0,
        sleep=lambda _: None,
    )

    assert monitor.wait(timeout_seconds=1).kind == "arbiter_complete"
