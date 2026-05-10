from pathlib import Path

from millracer.millrace import MillraceConfig, MillraceController, render_task_document


class RecordingExecutor:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def run(self, args, *, cwd, timeout_seconds=None, env=None):  # noqa: ANN001
        self.commands.append(tuple(args))
        stdout = '{"workspace": "/tmp/ws"}' if "status" in args else "ok"
        return type(
            "Result",
            (),
            {"returncode": 0, "stdout": stdout, "stderr": "", "args": tuple(args)},
        )()

    def start(self, args, *, cwd, env=None):  # noqa: ANN001
        self.commands.append(tuple(args))
        return type("Handle", (), {"poll": lambda self: None})()


def test_render_task_document_contains_required_millrace_fields() -> None:
    raw = render_task_document(
        task_id="task-abc",
        title="Benchmark task",
        summary="Do the thing",
        created_at="2026-05-10T00:00:00+00:00",
    )

    assert raw.startswith("# Benchmark task\n")
    assert "Task-ID: task-abc" in raw
    assert "Target-Paths:" in raw
    assert "Acceptance:" in raw
    assert "Required-Checks:" in raw
    assert "Risk:" in raw


def test_controller_uses_default_pi_mode_for_daemon() -> None:
    executor = RecordingExecutor()
    controller = MillraceController(
        config=MillraceConfig(command="millrace", mode="default_pi"),
        executor=executor,
        workspace=Path("/tmp/ws"),
    )

    controller.initialize()
    controller.validate()
    controller.start_daemon()

    assert executor.commands == [
        ("millrace", "init", "--workspace", "/tmp/ws"),
        ("millrace", "compile", "validate", "--workspace", "/tmp/ws", "--mode", "default_pi"),
        (
            "millrace",
            "run",
            "daemon",
            "--workspace",
            "/tmp/ws",
            "--mode",
            "default_pi",
            "--monitor",
            "none",
        ),
    ]
