# Millracer

Millracer is the local ops gateway for Millrace OS. It turns CLI, Mission
Control, channel adapter, agent, and future API/MCP requests into typed
Millrace runtime actions with structured evidence, warnings, and recovery
behavior.

Millracer is meant to be usable in three ways:

- as a typed JSON ops boundary for software callers
- as a persistent operator you can talk to directly
- as a one-shot natural-language command that external automation can call

## Requirements

Install these first:

- Python 3.11 or newer
- `millrace` on `PATH`
- `pi` on `PATH` when using natural-language direct work or delegated
  finalization
- model/API credentials configured for the selected runner backend when a
  runner is used

For local development, install `uv` as well.

## Download

From GitHub:

```bash
git clone https://github.com/tim-osterhus/millracer.git
cd millracer
```

From inside the Millrace development workspace, the repo lives at:

```bash
cd /Users/timinator/Desktop/Millrace-Dev/dev/harness/millracer
```

## Install

From PyPI:

```bash
pipx install millracer
```

Or with uv:

```bash
uv tool install millracer
```

For an isolated command-line install from a local checkout:

```bash
pipx install .
```

For editable development:

```bash
uv sync --extra dev
uv run millracer --help
```

You can also run without installing:

```bash
uv run --extra dev python -m millracer --help
```

Direct install from GitHub is:

```bash
pipx install git+https://github.com/tim-osterhus/millracer
```

## Persistent Operator

Use `operator` for normal Millracer operation:

```bash
millracer operator --workspace /path/to/workspace
```

In a development checkout:

```bash
uv run --extra dev python -m millracer operator --workspace /path/to/workspace
```

This opens a small line prompt:

```text
Millracer operator ready. Type /exit to quit.
millracer>
```

`operator` starts one Pi RPC session and reuses it across every task you enter.
Type `/exit` or `/quit` to close the session.

## One-Shot Run

Use `run` when another tool needs one command that returns one
answer:

```bash
millracer run --workspace /path/to/workspace "Fix the failing tests"
```

In a development checkout:

```bash
uv run --extra dev python -m millracer run \
  --workspace /path/to/workspace \
  "Fix the failing tests"
```

`run` also defaults to a persistent Pi RPC session for that single task, so the
decision turn and the finalization turn share one Pi conversation. For
compatibility debugging, `--pi-session print` uses one fresh `pi --print`
process per Pi turn.

## Ops JSON

Use `ops --json` when Mission Control, a channel adapter, or another software
caller needs the stable Millrace OS command boundary:

```bash
millracer ops --json < request.json
```

The request and result use schema version `millracer.ops.v0.2`:

```json
{
  "schema_version": "millracer.ops.v0.2",
  "request_id": "req-001",
  "workspace_ref": {
    "root_path": "/path/to/workspace",
    "mode": "learning_codex"
  },
  "source": {
    "kind": "mission_control",
    "surface": "command_panel"
  },
  "action": "status",
  "input": {
    "kind": "structured_action",
    "payload": {}
  }
}
```

Current structured actions include `status`, `enqueue`, `list_workspaces`,
`select_workspace`, `list_sessions`, and `inspect_session`. Unsupported actions
return machine-readable errors instead of falling through to arbitrary shell
execution.

`OpsResult` includes structured `warnings`, `errors`, `result`, and
`completion` fields. Runtime completion is never inferred from text alone. For
scoped delegated work, callers should gate external completion on:

```json
{
  "completion": {
    "scoped_completion": true
  }
}
```

`--stream-json` is reserved for event-frame streaming and currently returns a
structured `unsupported_transport` result.

## Legacy JSON

For callers still using the earlier one-shot compatibility shape, pass task
input as JSON on stdin:

```bash
printf '{"task":"Fix the project and run the tests","workspace":"/path/to/workspace"}' \
  | millracer run --benchmark-json --output json
```

The JSON input accepts `task`, `prompt`, or `instructions`, plus an optional
`workspace` and optional `intake_kind`. The option name is still
`--benchmark-json` for CLI compatibility. New product integrations should use
`millracer ops --json`.

The legacy JSON output includes the selected route, intake kind, decision
metadata, warnings, Millrace event data, intake document path, status payload,
progress events, final outcome, scoped completion flag, completion evidence,
and final answer.

Adapters for streaming queues should pass exactly one selected item at a time
using `scoped_work_item`:

```json
{
  "task": "Implement the selected queue item only.",
  "workspace": "/path/to/workspace",
  "intake_kind": "probe",
  "scoped_work_item": {
    "item_id": "ITEM-123",
    "title": "Fix the selected failure",
    "source_queue": "/path/to/TASK_QUEUE.md",
    "spec_path": "/path/to/specs/ITEM-123.md",
    "completion_ref": "submit-ITEM-123",
    "constraints": ["Do not implement or submit any other queue item."]
  }
}
```

Millracer writes this metadata into the Millrace intake task as the scoped-work
contract. The delegated agent is told not to batch independent queue items and
not to create completion signals for any item other than the selected one.
External callers should treat `scoped_completion: true` as the signal that the
selected scoped item completed. A drained daemon without scoped completion
evidence returns `outcome: "incomplete"` and must not be treated as selected
item completion.

## Intake Kinds

Millracer chooses both route and intake kind:

- `probe`: investigation-first intake for uncertain codebase work.
- `idea`: planning/decomposition intake for clear outcomes that need shaping.
- `task`: execution intake for already-scoped local work.

