from pathlib import Path

from millracer.agent import RunResult
from millracer.benchmark import (
    ScopedWorkItem,
    ops_result_to_legacy_json,
    parse_benchmark_request,
    parse_legacy_request_as_ops,
    render_benchmark_result,
)
from millracer.decision import Decision
from millracer.ops_models import (
    SCHEMA_VERSION,
    Completion,
    OpsResult,
    WorkspaceRef,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ops"


def test_parse_benchmark_request_preserves_scoped_work_item() -> None:
    request = parse_benchmark_request(
        """
        {
          "task": "Implement the selected queue item only.",
          "workspace": "/tmp/ws",
          "intake_kind": "probe",
          "scoped_work_item": {
            "item_id": "M06",
            "title": "Array API label encoder support",
            "source_queue": "/queue.md",
            "spec_path": "/srs/M06.md",
            "completion_ref": "agent-impl-M06",
            "constraints": ["Do not implement any other queue item."]
          }
        }
        """
    )

    assert request.workspace == Path("/tmp/ws")
    assert request.intake_kind == "probe"
    assert request.scoped_work_item == ScopedWorkItem(
        item_id="M06",
        title="Array API label encoder support",
        source_queue="/queue.md",
        spec_path="/srs/M06.md",
        completion_ref="agent-impl-M06",
        constraints=("Do not implement any other queue item.",),
    )


def test_render_benchmark_result_includes_scoped_work_item() -> None:
    raw = render_benchmark_result(
        RunResult(
            route="millrace",
            intake_kind="probe",
            decision=Decision(route="millrace", why="test"),
            output="done",
            scoped_work_item=ScopedWorkItem(item_id="ITEM-123"),
            intake_signals=("large pre-existing codebase",),
            outcome="completed",
            scoped_completion=True,
            completion_evidence=({"kind": "arbiter_complete", "reason": "closed"},),
        )
    )

    assert '"scoped_work_item"' in raw
    assert '"item_id": "ITEM-123"' in raw
    assert '"intake_kind": "probe"' in raw
    assert '"large pre-existing codebase"' in raw
    assert '"outcome": "completed"' in raw
    assert '"scoped_completion": true' in raw
    assert '"completion_evidence"' in raw


def test_legacy_request_maps_to_ops_request() -> None:
    raw = (FIXTURES / "legacy_request.json").read_text(encoding="utf-8")

    request = parse_legacy_request_as_ops(raw, request_id="req-legacy-001")

    assert request.schema_version == SCHEMA_VERSION
    assert request.request_id == "req-legacy-001"
    assert request.source.kind == "benchmark_compat"
    assert request.action == "enqueue"
    assert request.intake_preference == "probe"
    assert request.scoped_work_item is not None
    assert request.scoped_work_item.item_id == "ITEM-123"


def test_ops_result_can_render_legacy_json() -> None:
    raw = ops_result_to_legacy_json(
        OpsResult(
            schema_version=SCHEMA_VERSION,
            request_id="req-legacy-001",
            status="incomplete",
            action="enqueue",
            workspace_ref=WorkspaceRef(root_path="/tmp/ws"),
            started_at="2026-05-12T00:00:00+00:00",
            finished_at="2026-05-12T00:00:01+00:00",
            warnings=(),
            errors=(),
            result={"output": "not complete"},
            route="millrace",
            intake_kind="probe",
            scoped_work_item=ScopedWorkItem(item_id="ITEM-123"),
            completion=Completion(outcome="incomplete", scoped_completion=False),
            raw_compat={"route": "millrace"},
        )
    )

    assert '"status": "incomplete"' in raw
    assert '"scoped_completion": false' in raw
