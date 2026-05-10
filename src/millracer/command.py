"""Small subprocess boundary for Pi and Millrace commands."""

from __future__ import annotations

import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CommandResult:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class ProcessHandle(Protocol):
    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...


class CommandExecutor(Protocol):
    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult: ...

    def start(
        self,
        args: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
    ) -> ProcessHandle: ...


class CommandError(RuntimeError):
    """Raised when an external command returns a non-zero exit code."""

    def __init__(self, result: CommandResult) -> None:
        self.result = result
        command = " ".join(result.args)
        detail = result.stderr.strip() or result.stdout.strip() or "no output"
        super().__init__(f"command failed ({result.returncode}): {command}\n{detail}")


class SubprocessExecutor:
    """Production command executor."""

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path,
        timeout_seconds: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        completed = subprocess.run(
            tuple(args),
            cwd=str(cwd),
            env=dict(env) if env is not None else None,
            timeout=timeout_seconds,
            text=True,
            capture_output=True,
            check=False,
        )
        return CommandResult(
            args=tuple(args),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def start(
        self,
        args: Sequence[str],
        *,
        cwd: Path,
        env: Mapping[str, str] | None = None,
    ) -> ProcessHandle:
        return subprocess.Popen(
            tuple(args),
            cwd=str(cwd),
            env=dict(env) if env is not None else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )


def require_success(result: CommandResult) -> CommandResult:
    if result.returncode != 0:
        raise CommandError(result)
    return result
