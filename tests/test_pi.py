from pathlib import Path

from millracer.pi import PiConfig, PiHarness
from millracer.pi_rpc import PiRpcHarness, build_rpc_command


class RecordingExecutor:
    def __init__(self) -> None:
        self.args: tuple[str, ...] | None = None

    def run(self, args, *, cwd, timeout_seconds=None, env=None):  # noqa: ANN001
        self.args = tuple(args)
        return type(
            "Result",
            (),
            {"returncode": 0, "stdout": "ok", "stderr": "", "args": tuple(args)},
        )()


def test_pi_harness_injects_prompt_skills_and_thinking() -> None:
    executor = RecordingExecutor()
    harness = PiHarness(
        config=PiConfig(
            command="pi",
            provider="openai",
            model="gpt-5.4-mini",
            thinking="high",
            skill_paths=(Path("/skills/delegate"),),
        ),
        executor=executor,
    )

    assert harness.complete("hello", cwd=Path("/tmp/repo")) == "ok"
    assert executor.args is not None
    assert executor.args[:2] == ("pi", "--print")
    assert "--append-system-prompt" in executor.args
    assert (
        executor.args[executor.args.index("--skill")],
        executor.args[executor.args.index("--skill") + 1],
    ) == ("--skill", "/skills/delegate")
    assert (
        executor.args[executor.args.index("--thinking")],
        executor.args[executor.args.index("--thinking") + 1],
    ) == ("--thinking", "high")
    assert executor.args[-1] == "hello"


def test_pi_rpc_command_uses_persistent_rpc_mode() -> None:
    command = build_rpc_command(
        PiConfig(
            command="pi",
            provider="openai",
            model="gpt-5.4-mini",
            thinking="high",
            skill_paths=(Path("/skills/delegate"),),
        )
    )

    assert command[:4] == ("pi", "--mode", "rpc", "--no-session")
    assert "--print" not in command
    assert "--append-system-prompt" in command
    assert (
        command[command.index("--skill")],
        command[command.index("--skill") + 1],
    ) == ("--skill", "/skills/delegate")


def test_pi_rpc_harness_reuses_one_session_for_multiple_prompts() -> None:
    class FakeSession:
        def __init__(self) -> None:
            self.prompts: list[str] = []
            self.closed = False

        def prompt(self, prompt: str, *, timeout_seconds: int | None = None) -> str:
            self.prompts.append(prompt)
            return f"reply-{len(self.prompts)}"

        def close(self) -> None:
            self.closed = True

    sessions: list[FakeSession] = []

    def session_factory(*, command, cwd, env):  # noqa: ANN001
        session = FakeSession()
        sessions.append(session)
        return session

    harness = PiRpcHarness(config=PiConfig(), session_factory=session_factory)
    assert harness.complete("one", cwd=Path("/tmp/repo")) == "reply-1"
    assert harness.complete("two", cwd=Path("/tmp/repo")) == "reply-2"
    harness.close()

    assert len(sessions) == 1
    assert sessions[0].prompts == ["one", "two"]
    assert sessions[0].closed is True
