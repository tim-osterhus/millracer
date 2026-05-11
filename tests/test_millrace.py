from pathlib import Path

from millracer.benchmark import ScopedWorkItem
from millracer.millrace import MillraceConfig, MillraceController, render_task_document


class RecordingExecutor:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.status_payloads: list[str] = []
        self.started_handle: RecordingHandle | None = None

    def run(self, args, *, cwd, timeout_seconds=None, env=None):  # noqa: ANN001
        self.commands.append(tuple(args))
        if "status" in args:
            stdout = (
                self.status_payloads.pop(0)
                if self.status_payloads
                else '{"workspace": "/tmp/ws"}'
            )
        else:
            stdout = "ok"
        return type(
            "Result",
            (),
            {"returncode": 0, "stdout": stdout, "stderr": "", "args": tuple(args)},
        )()

    def start(self, args, *, cwd, env=None):  # noqa: ANN001
        self.commands.append(tuple(args))
        self.started_handle = RecordingHandle()
        return self.started_handle


class RecordingHandle:
    def __init__(self) -> None:
        self.terminated = False
        self.killed = False
        self.waits: list[float | None] = []

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        self.waits.append(timeout)
        return 0


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


def test_render_task_document_includes_scoped_work_contract() -> None:
    raw = render_task_document(
        task_id="task-abc",
        title="Benchmark task",
        summary="Implement the selected item only",
        created_at="2026-05-10T00:00:00+00:00",
        scoped_work_item=ScopedWorkItem(
            item_id="M06",
            title="Array API label encoder support",
            source_queue="/queue.md",
            spec_path="/srs/M06.md",
            completion_ref="agent-impl-M06",
            constraints=("Do not implement any other queue item.",),
        ),
    )

    assert "Scoped-Work:" in raw
    assert "Item-ID: M06" in raw
    assert "Spec-Path: /srs/M06.md" in raw
    assert "Completion-Ref: agent-impl-M06" in raw
    assert "Do not batch independent queue items into this work item." in raw


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
        ("millrace", "status", "--workspace", "/tmp/ws", "--format", "json"),
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


def test_controller_clears_stale_state_before_starting_daemon() -> None:
    executor = RecordingExecutor()
    executor.status_payloads.append('{"workspace": "/tmp/ws", "runtime_ownership_lock": "stale"}')
    controller = MillraceController(
        config=MillraceConfig(command="millrace", mode="default_pi"),
        executor=executor,
        workspace=Path("/tmp/ws"),
    )

    controller.start_daemon()

    assert executor.commands == [
        ("millrace", "status", "--workspace", "/tmp/ws", "--format", "json"),
        ("millrace", "control", "clear-stale-state", "--workspace", "/tmp/ws"),
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


def test_controller_stop_waits_for_daemon_before_clearing_stale_state() -> None:
    executor = RecordingExecutor()
    executor.status_payloads.append('{"workspace": "/tmp/ws"}')
    executor.status_payloads.append('{"workspace": "/tmp/ws", "runtime_ownership_lock": "stale"}')
    controller = MillraceController(
        config=MillraceConfig(command="millrace", mode="default_pi"),
        executor=executor,
        workspace=Path("/tmp/ws"),
    )

    controller.start_daemon()
    controller.stop_daemon()

    assert executor.started_handle is not None
    assert executor.started_handle.waits == [30.0]
    assert executor.started_handle.terminated is False
    assert executor.commands[-2:] == [
        ("millrace", "status", "--workspace", "/tmp/ws", "--format", "json"),
        ("millrace", "control", "clear-stale-state", "--workspace", "/tmp/ws"),
    ]
