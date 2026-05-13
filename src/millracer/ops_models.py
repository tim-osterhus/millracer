"""Versioned request/result contracts for Millracer ops callers."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from millracer.scope import ScopedWorkItem

SCHEMA_VERSION = "millracer.ops.v0.2"


@dataclass(frozen=True, slots=True)
class WorkspaceRef:
    workspace_id: str | None = None
    root_path: str | None = None
    display_name: str | None = None
    runtime_kind: str = "local"
    mode: str | None = None
    environment: str | None = None


@dataclass(frozen=True, slots=True)
class SourceRef:
    kind: str
    surface: str | None = None
    adapter_id: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    parent_request_id: str | None = None
    trace_ref: str | None = None


@dataclass(frozen=True, slots=True)
class ActorRef:
    kind: str
    display_name: str | None = None
    actor_id: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class WarningRecord:
    code: str
    message: str
    severity: str = "warning"
    recoverable: bool = True
    related_ref: str | None = None
    suggested_action: str | None = None


@dataclass(frozen=True, slots=True)
class ErrorRecord:
    code: str
    message: str
    severity: str = "error"
    recoverable: bool = False
    related_ref: str | None = None
    suggested_action: str | None = None


@dataclass(frozen=True, slots=True)
class Completion:
    outcome: str
    scoped_completion: bool
    evidence_summary: tuple[Mapping[str, str], ...] = ()
    missing_evidence: tuple[str, ...] = ()
    verification_status: str = "unverified"
    terminal_outcome_ref: str | None = None


@dataclass(frozen=True, slots=True)
class OpsRequest:
    schema_version: str
    request_id: str
    action: str
    workspace_ref: WorkspaceRef
    source: SourceRef
    input: Mapping[str, object]
    client_name: str | None = None
    client_version: str | None = None
    actor: ActorRef | None = None
    route_preference: str = "auto"
    intake_preference: str = "auto"
    scoped_work_item: ScopedWorkItem | None = None
    expected_evidence: tuple[str, ...] = ()
    context_refs: tuple[str, ...] = ()
    options: Mapping[str, object] = field(default_factory=dict)
    metadata: Mapping[str, object] = field(default_factory=dict)
    idempotency_key: str | None = None


@dataclass(frozen=True, slots=True)
class OpsResult:
    schema_version: str
    request_id: str
    status: str
    action: str
    workspace_ref: WorkspaceRef
    started_at: str
    finished_at: str
    warnings: tuple[WarningRecord, ...]
    errors: tuple[ErrorRecord, ...]
    result: Mapping[str, object]
    route: str | None = None
    intake_kind: str | None = None
    scoped_work_item: ScopedWorkItem | None = None
    completion: Completion | None = None
    evidence_refs: tuple[str, ...] = ()
    event_cursor: str | None = None
    session_ref: str | None = None
    raw_compat: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class OpsEventFrame:
    schema_version: str
    request_id: str
    event_id: str
    sequence: int
    timestamp: str
    event_type: str
    severity: str
    message: str
    payload: Mapping[str, object] = field(default_factory=dict)
    cursor: str | None = None


def parse_ops_request(raw: str) -> OpsRequest:
    payload = _loads_object(raw, "ops request")
    return parse_ops_request_payload(payload)


def parse_ops_request_payload(payload: Mapping[str, object]) -> OpsRequest:
    _require_schema(payload)
    request_id = _required_string(payload, "request_id")
    action = _required_string(payload, "action")
    workspace_payload = _required_mapping(payload, "workspace_ref")
    source_payload = _required_mapping(payload, "source")
    input_payload = _mapping_or_empty(payload.get("input"))
    return OpsRequest(
        schema_version=SCHEMA_VERSION,
        request_id=request_id,
        action=action,
        workspace_ref=_parse_workspace_ref(workspace_payload),
        source=_parse_source_ref(source_payload),
        input=input_payload,
        client_name=_optional_string(payload.get("client_name")),
        client_version=_optional_string(payload.get("client_version")),
        actor=_parse_actor_ref(payload.get("actor")),
        route_preference=_optional_string(payload.get("route_preference")) or "auto",
        intake_preference=_optional_string(payload.get("intake_preference")) or "auto",
        scoped_work_item=ScopedWorkItem.from_payload(payload.get("scoped_work_item")),
        expected_evidence=_tuple_strings(payload.get("expected_evidence")),
        context_refs=_tuple_strings(payload.get("context_refs")),
        options=_mapping_or_empty(payload.get("options")),
        metadata=_mapping_or_empty(payload.get("metadata")),
        idempotency_key=_optional_string(payload.get("idempotency_key")),
    )


def parse_ops_result(raw: str) -> OpsResult:
    payload = _loads_object(raw, "ops result")
    return parse_ops_result_payload(payload)


def parse_ops_result_payload(payload: Mapping[str, object]) -> OpsResult:
    _require_schema(payload)
    return OpsResult(
        schema_version=SCHEMA_VERSION,
        request_id=_required_string(payload, "request_id"),
        status=_required_string(payload, "status"),
        action=_required_string(payload, "action"),
        workspace_ref=_parse_workspace_ref(_required_mapping(payload, "workspace_ref")),
        started_at=_required_string(payload, "started_at"),
        finished_at=_required_string(payload, "finished_at"),
        warnings=tuple(_parse_warning(item) for item in _list_or_empty(payload.get("warnings"))),
        errors=tuple(_parse_error(item) for item in _list_or_empty(payload.get("errors"))),
        result=_mapping_or_empty(payload.get("result")),
        route=_optional_string(payload.get("route")),
        intake_kind=_optional_string(payload.get("intake_kind")),
        scoped_work_item=ScopedWorkItem.from_payload(payload.get("scoped_work_item")),
        completion=_parse_completion(payload.get("completion")),
        evidence_refs=_tuple_strings(payload.get("evidence_refs")),
        event_cursor=_optional_string(payload.get("event_cursor")),
        session_ref=_optional_string(payload.get("session_ref")),
        raw_compat=_optional_mapping(payload.get("raw_compat")),
    )


def render_ops_request(request: OpsRequest) -> dict[str, object]:
    rendered: dict[str, object] = {
        "schema_version": request.schema_version,
        "request_id": request.request_id,
        "workspace_ref": _render_workspace_ref(request.workspace_ref),
        "source": _render_source_ref(request.source),
        "action": request.action,
        "route_preference": request.route_preference,
        "intake_preference": request.intake_preference,
        "input": dict(request.input),
    }
    _set_if_not_none(rendered, "client_name", request.client_name)
    _set_if_not_none(rendered, "client_version", request.client_version)
    if request.actor is not None:
        rendered["actor"] = _render_actor_ref(request.actor)
    if request.scoped_work_item is not None:
        rendered["scoped_work_item"] = request.scoped_work_item.to_jsonable()
    if request.expected_evidence:
        rendered["expected_evidence"] = list(request.expected_evidence)
    if request.context_refs:
        rendered["context_refs"] = list(request.context_refs)
    if request.options:
        rendered["options"] = dict(request.options)
    if request.metadata:
        rendered["metadata"] = dict(request.metadata)
    _set_if_not_none(rendered, "idempotency_key", request.idempotency_key)
    return rendered


def render_ops_result(result: OpsResult) -> dict[str, object]:
    rendered: dict[str, object] = {
        "schema_version": result.schema_version,
        "request_id": result.request_id,
        "status": result.status,
        "action": result.action,
        "workspace_ref": _render_workspace_ref(result.workspace_ref),
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "warnings": [_render_warning(warning) for warning in result.warnings],
        "errors": [_render_error(error) for error in result.errors],
        "result": dict(result.result),
    }
    _set_if_not_none(rendered, "route", result.route)
    _set_if_not_none(rendered, "intake_kind", result.intake_kind)
    if result.scoped_work_item is not None:
        rendered["scoped_work_item"] = result.scoped_work_item.to_jsonable()
    if result.completion is not None:
        rendered["completion"] = _render_completion(result.completion)
    if result.evidence_refs:
        rendered["evidence_refs"] = list(result.evidence_refs)
    _set_if_not_none(rendered, "event_cursor", result.event_cursor)
    _set_if_not_none(rendered, "session_ref", result.session_ref)
    if result.raw_compat is not None:
        rendered["raw_compat"] = dict(result.raw_compat)
    return rendered


def render_ops_event_frame(frame: OpsEventFrame) -> dict[str, object]:
    rendered: dict[str, object] = {
        "schema_version": frame.schema_version,
        "request_id": frame.request_id,
        "event_id": frame.event_id,
        "sequence": frame.sequence,
        "timestamp": frame.timestamp,
        "event_type": frame.event_type,
        "severity": frame.severity,
        "message": frame.message,
        "payload": dict(frame.payload),
    }
    _set_if_not_none(rendered, "cursor", frame.cursor)
    return rendered


def _loads_object(raw: str, label: str) -> dict[str, object]:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    return payload


def _require_schema(payload: Mapping[str, object]) -> None:
    schema_version = payload.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ValueError(f"unsupported ops schema: {schema_version}")


def _required_string(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"ops payload requires non-empty {key}")
    return value.strip()


def _required_mapping(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"ops payload requires object {key}")
    return value


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    return value if isinstance(value, dict) else {}


def _optional_mapping(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, dict) else None


def _list_or_empty(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _tuple_strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _parse_workspace_ref(payload: Mapping[str, object]) -> WorkspaceRef:
    return WorkspaceRef(
        workspace_id=_optional_string(payload.get("workspace_id")),
        root_path=_optional_string(payload.get("root_path")),
        display_name=_optional_string(payload.get("display_name")),
        runtime_kind=_optional_string(payload.get("runtime_kind")) or "local",
        mode=_optional_string(payload.get("mode")),
        environment=_optional_string(payload.get("environment")),
    )


def _parse_source_ref(payload: Mapping[str, object]) -> SourceRef:
    return SourceRef(
        kind=_required_string(payload, "kind"),
        surface=_optional_string(payload.get("surface")),
        adapter_id=_optional_string(payload.get("adapter_id")),
        conversation_id=_optional_string(payload.get("conversation_id")),
        message_id=_optional_string(payload.get("message_id")),
        parent_request_id=_optional_string(payload.get("parent_request_id")),
        trace_ref=_optional_string(payload.get("trace_ref")),
    )


def _parse_actor_ref(value: object) -> ActorRef | None:
    if not isinstance(value, dict):
        return None
    metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
    return ActorRef(
        kind=_required_string(value, "kind"),
        display_name=_optional_string(value.get("display_name")),
        actor_id=_optional_string(value.get("actor_id")),
        metadata=metadata,
    )


def _parse_warning(value: object) -> WarningRecord:
    if not isinstance(value, dict):
        raise ValueError("warning records must be objects")
    return WarningRecord(
        code=_required_string(value, "code"),
        message=_required_string(value, "message"),
        severity=_optional_string(value.get("severity")) or "warning",
        recoverable=bool(value.get("recoverable", True)),
        related_ref=_optional_string(value.get("related_ref")),
        suggested_action=_optional_string(value.get("suggested_action")),
    )


def _parse_error(value: object) -> ErrorRecord:
    if not isinstance(value, dict):
        raise ValueError("error records must be objects")
    return ErrorRecord(
        code=_required_string(value, "code"),
        message=_required_string(value, "message"),
        severity=_optional_string(value.get("severity")) or "error",
        recoverable=bool(value.get("recoverable", False)),
        related_ref=_optional_string(value.get("related_ref")),
        suggested_action=_optional_string(value.get("suggested_action")),
    )


def _parse_completion(value: object) -> Completion | None:
    if not isinstance(value, dict):
        return None
    return Completion(
        outcome=_required_string(value, "outcome"),
        scoped_completion=bool(value.get("scoped_completion", False)),
        evidence_summary=tuple(
            item
            for item in _list_or_empty(value.get("evidence_summary"))
            if isinstance(item, dict)
        ),
        missing_evidence=_tuple_strings(value.get("missing_evidence")),
        verification_status=_optional_string(value.get("verification_status")) or "unverified",
        terminal_outcome_ref=_optional_string(value.get("terminal_outcome_ref")),
    )


def _render_workspace_ref(workspace_ref: WorkspaceRef) -> dict[str, object]:
    rendered: dict[str, object] = {"runtime_kind": workspace_ref.runtime_kind}
    _set_if_not_none(rendered, "workspace_id", workspace_ref.workspace_id)
    _set_if_not_none(rendered, "root_path", workspace_ref.root_path)
    _set_if_not_none(rendered, "display_name", workspace_ref.display_name)
    _set_if_not_none(rendered, "mode", workspace_ref.mode)
    _set_if_not_none(rendered, "environment", workspace_ref.environment)
    return rendered


def _render_source_ref(source: SourceRef) -> dict[str, object]:
    rendered: dict[str, object] = {"kind": source.kind}
    _set_if_not_none(rendered, "surface", source.surface)
    _set_if_not_none(rendered, "adapter_id", source.adapter_id)
    _set_if_not_none(rendered, "conversation_id", source.conversation_id)
    _set_if_not_none(rendered, "message_id", source.message_id)
    _set_if_not_none(rendered, "parent_request_id", source.parent_request_id)
    _set_if_not_none(rendered, "trace_ref", source.trace_ref)
    return rendered


def _render_actor_ref(actor: ActorRef) -> dict[str, object]:
    rendered: dict[str, object] = {"kind": actor.kind}
    _set_if_not_none(rendered, "display_name", actor.display_name)
    _set_if_not_none(rendered, "actor_id", actor.actor_id)
    if actor.metadata:
        rendered["metadata"] = dict(actor.metadata)
    return rendered


def _render_warning(warning: WarningRecord) -> dict[str, object]:
    rendered: dict[str, object] = {
        "code": warning.code,
        "message": warning.message,
        "severity": warning.severity,
        "recoverable": warning.recoverable,
    }
    _set_if_not_none(rendered, "related_ref", warning.related_ref)
    _set_if_not_none(rendered, "suggested_action", warning.suggested_action)
    return rendered


def _render_error(error: ErrorRecord) -> dict[str, object]:
    rendered: dict[str, object] = {
        "code": error.code,
        "message": error.message,
        "severity": error.severity,
        "recoverable": error.recoverable,
    }
    _set_if_not_none(rendered, "related_ref", error.related_ref)
    _set_if_not_none(rendered, "suggested_action", error.suggested_action)
    return rendered


def _render_completion(completion: Completion) -> dict[str, object]:
    return {
        "outcome": completion.outcome,
        "scoped_completion": completion.scoped_completion,
        "evidence_summary": [dict(item) for item in completion.evidence_summary],
        "missing_evidence": list(completion.missing_evidence),
        "verification_status": completion.verification_status,
        "terminal_outcome_ref": completion.terminal_outcome_ref,
    }


def _set_if_not_none(target: dict[str, object], key: str, value: object | None) -> None:
    if value is not None:
        target[key] = value
