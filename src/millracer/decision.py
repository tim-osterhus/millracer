"""Decision parsing for the outer Millracer agent."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Decision:
    route: str
    why: str
    mode: str = "default_pi"
    custom_loop_needed: bool = False
    notes: str = ""
    intake_kind: str | None = None
    signals: tuple[str, ...] = ()


_JSON_FENCE = re.compile(r"```(?:json)?\s*(?P<body>\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_ROUTE_LINE = re.compile(
    r"^\s*decision\s*:\s*(?P<route>direct|millrace)\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_WHY_LINE = re.compile(r"^\s*why\s*:\s*(?P<why>.+?)\s*$", re.IGNORECASE | re.MULTILINE)


def parse_decision(raw: str) -> Decision:
    payload = _load_decision_payload(raw)
    if payload is not None:
        route = _normalize_route(payload.get("decision") or payload.get("route"))
        why = str(payload.get("why") or "").strip() or "Pi selected this route."
        mode = str(payload.get("mode") or "default_pi").strip() or "default_pi"
        return Decision(
            route=route,
            why=why,
            mode=mode,
            custom_loop_needed=bool(payload.get("custom_loop_needed", False)),
            notes=str(payload.get("notes") or "").strip(),
            intake_kind=_normalize_intake_kind(payload.get("intake_kind")),
            signals=_normalize_signals(payload.get("signals")),
        )

    route_match = _ROUTE_LINE.search(raw)
    route = _normalize_route(route_match.group("route") if route_match else "direct")
    why_match = _WHY_LINE.search(raw)
    why = why_match.group("why").strip() if why_match else "Pi returned unstructured output."
    return Decision(route=route, why=why)


def _load_decision_payload(raw: str) -> dict[str, Any] | None:
    candidates = [raw.strip()]
    match = _JSON_FENCE.search(raw)
    if match is not None:
        candidates.insert(0, match.group("body").strip())

    for candidate in candidates:
        if not candidate.startswith("{"):
            continue
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _normalize_route(value: object) -> str:
    route = str(value or "").strip().lower()
    if route not in {"direct", "millrace"}:
        return "direct"
    return route


def _normalize_intake_kind(value: object) -> str | None:
    intake_kind = str(value or "").strip().lower()
    if intake_kind not in {"probe", "idea", "task"}:
        return None
    return intake_kind


def _normalize_signals(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    signals: list[str] = []
    for item in value:
        signal = str(item or "").strip()
        if signal:
            signals.append(signal)
    return tuple(signals)
