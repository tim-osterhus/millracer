# Millracer

Millracer is a Pi-backed Millrace operator harness. It keeps a persistent outer
Pi RPC session, injects Millrace-aware operator instructions, and can either
work directly or delegate substantial work into Millrace.

Millracer is meant to be usable in two ways:

- as a persistent operator you can talk to directly
- as a one-shot command that benchmark harnesses such as EvoClaw can call

## Requirements

Install these first:

- Python 3.11 or newer
- `pi` on `PATH`
- `millrace` on `PATH`
- model/API credentials configured for Pi

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

After this repo is available on GitHub, direct install is:

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

Use `run` when another tool or benchmark needs one command that returns one
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

## Benchmark JSON

For benchmark adapters, pass task input as JSON on stdin:

```bash
printf '{"task":"Fix the project and run the tests","workspace":"/path/to/workspace"}' \
  | millracer run --benchmark-json --output json
```

The JSON input accepts `task`, `prompt`, or `instructions`, plus an optional
`workspace`. The JSON output includes the selected route, decision metadata,
warnings, Millrace event data, task path, status payload, and final answer.

## Common Options

- `--route auto|direct|millrace`: let Pi choose, force direct work, or force
  Millrace delegation.
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

1. receive one task
2. ask Pi whether the task should stay direct or enter Millrace
3. run direct work through Pi when Millrace is unnecessary
4. enqueue and monitor Millrace work when durable staged execution is useful
5. inject daemon-completion events back into Pi for final inspection

The goal is a dedicated Millrace-equipped operator that is still easy to drive
from benchmark infrastructure. Benchmarks can use one-shot `run`; humans and
longer operator sessions can use persistent `operator`.

By default, Millracer uses:

- `pi` as the outer harness
- `millrace` as the runtime CLI
- `default_pi` as the Millrace mode for delegated work
- `high` Pi thinking for the outer agent
- a persistent Pi RPC session for the full Millracer run

The automatic decision turn can flag that a custom Millrace loop appears
necessary. Millracer preserves that signal in JSON output and emits a text-mode
warning, but it still delegates with the selected `--millrace-mode`. Pass a
custom mode explicitly when the benchmark setup has one available.

## Routes

Use `--route auto` for the default Pi decision turn. Use `--route direct` or
`--route millrace` to force a path:

```bash
python -m millracer run --route direct "Summarize README.md"
python -m millracer run --route millrace "Implement the pending refactor spec"
```

Use `--output json` when driving benchmark infrastructure.

## Benchmark Semantics

The daemon monitor is synchronous inside one delegated task. During that task,
Millracer waits for a terminal Millrace event before returning to the caller.
The outer Pi session remains persistent across the decision, daemon-completion
notification, and finalization turns, and `operator` keeps it alive across
multiple tasks.

Millracer also does not automatically retry crashed or blocked Millrace runs or
fall back to direct execution. It reports those events to the final Pi turn so
benchmark output reflects the real delegated run rather than hiding failures.

For delegated tasks, Millracer writes an intake task under `.millracer/intake/`
and passes that file to `millrace queue add-task`. Millrace accepts arbitrary
readable task markdown paths there and copies the parsed document into its
managed queue.

The current finalization turn combines two jobs: notification that a daemon
finished and production of the benchmark-facing answer. The `MonitorEvent`
boundary keeps the hook seam explicit so a later version can chain follow-up
delegations before finalizing.
