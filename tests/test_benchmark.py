from pathlib import Path

from millracer.agent import RunResult
from millracer.benchmark import ScopedWorkItem, parse_benchmark_request, render_benchmark_result
from millracer.decision import Decision


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
