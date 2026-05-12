from pathlib import Path

from millracer.benchmark import ScopedWorkItem
from millracer.intake import IntakeKind
from millracer.millrace import (
    MillraceConfig,
    MillraceController,
    render_idea_document,
    render_probe_document,
    render_task_document,
)


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


def test_render_probe_document_is_investigation_first() -> None:
    raw = render_probe_document(
        task_id="probe-abc",
        title="Investigate launch behavior",
        summary="Figure out how launch behavior should change.",
        created_at="2026-05-10T00:00:00+00:00",
        scoped_work_item=ScopedWorkItem(item_id="ITEM-123"),
    )

    assert "Probe-ID: probe-abc" in raw
    assert "Summary: Figure out how launch behavior should change." in raw
    assert "Request: Figure out how launch behavior should change." in raw
    assert "Do not implement code changes during this probe stage." in raw
    assert "Which codebase areas are likely involved?" in raw
    assert "What should downstream Builder/Checker know before changing code?" in raw
    assert "Item-ID: ITEM-123" in raw


def test_render_idea_document_preserves_intent_and_scope() -> None:
    raw = render_idea_document(
        task_id="idea-abc",
        title="Add operator dashboard",
        summary="Add a dashboard for queued runs.",
        created_at="2026-05-10T00:00:00+00:00",
        scoped_work_item=ScopedWorkItem(item_id="ITEM-123"),
    )

    assert "Idea-ID: idea-abc" in raw
    assert "Desired-Outcome:" in raw
    assert "Planning-Intent:" in raw
    assert "Item-ID: ITEM-123" in raw


def test_controller_dispatches_probe_idea_and_task_to_matching_queue_commands(tmp_path) -> None:
    executor = RecordingExecutor()
    controller = MillraceController(
        config=MillraceConfig(command="millrace", mode="default_pi"),
        executor=executor,
        workspace=tmp_path,
    )

    probe_path = controller.enqueue(IntakeKind.PROBE, "Investigate runtime behavior")
    idea_path = controller.enqueue(IntakeKind.IDEA, "Build an operator dashboard")
    task_path = controller.enqueue(IntakeKind.TASK, "Fix src/millracer/monitor.py")

    assert probe_path.name.startswith("probe-")
    assert idea_path.name.startswith("idea-")
    assert task_path.name.startswith("task-")
    assert executor.commands == [
        (
            "millrace",
            "queue",
            "add-probe",
            str(probe_path),
            "--workspace",
            str(tmp_path),
        ),
        (
            "millrace",
            "queue",
            "add-idea",
            str(idea_path),
            "--workspace",
            str(tmp_path),
        ),
        (
            "millrace",
            "queue",
            "add-task",
            str(task_path),
            "--workspace",
            str(tmp_path),
        ),
    ]


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
