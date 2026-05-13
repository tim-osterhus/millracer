"""Workspace registry and resolution helpers for Millracer ops requests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from millracer.ops_models import OpsRequest


@dataclass(frozen=True, slots=True)
class WorkspaceRecord:
    workspace_id: str
    root_path: Path
    display_name: str | None = None
    default_mode: str | None = None
    tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkspaceRegistry:
    records: dict[str, WorkspaceRecord]
    default_workspace_id: str | None = None

    @classmethod
    def empty(cls) -> WorkspaceRegistry:
        return cls(records={}, default_workspace_id=None)

    def get(self, workspace_id: str | None) -> WorkspaceRecord | None:
        if workspace_id is None:
            return None
        return self.records.get(workspace_id)

    def default(self) -> WorkspaceRecord | None:
        return self.get(self.default_workspace_id)


@dataclass(frozen=True, slots=True)
class WorkspaceResolution:
    root_path: Path | None
    workspace_id: str | None
    strategy: str
    validated: bool
    mode: str | None = None
    display_name: str | None = None
    error_code: str | None = None


def resolve_workspace(
    request: OpsRequest,
    *,
    registry: WorkspaceRegistry,
    cli_workspace: Path | None = None,
    active_workspace_id: str | None = None,
    cwd: Path | None = Path("."),
) -> WorkspaceResolution:
    workspace_ref = request.workspace_ref
    if workspace_ref.workspace_id:
        record = registry.get(workspace_ref.workspace_id)
        if record is None:
            if workspace_ref.root_path:
                return _from_path(
                    Path(workspace_ref.root_path),
                    strategy="request_root_path",
                    workspace_id=workspace_ref.workspace_id,
                    mode=workspace_ref.mode,
                    display_name=workspace_ref.display_name,
                )
            return _unresolved("request_workspace_id", "workspace_unresolved")
        return _from_record(record, strategy="request_workspace_id", mode=workspace_ref.mode)

    if workspace_ref.root_path:
        return _from_path(
            Path(workspace_ref.root_path),
            strategy="request_root_path",
            workspace_id=workspace_ref.workspace_id,
            mode=workspace_ref.mode,
            display_name=workspace_ref.display_name,
        )

    if cli_workspace is not None:
        return _from_path(cli_workspace, strategy="cli_workspace", mode=workspace_ref.mode)

    active = registry.get(active_workspace_id)
    if active is not None:
        return _from_record(active, strategy="active_session", mode=workspace_ref.mode)

    default = registry.default()
    if default is not None:
        return _from_record(default, strategy="registry_default", mode=workspace_ref.mode)

    if cwd is not None:
        cwd_path = cwd.expanduser().resolve()
        if cwd_path.exists():
            return WorkspaceResolution(
                root_path=cwd_path,
                workspace_id=None,
                strategy="cwd",
                validated=True,
                mode=workspace_ref.mode,
            )

    return _unresolved("unresolved", "workspace_unresolved")


def _from_record(
    record: WorkspaceRecord,
    *,
    strategy: str,
    mode: str | None = None,
) -> WorkspaceResolution:
    root_path = record.root_path.expanduser().resolve()
    return WorkspaceResolution(
        root_path=root_path,
        workspace_id=record.workspace_id,
        strategy=strategy,
        validated=root_path.exists(),
        mode=mode or record.default_mode,
        display_name=record.display_name,
    )


def _from_path(
    path: Path,
    *,
    strategy: str,
    workspace_id: str | None = None,
    mode: str | None = None,
    display_name: str | None = None,
) -> WorkspaceResolution:
    root_path = path.expanduser().resolve()
    return WorkspaceResolution(
        root_path=root_path,
        workspace_id=workspace_id,
        strategy=strategy,
        validated=root_path.exists(),
        mode=mode,
        display_name=display_name,
    )


def _unresolved(strategy: str, error_code: str) -> WorkspaceResolution:
    return WorkspaceResolution(
        root_path=None,
        workspace_id=None,
        strategy=strategy,
        validated=False,
        error_code=error_code,
    )
