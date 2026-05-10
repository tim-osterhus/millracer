"""Pi command wrapper used as Millracer's base harness."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from millracer.command import CommandExecutor, SubprocessExecutor, require_success
from millracer.prompts import MILLRACER_SYSTEM_PROMPT


@dataclass(frozen=True, slots=True)
class PiConfig:
    command: str = "pi"
    provider: str | None = None
    model: str | None = None
    thinking: str | None = "high"
    skill_paths: tuple[Path, ...] = ()
    extra_args: tuple[str, ...] = ()


@dataclass(slots=True)
class PiHarness:
    config: PiConfig = field(default_factory=PiConfig)
    executor: CommandExecutor = field(default_factory=SubprocessExecutor)

    def complete(
        self,
        prompt: str,
        *,
        cwd: Path,
        timeout_seconds: int | None = None,
    ) -> str:
        result = require_success(
            self.executor.run(
                self.build_command(prompt),
                cwd=cwd,
                timeout_seconds=timeout_seconds,
            )
        )
        return result.stdout.rstrip("\n")

    def build_command(self, prompt: str) -> tuple[str, ...]:
        args: list[str] = [
            self.config.command,
            "--print",
            "--no-context-files",
            "--append-system-prompt",
            MILLRACER_SYSTEM_PROMPT,
        ]
        if self.config.provider:
            args.extend(["--provider", self.config.provider])
        if self.config.model:
            args.extend(["--model", self.config.model])
        if self.config.thinking:
            args.extend(["--thinking", self.config.thinking])
        for skill_path in self.config.skill_paths:
            args.extend(["--skill", str(skill_path)])
        args.extend(self.config.extra_args)
        args.append(prompt)
        return tuple(args)


def discover_default_skill_paths(*, start: Path | None = None) -> tuple[Path, ...]:
    """Find repo-local Millrace operator skills in the standard dev layout."""

    start_path = (start or Path(__file__).resolve()).resolve()
    roots: Sequence[Path] = (start_path, *start_path.parents)
    skill_dirs = (
        "millrace-autonomous-delegation",
        "millrace-ops-agent-manual",
    )
    for root in roots:
        for relative_root in (
            Path("dev/source/millrace/docs/skills"),
            Path("source/millrace/docs/skills"),
        ):
            candidate = root / relative_root
            paths = tuple(candidate / item for item in skill_dirs)
            if all(path.exists() for path in paths):
                return paths
    return ()
