from __future__ import annotations

from pathlib import Path

from millracer.ops_models import SCHEMA_VERSION, OpsRequest, SourceRef, WorkspaceRef
from millracer.workspaces import WorkspaceRecord, WorkspaceRegistry, resolve_workspace


def _request(workspace_ref: WorkspaceRef) -> OpsRequest:
    return OpsRequest(
        schema_version=SCHEMA_VERSION,
        request_id="req-001",
        action="status",
        workspace_ref=workspace_ref,
        source=SourceRef(kind="cli"),
        input={"kind": "structured_action", "payload": {}},
    )


def test_workspace_resolution_prefers_request_root_path(tmp_path: Path) -> None:
    result = resolve_workspace(
        _request(WorkspaceRef(root_path=str(tmp_path))),
        registry=WorkspaceRegistry.empty(),
    )

    assert result.root_path == tmp_path.resolve()
    assert result.strategy == "request_root_path"
    assert result.validated is True


def test_workspace_resolution_prefers_request_workspace_id(tmp_path: Path) -> None:
    registry = WorkspaceRegistry(
        records={
            "millrace-os": WorkspaceRecord(
                workspace_id="millrace-os",
                root_path=tmp_path,
                display_name="Millrace OS",
                default_mode="learning_codex",
            )
        },
        default_workspace_id=None,
    )

    result = resolve_workspace(
        _request(WorkspaceRef(workspace_id="millrace-os")),
        registry=registry,
    )

    assert result.root_path == tmp_path.resolve()
    assert result.workspace_id == "millrace-os"
    assert result.strategy == "request_workspace_id"
    assert result.mode == "learning_codex"


def test_workspace_resolution_falls_back_to_request_root_when_id_is_unknown(
    tmp_path: Path,
) -> None:
    result = resolve_workspace(
        _request(
            WorkspaceRef(
                workspace_id="unknown",
                root_path=str(tmp_path),
                mode="learning_codex",
            )
        ),
        registry=WorkspaceRegistry.empty(),
    )

    assert result.root_path == tmp_path.resolve()
    assert result.workspace_id == "unknown"
    assert result.strategy == "request_root_path"
    assert result.mode == "learning_codex"


def test_workspace_resolution_uses_cli_default_before_registry_default(tmp_path: Path) -> None:
    registry_root = tmp_path / "registry"
    registry_root.mkdir()
    cli_root = tmp_path / "cli"
    cli_root.mkdir()
    registry = WorkspaceRegistry(
        records={
            "default": WorkspaceRecord(
                workspace_id="default",
                root_path=registry_root,
            )
        },
        default_workspace_id="default",
    )

    result = resolve_workspace(
        _request(WorkspaceRef()),
        registry=registry,
        cli_workspace=cli_root,
    )

    assert result.root_path == cli_root.resolve()
    assert result.strategy == "cli_workspace"


def test_workspace_resolution_reports_unresolved_without_guessing() -> None:
    result = resolve_workspace(
        _request(WorkspaceRef()),
        registry=WorkspaceRegistry.empty(),
        cwd=None,
    )

    assert result.root_path is None
    assert result.error_code == "workspace_unresolved"
