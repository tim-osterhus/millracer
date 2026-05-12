"""Generic Millrace intake-kind selection for Millracer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class IntakeKind(StrEnum):
    AUTO = "auto"
    PROBE = "probe"
    IDEA = "idea"
    TASK = "task"


@dataclass(frozen=True, slots=True)
class IntakeDecision:
    intake_kind: IntakeKind
    confidence: str
    signals: tuple[str, ...] = ()


class DecisionLike(Protocol):
    intake_kind: str | None
    signals: tuple[str, ...]


_SOURCE_PATH_RE = re.compile(
    r"(?<![\w.-])[\w./-]+\.(?:py|pyi|js|jsx|ts|tsx|rs|go|java|c|cc|cpp|h|hpp|"
    r"md|rst|toml|yaml|yml|json|ini|cfg|css|scss|html)(?:::[\w.-]+)?"
)
_TEST_PATH_RE = re.compile(r"(?:^|[\s/])tests?/|\btest_[\w.-]+|\bpytest\b|::test_", re.I)


def normalize_intake_kind(value: object, *, allow_auto: bool = True) -> IntakeKind | None:
    raw = str(value or "").strip().lower()
    allowed = {IntakeKind.PROBE, IntakeKind.IDEA, IntakeKind.TASK}
    if allow_auto:
        allowed.add(IntakeKind.AUTO)
    for kind in allowed:
        if raw == kind.value:
            return kind
    return None


def choose_intake_kind(
    task: str,
    *,
    requested: IntakeKind | str = IntakeKind.AUTO,
    decision: DecisionLike | None = None,
) -> IntakeDecision:
    requested_kind = normalize_intake_kind(requested) or IntakeKind.AUTO
    if requested_kind is not IntakeKind.AUTO:
        return IntakeDecision(
            intake_kind=requested_kind,
            confidence="high",
            signals=(f"forced --intake {requested_kind.value}",),
        )

    decision_kind = normalize_intake_kind(
        None if decision is None else decision.intake_kind,
        allow_auto=False,
    )
    if decision_kind is not None:
        return IntakeDecision(
            intake_kind=decision_kind,
            confidence="medium",
            signals=tuple(decision.signals) if decision is not None else (),
        )

    signals = _signals_for_task(task)
    if "exact local file and test" in signals:
        return IntakeDecision(IntakeKind.TASK, "medium", signals)
    if _has_probe_signal(signals):
        return IntakeDecision(IntakeKind.PROBE, "medium", signals)
    if _has_idea_signal(signals):
        return IntakeDecision(IntakeKind.IDEA, "medium", signals)
    if "exact local file" in signals and _has_local_fix_signal(task):
        return IntakeDecision(IntakeKind.TASK, "medium", signals)
    return IntakeDecision(
        IntakeKind.PROBE,
        "low",
        ("uncertain delegated repo work",),
    )


def _signals_for_task(task: str) -> tuple[str, ...]:
    text = task.lower()
    signals: list[str] = []
    has_file = bool(_SOURCE_PATH_RE.search(task))
    has_test = bool(_TEST_PATH_RE.search(task)) or "failing test" in text
    if has_file and has_test:
        signals.append("exact local file and test")
    elif has_file:
        signals.append("exact local file")

    if "large pre-existing codebase" in text or "pre-existing codebase" in text:
        signals.append("large pre-existing codebase")
    if "uncertain" in text or "affected files" in text or "affected surface" in text:
        signals.append("uncertain affected files")
    if "understand the codebase" in text or "before changing" in text:
        signals.append("understand before changing")
    if "migration" in text or "migrate" in text or "refactor" in text:
        signals.append("migration or refactor")
    if (
        "compatibility" in text
        or "regression" in text
        or "neighboring module" in text
        or "existing convention" in text
        or "cross-module" in text
        or "repo-wide" in text
        or "repository-wide" in text
    ):
        signals.append("compatibility or regression risk")
    if (
        "build a new" in text
        or "add a new" in text
        or "capability" in text
        or "dashboard" in text
        or "user-facing" in text
        or "operator-visible" in text
        or "workflow" in text
        or "tool behavior" in text
    ):
        signals.append("clear outcome needing shaping")
    return tuple(dict.fromkeys(signals))


def _has_probe_signal(signals: tuple[str, ...]) -> bool:
    return any(
        signal
        in {
            "large pre-existing codebase",
            "uncertain affected files",
            "understand before changing",
            "migration or refactor",
            "compatibility or regression risk",
        }
        for signal in signals
    )


def _has_idea_signal(signals: tuple[str, ...]) -> bool:
    return "clear outcome needing shaping" in signals


def _has_local_fix_signal(task: str) -> bool:
    text = task.lower()
    return any(
        phrase in text
        for phrase in (
            "fix",
            "mechanical",
            "exact",
            "local",
            "only",
            "acceptance",
        )
    )
