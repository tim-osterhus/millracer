from pathlib import Path

from millracer.agent import MillracerAgent, RunOptions
from millracer.decision import Decision
from millracer.monitor import MonitorEvent
from millracer.scope import ScopedWorkItem


class FakePi:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str, *, cwd: Path, timeout_seconds: int | None = None) -> str:
        self.prompts.append(prompt)
        if "Return only JSON" in prompt:
            return '{"decision": "millrace", "why": "needs durable execution"}'
        if "Millrace emitted this terminal event" in prompt:
            return "final answer"
        return "direct answer"


class FakeMillrace:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def initialize(self) -> None:
        self.calls.append("initialize")

    def validate(self) -> None:
        self.calls.append("validate")

    def enqueue(self, intake_kind, task: str, scoped_work_item=None) -> Path:  # noqa: ANN001
        self.calls.append(f"enqueue:{intake_kind}:{task}")
        return Path(f"/tmp/ws/.millracer/intake/{intake_kind}.md")

    def start_daemon(self):  # noqa: ANN201
        self.calls.append("start_daemon")
        return object()

    def restart_daemon(self):  # noqa: ANN201
        self.calls.append("restart_daemon")
        return object()

    def stop_daemon(self) -> None:
        self.calls.append("stop_daemon")

    def status(self) -> dict[str, object]:
        self.calls.append("status")
        return {"workspace": "/tmp/ws"}


class FakeMonitor:
    def wait(self, *, timeout_seconds: float) -> MonitorEvent:
        return MonitorEvent(kind="arbiter_complete", workspace="/tmp/ws", reason="test")


def test_agent_routes_auto_decision_into_millrace_flow() -> None:
    pi = FakePi()
    millrace = FakeMillrace()
    agent = MillracerAgent(pi=pi, millrace=millrace, monitor=FakeMonitor())

    result = agent.run(
        "Implement a multi-stage refactor",
        options=RunOptions(workspace=Path("/tmp/ws"), cwd=Path("/tmp/ws")),
    )

    assert result.route == "millrace"
    assert result.intake_kind == "probe"
    assert result.outcome == "completed"
    assert result.scoped_completion is True
    assert result.completion_evidence == (
        {"kind": "arbiter_complete", "reason": "test", "workspace": "/tmp/ws"},
    )
    assert result.decision == Decision(route="millrace", why="needs durable execution")
    assert result.output == "final answer"
    assert millrace.calls == [
        "initialize",
        "validate",
        "enqueue:probe:Implement a multi-stage refactor",
        "start_daemon",
        "stop_daemon",
        "status",
    ]


def test_agent_surfaces_custom_loop_warning() -> None:
    pi = FakePi()
    millrace = FakeMillrace()
    agent = MillracerAgent(pi=pi, millrace=millrace, monitor=FakeMonitor())

    result = agent.run(
        "Implement a multi-stage refactor",
        options=RunOptions(workspace=Path("/tmp/ws"), cwd=Path("/tmp/ws"), route="millrace"),
    )

    assert result.warnings == ()


def test_agent_warns_when_decision_requests_custom_loop() -> None:
    class CustomLoopPi(FakePi):
        def complete(self, prompt: str, *, cwd: Path, timeout_seconds: int | None = None) -> str:
            self.prompts.append(prompt)
            if "Return only JSON" in prompt:
                return (
                    '{"decision": "millrace", "why": "needs special topology", '
                    '"custom_loop_needed": true, "mode": "default_pi"}'
                )
            return "final answer"

    pi = CustomLoopPi()
    millrace = FakeMillrace()
    agent = MillracerAgent(pi=pi, millrace=millrace, monitor=FakeMonitor())

    result = agent.run(
        "Use a custom workflow",
        options=RunOptions(workspace=Path("/tmp/ws"), cwd=Path("/tmp/ws")),
    )

    assert result.warnings
    assert "custom Millrace loop" in result.warnings[0]


def test_agent_uses_forced_intake_override() -> None:
    pi = FakePi()
    millrace = FakeMillrace()
    agent = MillracerAgent(pi=pi, millrace=millrace, monitor=FakeMonitor())

    result = agent.run(
        "Update behavior in a large pre-existing codebase.",
        options=RunOptions(
            workspace=Path("/tmp/ws"),
            cwd=Path("/tmp/ws"),
            route="millrace",
            intake="task",
        ),
    )

    assert result.intake_kind == "task"
    assert "enqueue:task:Update behavior in a large pre-existing codebase." in millrace.calls