Use `--intake auto` for the default behavior. Auto selection uses Pi's decision
when available, then a small deterministic fallback. For large pre-existing
codebases with uncertain affected files, auto selection biases toward `probe`.
Use `--intake task`, `--intake idea`, or `--intake probe` to force the intake
kind exactly.

Millracer dispatches the selected intake kind to the matching Millrace queue
command:

- `probe` -> `millrace queue add-probe`
- `idea` -> `millrace queue add-idea`
- `task` -> `millrace queue add-task`

## Common Options

- `--route auto|direct|millrace`: let Pi choose, force direct work, or force
  Millrace delegation.
- `--intake auto|probe|idea|task`: choose the Millrace intake kind for
  delegated work.
- `--workspace <path>`: Millrace workspace root and default command working
  directory.
- `--cwd <path>`: command working directory when it differs from the workspace.
- `--millrace-mode <mode>`: Millrace mode for delegated work, default
  `default_pi`.
- `--thinking <level>`: Pi thinking level for the outer operator, default
  `high`.
- `--provider <name>` / `--model <name>`: Pi provider/model selection.
- `--skill <path>`: load a Millrace operator skill package or `SKILL.md`.
- `--no-default-skills`: disable automatic skill discovery.
- `--daemon-timeout-seconds <n>`: maximum wait for a delegated Millrace run.
- `--notify-terminal-stages` / `--no-notify-terminal-stages`: notify the outer
  Pi session when meaningful terminal stages finish before full run drainage,
  default enabled.
- `--max-daemon-restarts <n>`: restart attempts after Millracer sees queued
  work with a stopped daemon, default `1`.
- `--output json`: machine-readable one-shot output.

## Skill Loading

When this repository lives in the standard Millrace development layout,
Millracer automatically loads the repo-local Millrace operator skills from
`../../source/millrace/docs/skills/`.

Outside that layout, pass skill paths explicitly:

```bash
millracer operator \
  --skill /path/to/millrace-autonomous-delegation \
  --skill /path/to/millrace-ops-agent-manual \
  --workspace /path/to/workspace
```

## How It Works

Millracer keeps the outer interface simple:

1. receive a typed ops request or one natural-language task
2. resolve workspace and mode
3. dispatch structured actions directly when no model interpretation is needed
4. use a runner backend for natural-language routing or direct work when needed
5. enqueue probe, idea, or task documents into Millrace when durable staged
   execution is useful
6. monitor runtime state and synthesize evidence-bearing results

The goal is a dedicated Millrace-equipped operator that is still easy to drive
from automation. Product surfaces should use `ops --json`; external
compatibility callers can use one-shot `run`; humans and longer operator
sessions can use persistent `operator`.

By default, Millracer uses:

- `millrace` as the runtime CLI
- `default_pi` as the Millrace mode for delegated work
- `pi` as the current runner backend when model-backed interpretation or
  finalization is needed
- `high` thinking for that runner
- a persistent Pi RPC session for natural-language `run` and `operator`
  workflows

The automatic decision turn can flag that a custom Millrace loop appears
necessary. Millracer preserves that signal in JSON output and emits a text-mode
warning, but it still delegates with the selected `--millrace-mode`. Pass a
custom mode explicitly when one is available.

## Workspace And Sessions

`OpsRequest.workspace_ref` can identify a workspace by `workspace_id` or
`root_path`. Resolution prefers request fields, then CLI workspace defaults,
then selected/default session context when available.

Millracer may persist operator session convenience state such as selected
workspace, selected mode, recent request IDs, and warning codes. It does not
persist queue truth, work-item lifecycle truth, traces, artifacts, approvals, or
terminal outcomes as session state. The Millrace runtime remains authoritative.

## Routes

Use `--route auto` for the default Pi decision turn. Use `--route direct` or
`--route millrace` to force a path:

```bash
python -m millracer run --route direct "Summarize README.md"
python -m millracer run --route millrace "Implement the pending refactor spec"
```

Use `--output json` when driving external automation.

## Delegation Semantics

The daemon monitor is synchronous inside one delegated task. During that task,
Millracer waits for a terminal Millrace event before returning to the caller.
The outer Pi session remains persistent across the decision, daemon-completion
notification, and finalization turns, and `operator` keeps it alive across
multiple tasks.

Millracer does not automatically retry blocked Millrace runs or fall back to
direct execution. It reports those events to the final Pi turn so output
reflects the real delegated run rather than hiding failures.

If Millracer sees queued work while the daemon is stopped, it classifies that
as `restart_needed`, clears stale Millrace state when needed, and restarts the
daemon up to `--max-daemon-restarts`. This is a lifecycle repair only; it does
not change the queued task or silently switch to direct execution.

For delegated work, Millracer writes an intake document under
`.millracer/intake/` and passes that file to `millrace queue add-probe`,
`millrace queue add-idea`, or `millrace queue add-task`. Millrace accepts
arbitrary readable markdown paths there and copies the parsed document into its
managed queue.

For dynamic queues, the caller should select one available item, load that
item's instructions, and call Millracer with `scoped_work_item`. Do not pass a
whole continuous-agent operating prompt as one broad task unless broad batching
is explicitly the requested work.

Terminal-stage notifications are default-on. Updater `UPDATE_COMPLETE` is a
progress event when other queues or closure targets remain; it is not treated
as global run closure. Arbiter completion is scoped completion evidence. Full
daemon idle without that evidence is a terminal `idle_no_work` event with an
`incomplete` outcome.

The current finalization turn combines two jobs: notification that a daemon
reached a terminal event and production of the final answer. The `MonitorEvent`
boundary keeps the hook explicit so a later version can chain follow-up
delegations before finalizing.
