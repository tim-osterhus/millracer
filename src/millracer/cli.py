"""Command-line entrypoint for Millracer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from millracer.agent import MillracerAgent, RunOptions
from millracer.benchmark import parse_benchmark_request, render_benchmark_result
from millracer.millrace import MillraceConfig, MillraceController
from millracer.monitor import DaemonMonitor
from millracer.operator import MillracerOperator
from millracer.pi import PiConfig, PiHarness, discover_default_skill_paths
from millracer.pi_rpc import PiRpcHarness
from millracer.scope import ScopedWorkItem


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return _run_once(args)
    if args.command == "operator":
        return _run_operator(args)
    else:
        parser.print_help()
        return 2


def _run_once(args: argparse.Namespace) -> int:
    pi = None
    try:
        task, workspace, scoped_work_item, request_intake = _task_workspace_and_scope(args)
        intake = args.intake if args.intake != "auto" else request_intake or args.intake
        cwd = Path(args.cwd or workspace).expanduser().resolve()
        workspace = workspace.expanduser().resolve()
        pi, agent = _build_agent(args, workspace=workspace, cwd=cwd)
        result = agent.run(
            task,
            options=RunOptions(
                workspace=workspace,
                cwd=cwd,
                route=args.route,
                daemon_timeout_seconds=args.daemon_timeout_seconds,
                pi_timeout_seconds=args.pi_timeout_seconds,
                keep_daemon=args.keep_daemon,
                scoped_work_item=scoped_work_item,
                max_daemon_restarts=args.max_daemon_restarts,
                intake=intake,
                notify_terminal_stages=args.notify_terminal_stages,
            ),
        )
    except Exception as exc:  # pragma: no cover - user-facing CLI boundary
        print(f"millracer: error: {exc}", file=sys.stderr)
        return 1
    finally:
        _close_if_needed(pi)

    if args.output == "json":
        print(render_benchmark_result(result))
    else:
        for warning in result.warnings:
            print(f"millracer: warning: {warning}", file=sys.stderr)
        print(result.output)
    return 0


def _run_operator(args: argparse.Namespace) -> int:
    pi = None
    try:
        workspace = args.workspace.expanduser().resolve()
        cwd = Path(args.cwd or workspace).expanduser().resolve()
        pi, agent = _build_agent(args, workspace=workspace, cwd=cwd, force_rpc=True)
        operator = MillracerOperator(
            agent=agent,
            pi=pi,
            workspace=workspace,
            cwd=cwd,
            route=args.route,
            daemon_timeout_seconds=args.daemon_timeout_seconds,
            pi_timeout_seconds=args.pi_timeout_seconds,
            keep_daemon=args.keep_daemon,
            max_daemon_restarts=args.max_daemon_restarts,
            intake=args.intake,
            notify_terminal_stages=args.notify_terminal_stages,
        )
        print("Millracer operator ready. Type /exit to quit.", file=sys.stderr)
        while True:
            try:
                task = input("millracer> ").strip()
            except EOFError:
                break
            if task in {"/exit", "/quit"}:
                break
            if not task:
                continue
            result = operator.handle(task)
            for warning in result.warnings:
                print(f"millracer: warning: {warning}", file=sys.stderr)
            print(result.output)
        return 0
    except Exception as exc:  # pragma: no cover - user-facing CLI boundary
        print(f"millracer: error: {exc}", file=sys.stderr)
        return 1
    finally:
        _close_if_needed(pi)


def _build_agent(
    args: argparse.Namespace,
    *,
    workspace: Path,
    cwd: Path,
    force_rpc: bool = False,
) -> tuple[object, MillracerAgent]:
    skill_paths = tuple(Path(path).expanduser().resolve() for path in args.skill)
    if not skill_paths and not args.no_default_skills:
        skill_paths = discover_default_skill_paths()

    config = PiConfig(
        command=args.pi_command,
        provider=args.provider,
        model=args.model,
        thinking=args.thinking,
        skill_paths=skill_paths,
    )
    pi = (
        PiRpcHarness(config=config)
        if force_rpc or getattr(args, "pi_session", "rpc") == "rpc"
        else PiHarness(config=config)
    )
    millrace = MillraceController(
        config=MillraceConfig(command=args.millrace_command, mode=args.millrace_mode),
        workspace=workspace,
        cwd=cwd,
    )
    monitor = DaemonMonitor(
        status_loader=millrace.status,
        poll_interval_seconds=args.poll_interval_seconds,
        notify_terminal_stages=args.notify_terminal_stages,
    )
    return pi, MillracerAgent(pi=pi, millrace=millrace, monitor=monitor)


def _close_if_needed(candidate: object) -> None:
    close = getattr(candidate, "close", None)
    if callable(close):
        close()


def _add_common_options(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--workspace",
        type=Path,
        default=Path("."),
        help="Millrace workspace root.",
    )
    command.add_argument(
        "--cwd",
        type=Path,
        default=None,
        help="Working directory for Pi and Millrace commands.",
    )
    command.add_argument("--route", choices=("auto", "direct", "millrace"), default="auto")
    command.add_argument("--intake", choices=("auto", "probe", "idea", "task"), default="auto")
    command.add_argument("--pi-command", default="pi")
    command.add_argument("--millrace-command", default="millrace")
    command.add_argument("--provider", default=None)
    command.add_argument("--model", default=None)
    command.add_argument("--thinking", default="high")
    command.add_argument("--millrace-mode", default="default_pi")
    command.add_argument("--skill", action="append", default=[])
    command.add_argument("--no-default-skills", action="store_true")
    command.add_argument("--poll-interval-seconds", type=float, default=2.0)
    command.add_argument("--daemon-timeout-seconds", type=float, default=7200.0)
    command.add_argument("--max-daemon-restarts", type=int, default=1)
    command.add_argument("--pi-timeout-seconds", type=int, default=None)
    command.add_argument("--keep-daemon", action="store_true")
    command.add_argument(
        "--notify-terminal-stages",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Notify the outer Pi session when terminal Millrace stages finish.",
    )


def _add_operator_parser(subparsers) -> None:
    operator = subparsers.add_parser("operator", help="Start a persistent Millracer operator.")
    _add_common_options(operator)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="millracer")
    subparsers = parser.add_subparsers(dest="command")
    run = subparsers.add_parser("run", help="Run one Millracer task.")
    run.add_argument("task", nargs="*", help="Task text. Reads stdin when omitted.")
    run.add_argument(
        "--benchmark-json",
        action="store_true",
        help="Read external request JSON from stdin.",
    )
    _add_common_options(run)
    run.add_argument("--pi-session", choices=("rpc", "print"), default="rpc")
    run.add_argument("--output", choices=("text", "json"), default="text")
    _add_operator_parser(subparsers)
    return parser


def _task_workspace_and_scope(
    args: argparse.Namespace,
) -> tuple[str, Path, ScopedWorkItem | None, str | None]:
    if args.benchmark_json:
        request = parse_benchmark_request(sys.stdin.read())
        workspace = request.workspace or args.workspace
        return request.task, workspace, request.scoped_work_item, request.intake_kind
    task = " ".join(args.task).strip()
    if not task:
        task = sys.stdin.read().strip()
    if not task:
        raise ValueError("task text is required")
    return task, args.workspace, None, None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
