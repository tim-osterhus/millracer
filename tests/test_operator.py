from pathlib import Path

from millracer.agent import RunResult
from millracer.decision import Decision
from millracer.operator import MillracerOperator


class FakeAgent:
    def __init__(self) -> None:
        self.tasks: list[str] = []

    def run(self, task, *, options):  # noqa: ANN001
        self.tasks.append(task)
        return RunResult(
            route="direct",
            decision=Decision(route="direct", why="test"),
            output=task.upper(),
        )


class FakePi:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def test_operator_keeps_one_agent_session_across_tasks() -> None:
    agent = FakeAgent()
    pi = FakePi()
    operator = MillracerOperator(
        agent=agent,
        pi=pi,
        workspace=Path("/tmp/ws"),
        cwd=Path("/tmp/ws"),
    )

    first = operator.handle("first task")
    second = operator.handle("second task")
    operator.close()

    assert first.output == "FIRST TASK"
    assert second.output == "SECOND TASK"
    assert agent.tasks == ["first task", "second task"]
    assert pi.closed is True
