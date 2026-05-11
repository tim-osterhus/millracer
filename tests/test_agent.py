from pathlib import Path

from millracer.agent import MillracerAgent, RunOptions
from millracer.decision import Decision
from millracer.monitor import MonitorEvent


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

    def enqueue_task(self, task: str, scoped_work_item=None) -> Path:  # noqa: ANN001
        self.calls.append(f"enqueue:{task}")
        return Path("/tmp/ws/.millracer/intake/task.md")

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
    assert result.decision == Decision(route="millrace", why="needs durable execution")
    assert result.output == "final answer"
    assert millrace.calls == [
        "initialize",
        "validate",
        "enqueue:Implement a multi-stage refactor",
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
                    kind="complete",
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
        kind="complete",
        workspace="/tmp/ws",
        reason="daemon idle with no work",
    )
    assert millrace.calls == [
        "initialize",
        "validate",
        "enqueue:Process one scoped queue item",
        "start_daemon",
        "restart_daemon",
        "stop_daemon",
        "status",
    ]
