from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from millracer.agent import RunOptions, RunResult
from millracer.decision import Decision
from millracer.ops_models import (
    SCHEMA_VERSION,
    OpsRequest,
    SourceRef,
    WorkspaceRef,
    parse_ops_request,
)
from millracer.ops_service import OpsService
from millracer.scope import ScopedWorkItem
from millracer.sessions import SessionStore
from millracer.workspaces import WorkspaceRecord, WorkspaceRegistry

FIXTURES = Path(__file__).parent / "fixtures" / "ops"


@dataclass(slots=True)
class FakeRuntime:
    status_payload: dict[str, object] | None = None

    def status(self) -> dict[str, object]:
        return self.status_payload or {"workspace": "/tmp/ws"}


@dataclass(slots=True)
class FailingRunner:
    calls: list[str]

    def complete(self, *args, **kwargs):  # noqa: ANN002, ANN003, ANN201
        self.calls.append("complete")
        raise AssertionError("runner should not be called")


@dataclass(slots=True)
class FakeAgent:
    result: RunResult
    calls: list[tuple[str, RunOptions]]

    def run(self, task: str, *, options: RunOptions) -> RunResult:
        self.calls.append((task, options))
        return self.result


def make_request(
    *,
    action: str,
    workspace_root: Path,
    route_preference: str = "auto",
    intake_preference: str = "auto",
    input_payload: dict[str, object] | None = None,
) -> OpsRequest:
    return OpsRequest(
        schema_version=SCHEMA_VERSION,
        request_id=f"req-{action}",
        action=action,
        workspace_ref=WorkspaceRef(root_path=str(workspace_root)),
        source=SourceRef(kind="cli"),
        input=input_payload or {"kind": "structured_action", "payload": {}},
        route_preference=route_preference,
        intake_preference=intake_preference,
    )


def test_structured_status_uses_runtime_without_runner(tmp_path: Path) -> None:
    runtime = FakeRuntime(status_payload={"workspace": str(tmp_path), "process_running": False})
    runner = FailingRunner(calls=[])
    service = OpsService(
        runtime_factory=lambda resolved: runtime,
        runner=runner,
        registry=WorkspaceRegistry.empty(),
    )

    result = service.handle(make_request(action="status", workspace_root=tmp_path))

    assert result.status == "succeeded"
    assert result.action == "status"
    assert result.route == "status_only"
    assert result.result["process_running"] is False
    assert result.completion is not None
    assert result.completion.verification_status == "not_applicable"
    assert runner.calls == []


def test_unsupported_structured_action_returns_machine_error(tmp_path: Path) -> None:
    service = OpsService(
        runtime_factory=lambda resolved: FakeRuntime(),
        runner=FailingRunner(calls=[]),
        registry=WorkspaceRegistry.empty(),
    )

    result = service.handle(make_request(action="approve", workspace_root=tmp_path))

    assert result.status == "failed"
    assert result.errors[0].code == "unsupported_action"


def test_workspace_unresolved_returns_machine_error() -> None:
    service = OpsService(
        runtime_factory=lambda resolved: FakeRuntime(),
        runner=FailingRunner(calls=[]),
        registry=WorkspaceRegistry.empty(),
        cwd=None,
    )
    request = OpsRequest(
        schema_version=SCHEMA_VERSION,
        request_id="req-status",
        action="status",
        workspace_ref=WorkspaceRef(),
        source=SourceRef(kind="cli"),
        input={"kind": "structured_action", "payload": {}},
    )

    result = service.handle(request)

    assert result.status == "failed"
    assert result.errors[0].code == "workspace_unresolved"


def test_enqueue_maps_run_result_completion_fields(tmp_path: Path) -> None:
    agent_calls: list[tuple[str, RunOptions]] = []
    agent = FakeAgent(
        result=RunResult(
            route="millrace",
            intake_kind="task",
            decision=Decision(route="millrace", why="forced"),
            output="delegated",
            outcome="incomplete",
            scoped_completion=False,
            completion_evidence=(),
        ),
        calls=agent_calls,
    )
    service = OpsService(
        runtime_factory=lambda resolved: FakeRuntime(),
        runner=FailingRunner(calls=[]),
        agent_factory=lambda runtime, runner, monitor: agent,
        registry=WorkspaceRegistry.empty(),
    )
    request = parse_ops_request((FIXTURES / "enqueue_request.json").read_text(encoding="utf-8"))

    result = service.handle(request)

    assert result.status == "incomplete"
    assert result.completion is not None
    assert result.completion.outcome == "incomplete"
    assert result.completion.scoped_completion is False
    assert result.scoped_work_item == ScopedWorkItem(
        item_id="WP-002A",
        title="Millracer ops contract skeleton",
        constraints=("Do not implement unrelated packets.",),
    )
    assert agent_calls[0][0] == "Implement the selected packet only."
    assert agent_calls[0][1].intake == "task"


def test_list_workspaces_returns_registry_records(tmp_path: Path) -> None:
    registry = WorkspaceRegistry(
        records={
            "millrace-os": WorkspaceRecord(
                workspace_id="millrace-os",
                root_path=tmp_path,
                display_name="Millrace OS",
                default_mode="learning_codex",
            )
        }
    )
    service = OpsService(
        runtime_factory=lambda resolved: FakeRuntime(),
        runner=FailingRunner(calls=[]),
        registry=registry,
    )

    result = service.handle(make_request(action="list_workspaces", workspace_root=tmp_path))

    assert result.status == "succeeded"
    assert result.result["workspaces"][0]["workspace_id"] == "millrace-os"


def test_select_workspace_updates_session_store(tmp_path: Path) -> None:
    registry = WorkspaceRegistry(
        records={
            "millrace-os": WorkspaceRecord(
                workspace_id="millrace-os",
                root_path=tmp_path,
                default_mode="learning_codex",
            )
        }
    )
    session_store = SessionStore(path=tmp_path / "sessions.json")
    service = OpsService(
        runtime_factory=lambda resolved: FakeRuntime(),
        runner=FailingRunner(calls=[]),
        registry=registry,
        session_store=session_store,
    )
    request = make_request(
        action="select_workspace",
        workspace_root=tmp_path,
        input_payload={
            "kind": "structured_action",
            "payload": {"workspace_id": "millrace-os", "session_id": "local"},
        },
    )

    result = service.handle(request)

    assert result.status == "succeeded"
    assert session_store.get_or_create("local").selected_workspace_id == "millrace-os"


def test_list_sessions_returns_session_store_records(tmp_path: Path) -> None:
    session_store = SessionStore(path=tmp_path / "sessions.json")
    session_store.get_or_create("local")
    service = OpsService(
        runtime_factory=lambda resolved: FakeRuntime(),
        runner=FailingRunner(calls=[]),
        session_store=session_store,
    )

    result = service.handle(make_request(action="list_sessions", workspace_root=tmp_path))

    assert result.status == "succeeded"
    assert result.result["sessions"][0]["session_id"] == "local"


def test_preview_events_exposes_request_accepted_frame(tmp_path: Path) -> None:
    service = OpsService(
        runtime_factory=lambda resolved: FakeRuntime(),
        runner=FailingRunner(calls=[]),
    )

    frames = service.preview_events(make_request(action="status", workspace_root=tmp_path))

    assert frames[0].event_type == "request.accepted"
