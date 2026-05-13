from __future__ import annotations

from pathlib import Path

import pytest

from millracer.ops_models import (
    SCHEMA_VERSION,
    OpsEventFrame,
    parse_ops_request,
    parse_ops_result,
    render_ops_event_frame,
    render_ops_request,
    render_ops_result,
)

FIXTURES = Path(__file__).parent / "fixtures" / "ops"


def test_ops_request_roundtrips_status_fixture() -> None:
    raw = (FIXTURES / "status_request.json").read_text(encoding="utf-8")
    request = parse_ops_request(raw)

    assert request.schema_version == SCHEMA_VERSION
    assert request.request_id == "req-status-001"
    assert request.action == "status"
    assert request.workspace_ref.workspace_id == "millrace-os"
    assert request.workspace_ref.mode == "learning_codex"
    assert request.source.kind == "mission_control"
    assert render_ops_request(request)["schema_version"] == SCHEMA_VERSION


def test_ops_result_roundtrips_status_fixture() -> None:
    raw = (FIXTURES / "status_result.json").read_text(encoding="utf-8")
    result = parse_ops_result(raw)

    assert result.status == "succeeded"
    assert result.completion is not None
    assert result.completion.scoped_completion is False
    assert render_ops_result(result)["completion"]["verification_status"] == "not_applicable"


def test_ops_request_rejects_unsupported_schema() -> None:
    with pytest.raises(ValueError, match="unsupported ops schema"):
        parse_ops_request(
            """
            {
              "schema_version": "millracer.ops.v9",
              "request_id": "req-bad",
              "workspace_ref": {},
              "source": {"kind": "cli"},
              "action": "status",
              "input": {}
            }
            """
        )


def test_ops_event_frame_renders_sequence_and_cursor() -> None:
    frame = OpsEventFrame(
        schema_version=SCHEMA_VERSION,
        request_id="req-001",
        event_id="evt-001",
        sequence=1,
        timestamp="2026-05-12T00:00:00+00:00",
        event_type="request.accepted",
        severity="info",
        message="Request accepted.",
        payload={},
        cursor="1",
    )

    rendered = render_ops_event_frame(frame)

    assert rendered["event_type"] == "request.accepted"
    assert rendered["cursor"] == "1"
