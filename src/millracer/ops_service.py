"""Deterministic dispatcher for Millracer ops requests."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from millracer.agent import RunOptions, RunResult
from millracer.ops_models import (
    SCHEMA_VERSION,
    Completion,
    ErrorRecord,
    OpsEventFrame,
    OpsRequest,
    OpsResult,
    WarningRecord,
    WorkspaceRef,
)
from millracer.sessions import SessionStore
from millracer.workspaces import WorkspaceRegistry, WorkspaceResolution, resolve_workspace

RuntimeFactory = Callable[[WorkspaceResolution], object]
AgentFactory = Callable[[object, object | None, object | None], object]


@dataclass(slots=True)
class OpsService:
    runtime_factory: RuntimeFactory
    runner: object | None = None
    agent_factory: AgentFactory | None = None
    registry: WorkspaceRegistry = field(default_factory=WorkspaceRegistry.empty)
    session_store: SessionStore | None = None
    cli_workspace: Path | None = None
    cwd: Path | None = Path(".")

    def handle(self, request: OpsRequest) -> OpsResult:
        started_at = _now()
        if request.action == "list_workspaces":
            return self._list_workspaces_result(request, started_at=started_at)
        if request.action == "list_sessions":
            return self._list_sessions_result(request, started_at=started_at)
        if request.action == "select_workspace":
            return self._select_workspace_result(request, started_at=started_at)
        if request.action == "inspect_session":
            return self._inspect_session_result(request, started_at=started_at)

        resolution = resolve_workspace(
            request,
            registry=self.registry,
            cli_workspace=self.cli_workspace,
            cwd=self.cwd,
        )
        if resolution.error_code is not None or resolution.root_path is None:
            return self._error_result(
                request,
                started_at=started_at,
                resolution=resolution,
                error=ErrorRecord(
                    code=resolution.error_code or "workspace_unresolved",
                    message="Unable to resolve Millrace workspace.",
                    recoverable=True,
                    suggested_action="Pass workspace_ref.root_path or register/select a workspace.",
                ),
            )

        if request.action == "status":
            return self._status_result(request, started_at=started_at, resolution=resolution)
        if request.action == "enqueue":
            return self._enqueue_result(request, started_at=started_at, resolution=resolution)

        return self._error_result(
            request,
            started_at=started_at,
            resolution=resolution,
            error=ErrorRecord(
                code="unsupported_action",
                message=f"Unsupported Millracer ops action: {request.action}",
                recoverable=True,
                suggested_action="Use status or enqueue in this Millracer version.",
            ),
        )

    def _list_workspaces_result(self, request: OpsRequest, *, started_at: str) -> OpsResult:
        workspaces = [
            {
                "workspace_id": record.workspace_id,
                "root_path": str(record.root_path),
                "display_name": record.display_name,
                "default_mode": record.default_mode,
                "tags": list(record.tags),
                "is_default": workspace_id == self.registry.default_workspace_id,
            }
            for workspace_id, record in sorted(self.registry.records.items())
        ]
        return self._success_result(
            request,
            started_at=started_at,
            result={"workspaces": workspaces},
            route="inspect_only",
        )

    def _list_sessions_result(self, request: OpsRequest, *, started_at: str) -> OpsResult:
        sessions = () if self.session_store is None else self.session_store.list_sessions()
        return self._success_result(
            request,
            started_at=started_at,
            result={"sessions": [session.to_jsonable() for session in sessions]},
            route="inspect_only",
        )

    def _select_workspace_result(self, request: OpsRequest, *, started_at: str) -> OpsResult:
        if self.session_store is None:
            return self._error_result(
                request,
                started_at=started_at,
                resolution=_empty_resolution(),
                error=ErrorRecord(
                    code="session_store_unavailable",
                    message="select_workspace requires a session store.",
                    recoverable=True,
                ),
            )
        payload = _payload(request.input)
        workspace_id = _optional_string(payload.get("workspace_id"))
        session_id = _optional_string(payload.get("session_id")) or "local"
        if workspace_id is None or self.registry.get(workspace_id) is None:
            return self._error_result(
                request,
                started_at=started_at,
                resolution=_empty_resolution(),
                error=ErrorRecord(
                    code="workspace_unresolved",
                    message="select_workspace requires a registered workspace_id.",
                    recoverable=True,
                ),
            )
        record = self.registry.get(workspace_id)
        session = self.session_store.update_selection(
            session_id,
            workspace_id=workspace_id,
            mode=None if record is None else record.default_mode,
        )
        return self._success_result(
            request,
            started_at=started_at,
            result={"session": session.to_jsonable()},
            route="inspect_only",
            session_ref=session.session_id,
        )

    def _inspect_session_result(self, request: OpsRequest, *, started_at: str) -> OpsResult:
        sessions = () if self.session_store is None else self.session_store.list_sessions()
        payload = _payload(request.input)
        session_id = _optional_string(payload.get("session_id"))
        selected = next(
            (session for session in sessions if session.session_id == session_id),
            None,
        )
        return self._success_result(
            request,
            started_at=started_at,
            result={"session": None if selected is None else selected.to_jsonable()},
            route="inspect_only",
            session_ref=session_id,
        )

    def preview_events(self, request: OpsRequest) -> tuple[OpsEventFrame, ...]:
        timestamp = _now()
        return (
            OpsEventFrame(
                schema_version=SCHEMA_VERSION,
                request_id=request.request_id,
                event_id=f"{request.request_id}-accepted",
                sequence=1,
                timestamp=timestamp,
                event_type="request.accepted",
                severity="info",
                message="Request accepted.",
                payload={"action": request.action},
                cursor="1",
            ),
        )

    def _status_result(
        self,
        request: OpsRequest,
        *,
        started_at: str,
        resolution: WorkspaceResolution,
    ) -> OpsResult:
        runtime = self.runtime_factory(resolution)
        try:
            status_payload = _call_status(runtime)
        except Exception as exc:
            return self._error_result(
                request,
                started_at=started_at,
                resolution=resolution,
                error=ErrorRecord(
                    code="runtime_command_failed",
                    message=str(exc),
                    recoverable=True,
                ),
            )
        return OpsResult(
            schema_version=SCHEMA_VERSION,
            request_id=request.request_id,
            status="succeeded",
            action=request.action,
            workspace_ref=_workspace_ref_for_resolution(request, resolution),
            started_at=started_at,
            finished_at=_now(),
            warnings=(),
            errors=(),
            result=status_payload,
            route="status_only",
            completion=Completion(
                outcome="unknown",
                scoped_completion=False,
                verification_status="not_applicable",
            ),
        )

    def _success_result(
        self,
        request: OpsRequest,
        *,
        started_at: str,
        result: Mapping[str, object],
        route: str,
        session_ref: str | None = None,
    ) -> OpsResult:
        return OpsResult(
            schema_version=SCHEMA_VERSION,
            request_id=request.request_id,
            status="succeeded",
            action=request.action,
            workspace_ref=request.workspace_ref,
            started_at=started_at,
            finished_at=_now(),
            warnings=(),
            errors=(),
            result=result,
            route=route,
            completion=Completion(
                outcome="unknown",
                scoped_completion=False,
                verification_status="not_applicable",
            ),
            session_ref=session_ref,
        )

    def _enqueue_result(
        self,
        request: OpsRequest,
        *,
        started_at: str,
        resolution: WorkspaceResolution,
    ) -> OpsResult:
        if self.agent_factory is None:
            return self._error_result(
                request,
                started_at=started_at,
                resolution=resolution,
                error=ErrorRecord(
                    code="unsupported_action",
                    message="enqueue requires an agent factory for this transport.",
                    recoverable=True,
                ),
            )
        task = _task_text(request.input)
        if task is None:
            return self._error_result(
                request,
                started_at=started_at,
                resolution=resolution,
                error=ErrorRecord(
                    code="invalid_input",
                    message="enqueue requires input.text or input.payload.task.",
                    recoverable=True,
                ),
            )
        runtime = self.runtime_factory(resolution)
        agent = self.agent_factory(runtime, self.runner, None)
        run_result = agent.run(
            task,
            options=RunOptions(
                workspace=resolution.root_path or Path("."),
                cwd=resolution.root_path or Path("."),
                route=_route_for_request(request),
                scoped_work_item=request.scoped_work_item,
                intake=_intake_for_request(request),
            ),
        )
        return _ops_result_from_run_result(
            request,
            run_result,
            started_at=started_at,
            resolution=resolution,
            task=task,
        )

    def _error_result(
        self,
        request: OpsRequest,
        *,
        started_at: str,
        resolution: WorkspaceResolution,
        error: ErrorRecord,
    ) -> OpsResult:
        return OpsResult(
            schema_version=SCHEMA_VERSION,
            request_id=request.request_id,
            status="failed",
            action=request.action,
            workspace_ref=_workspace_ref_for_resolution(request, resolution),
            started_at=started_at,
            finished_at=_now(),
            warnings=(),
            errors=(error,),
            result={},
            completion=Completion(
                outcome="unknown",
                scoped_completion=False,
                verification_status="unverified",
            ),
        )


def _ops_result_from_run_result(
    request: OpsRequest,
    run_result: RunResult,
    *,
    started_at: str,
    resolution: WorkspaceResolution,
    task: str,
) -> OpsResult:
    completion = Completion(
        outcome=run_result.outcome,
        scoped_completion=run_result.scoped_completion,
        evidence_summary=run_result.completion_evidence,
        missing_evidence=()
        if run_result.scoped_completion
        else ("positive scoped completion evidence",),
        verification_status="verified" if run_result.scoped_completion else "unverified",
    )
    return OpsResult(
        schema_version=SCHEMA_VERSION,
        request_id=request.request_id,
        status=_status_for_outcome(run_result),
        action=request.action,
        workspace_ref=_workspace_ref_for_resolution(request, resolution),
        started_at=started_at,
        finished_at=_now(),
        warnings=tuple(_warning_from_text(warning) for warning in run_result.warnings),
        errors=(),
        result={
            "task": task,
            "output": run_result.output,
            "event": None
            if run_result.event is None
            else {
                "kind": run_result.event.kind,
                "workspace": run_result.event.workspace,
                "reason": run_result.event.reason,
            },
            "task_path": None if run_result.task_path is None else str(run_result.task_path),
            "status": run_result.status,
        },
        route=run_result.route,
        intake_kind=run_result.intake_kind,
        scoped_work_item=run_result.scoped_work_item or request.scoped_work_item,
        completion=completion,
        raw_compat=run_result.to_jsonable(),
    )


def _workspace_ref_for_resolution(
    request: OpsRequest,
    resolution: WorkspaceResolution,
) -> WorkspaceRef:
    return WorkspaceRef(
        workspace_id=resolution.workspace_id or request.workspace_ref.workspace_id,
        root_path=None if resolution.root_path is None else str(resolution.root_path),
        display_name=resolution.display_name or request.workspace_ref.display_name,
        runtime_kind=request.workspace_ref.runtime_kind,
        mode=resolution.mode or request.workspace_ref.mode,
        environment=request.workspace_ref.environment,
    )


def _call_status(runtime: object) -> dict[str, object]:
    status = getattr(runtime, "status", None)
    if not callable(status):
        raise RuntimeError("runtime does not support status")
    payload = status()
    if not isinstance(payload, dict):
        raise RuntimeError("runtime status must return an object")
    return payload


def _payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    nested = payload.get("payload")
    return nested if isinstance(nested, dict) else payload


def _optional_string(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _task_text(payload: Mapping[str, object]) -> str | None:
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    nested = payload.get("payload")
    if isinstance(nested, dict):
        task = nested.get("task") or nested.get("text")
        if isinstance(task, str) and task.strip():
            return task.strip()
    return None


def _route_for_request(request: OpsRequest) -> str:
    if request.route_preference in {"auto", "direct", "millrace"}:
        return request.route_preference
    return "auto"


def _intake_for_request(request: OpsRequest) -> str:
    if request.intake_preference in {"auto", "probe", "idea", "task"}:
        return request.intake_preference
    return "auto"


def _status_for_outcome(result: RunResult) -> str:
    if result.outcome == "completed" and result.scoped_completion:
        return "succeeded"
    if result.outcome == "blocked":
        return "blocked"
    if result.outcome in {"restart_needed", "crashed"}:
        return "failed"
    if result.outcome == "incomplete":
        return "incomplete"
    return "failed"


def _warning_from_text(text: str) -> WarningRecord:
    return WarningRecord(
        code="runtime_warning",
        message=text,
        recoverable=True,
    )


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _empty_resolution() -> WorkspaceResolution:
    return WorkspaceResolution(
        root_path=None,
        workspace_id=None,
        strategy="not_required",
        validated=False,
    )
