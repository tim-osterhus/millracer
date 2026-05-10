"""Prompt templates injected into the Pi-backed outer harness."""

from __future__ import annotations

MILLRACER_SYSTEM_PROMPT = """\
You are Millracer, a Pi-backed outer agent that can either work directly or
delegate substantial work into Millrace.

Millrace is a durable runtime for long-running software work. Use it when work
benefits from a queue, staged execution, recovery, daemon persistence, run
artifacts, or Arbiter-based closure. Stay direct for small bounded questions,
quick local edits, and tasks where runtime overhead would exceed the work.

When Millrace is selected, operate it through the CLI only. Do not mutate
runtime-owned files directly. Prefer `default_pi` unless the task explicitly
needs the learning plane or a custom loop. If repo-local Millrace skills are
loaded, follow them as the detailed source of truth.

These are standing Millracer instructions. Treat daemon-completion events as
normal follow-up prompts inside the same operator session.
"""


def decision_prompt(task: str) -> str:
    return f"""\
Decide whether this task should be handled directly by the outer Pi harness or
delegated into Millrace.

Return only JSON with this shape:
{{
  "decision": "direct|millrace",
  "why": "<one sentence>",
  "mode": "default_pi|learning_pi",
  "custom_loop_needed": false,
  "notes": "<optional concise note>"
}}

Use `millrace` for substantial, multi-stage, recovery-sensitive, or
closure-sensitive work. Use `direct` for small bounded work. Set
`custom_loop_needed` to true only when the task appears to need a non-standard
Millrace loop or mode before delegation would be honest.

Task:
{task}
"""


def direct_prompt(task: str) -> str:
    return f"""\
Handle this task directly in the current repository. Millrace was judged
unnecessary for this request.

Task:
{task}
"""


def finalization_prompt(
    *,
    task: str,
    workspace: str,
    event_kind: str,
    event_reason: str,
    status_json: str,
    warnings: tuple[str, ...] = (),
) -> str:
    warning_text = "\n".join(f"- {warning}" for warning in warnings) or "- none"
    return f"""\
Millrace emitted this terminal event for delegated work:

- workspace: {workspace}
- event: {event_kind}
- reason: {event_reason}

Original task:
{task}

Latest Millrace status JSON:
{status_json}

Millracer warnings:
{warning_text}

Inspect the workspace and Millrace run evidence as needed, then return the
final benchmark-facing answer. Be explicit about whether the delegated run
completed, blocked, or needs follow-up.
"""