def test_agent_restarts_daemon_when_monitor_reports_restart_needed() -> None:
    class RestartMonitor:
        def __init__(self) -> None:
            self.events = [
                MonitorEvent(
                    kind="restart_needed",
                    workspace="/tmp/ws",
                    reason="daemon stopped with queued work",
                ),
                MonitorEvent(
                    kind="idle_no_work",
                    workspace="/tmp/ws",
                    reason="daemon idle with no work",
                ),
            ]

        def wait(self, *, timeout_seconds: float) -> MonitorEvent:
            return self.events.pop(0)

    pi = FakePi()
    millrace = FakeMillrace()
    agent = MillracerAgent(pi=pi, millrace=millrace, monitor=RestartMonitor())

    result = agent.run(
        "Process one scoped queue item",
        options=RunOptions(workspace=Path("/tmp/ws"), cwd=Path("/tmp/ws"), route="millrace"),
    )

    assert result.event == MonitorEvent(
        kind="idle_no_work",
        workspace="/tmp/ws",
        reason="daemon idle with no work",
    )
    assert result.outcome == "incomplete"
    assert result.scoped_completion is False
    assert millrace.calls == [
        "initialize",
        "validate",
        "enqueue:probe:Process one scoped queue item",
        "start_daemon",
        "restart_daemon",
        "stop_daemon",
        "status",
    ]


def test_agent_surfaces_progress_events_without_stopping_daemon_early() -> None:
    class ProgressMonitor:
        def __init__(self) -> None:
            self.events = [
                MonitorEvent(
                    kind="stage_progress",
                    workspace="/tmp/ws",
                    reason="updater update complete",
                ),
                MonitorEvent(kind="idle_no_work", workspace="/tmp/ws", reason="daemon idle"),
            ]

        def wait(self, *, timeout_seconds: float) -> MonitorEvent:
            return self.events.pop(0)

    pi = FakePi()
    millrace = FakeMillrace()
    agent = MillracerAgent(pi=pi, millrace=millrace, monitor=ProgressMonitor())

    result = agent.run(
        "Process one scoped queue item",
        options=RunOptions(workspace=Path("/tmp/ws"), cwd=Path("/tmp/ws"), route="millrace"),
    )

    assert result.progress_events == (
        MonitorEvent(
            kind="stage_progress",
            workspace="/tmp/ws",
            reason="updater update complete",
        ),
    )
    assert result.outcome == "incomplete"
    assert result.scoped_completion is False
    assert "Millrace reported this progress event" in pi.prompts[-2]
    assert millrace.calls == [
        "initialize",
        "validate",
        "enqueue:probe:Process one scoped queue item",
        "start_daemon",
        "stop_daemon",
        "status",
    ]


def test_agent_can_ignore_progress_prompts_when_notifications_disabled() -> None:
    class ProgressMonitor:
        def __init__(self) -> None:
            self.events = [
                MonitorEvent(
                    kind="stage_progress",
                    workspace="/tmp/ws",
                    reason="updater update complete",
                ),
                MonitorEvent(kind="idle_no_work", workspace="/tmp/ws", reason="daemon idle"),
            ]

        def wait(self, *, timeout_seconds: float) -> MonitorEvent:
            return self.events.pop(0)

    pi = FakePi()
    millrace = FakeMillrace()
    agent = MillracerAgent(pi=pi, millrace=millrace, monitor=ProgressMonitor())

    result = agent.run(
        "Process one scoped queue item",
        options=RunOptions(
            workspace=Path("/tmp/ws"),
            cwd=Path("/tmp/ws"),
            route="millrace",
            notify_terminal_stages=False,
        ),
    )

    assert result.progress_events == ()
    assert all("Millrace reported this progress event" not in prompt for prompt in pi.prompts)


def test_agent_reports_existing_blocked_scoped_intake_without_reusing_as_completion() -> None:
    class BlockedScopedMillrace(FakeMillrace):
        def find_existing_scoped_intake(self, scoped_work_item):  # noqa: ANN001
            self.calls.append(f"find_existing:{scoped_work_item.item_id}")
            return Path("/tmp/ws/.millracer/intake/probe-old.md")

        def status(self) -> dict[str, object]:
            self.calls.append("status")
            return {
                "workspace": "/tmp/ws",
                "current_failure_class": "recon_handoff_invalid",
                "latest_runtime_error_report_path": "/tmp/ws/runtime-errors/report.md",
                "active_run_count": 0,
                "execution_queue_depth": 0,
                "planning_queue_depth": 0,
                "learning_queue_depth": 0,
            }

    pi = FakePi()
    millrace = BlockedScopedMillrace()
    agent = MillracerAgent(pi=pi, millrace=millrace, monitor=FakeMonitor())

    result = agent.run(
        "Process the selected scoped item",
        options=RunOptions(
            workspace=Path("/tmp/ws"),
            cwd=Path("/tmp/ws"),
            route="millrace",
            scoped_work_item=ScopedWorkItem(item_id="ITEM-123"),
        ),
    )

    assert result.event == MonitorEvent(
        kind="blocked",
        workspace="/tmp/ws",
        reason="recon_handoff_invalid",
    )
    assert result.outcome == "blocked"
    assert result.scoped_completion is False
    assert millrace.calls == [
        "initialize",
        "validate",
        "find_existing:ITEM-123",
        "status",
    ]
