"""Persistent Millracer operator loop."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from millracer.agent import MillracerAgent, RunOptions, RunResult


class Closable(Protocol):
    def close(self) -> None: ...


@dataclass(slots=True)
class MillracerOperator:
    """Reusable operator around one persistent outer Pi session."""

    agent: MillracerAgent
    pi: Closable
    workspace: Path
    cwd: Path
    route: str = "auto"
    daemon_timeout_seconds: float = 7200.0
    pi_timeout_seconds: int | None = None
    keep_daemon: bool = False
    max_daemon_restarts: int = 1

    def handle(self, task: str) -> RunResult:
        return self.agent.run(
            task,
            options=RunOptions(
                workspace=self.workspace,
                cwd=self.cwd,
                route=self.route,
                daemon_timeout_seconds=self.daemon_timeout_seconds,
                pi_timeout_seconds=self.pi_timeout_seconds,
                keep_daemon=self.keep_daemon,
                max_daemon_restarts=self.max_daemon_restarts,
            ),
        )

    def close(self) -> None:
        self.pi.close()
