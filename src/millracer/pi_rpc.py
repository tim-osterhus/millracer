"""Persistent Pi RPC harness for Millracer operator sessions."""

from __future__ import annotations

import codecs
import json
import os
import queue
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from millracer.pi import PiConfig
from millracer.prompts import MILLRACER_SYSTEM_PROMPT

_QUEUE_EOF = object()


class PiSessionLike(Protocol):
    def prompt(self, prompt: str, *, timeout_seconds: int | None = None) -> str: ...

    def close(self) -> None: ...


def build_rpc_command(config: PiConfig) -> tuple[str, ...]:
    args: list[str] = [
        config.command,
        "--mode",
        "rpc",
        "--no-session",
        "--no-context-files",
        "--append-system-prompt",
        MILLRACER_SYSTEM_PROMPT,
    ]
    if config.provider:
        args.extend(["--provider", config.provider])
    if config.model:
        args.extend(["--model", config.model])
    if config.thinking:
        args.extend(["--thinking", config.thinking])
    for skill_path in config.skill_paths:
        args.extend(["--skill", str(skill_path)])
    args.extend(config.extra_args)
    return tuple(args)


@dataclass(slots=True)
class PiRpcHarness:
    """Pi-backed harness that keeps one RPC subprocess alive across prompts."""

    config: PiConfig = field(default_factory=PiConfig)
    session_factory: Callable[..., PiSessionLike] | None = None
    env: Mapping[str, str] | None = None
    _session: PiSessionLike | None = field(default=None, init=False)
    _cwd: Path | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.session_factory is None:
            self.session_factory = PiRpcSession

    def complete(
        self,
        prompt: str,
        *,
        cwd: Path,
        timeout_seconds: int | None = None,
    ) -> str:
        session = self._session_for(cwd)
        return session.prompt(prompt, timeout_seconds=timeout_seconds)

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
            self._cwd = None

    def _session_for(self, cwd: Path) -> PiSessionLike:
        resolved_cwd = Path(cwd).expanduser().resolve()
        if self._session is not None:
            if self._cwd != resolved_cwd:
                raise ValueError(
                    f"persistent Pi session is bound to {self._cwd}; "
                    f"cannot reuse it for {resolved_cwd}"
                )
            return self._session

        env = dict(os.environ)
        if self.env is not None:
            env.update(self.env)
        self._cwd = resolved_cwd
        self._session = self.session_factory(
            command=build_rpc_command(self.config),
            cwd=resolved_cwd,
            env=env,
        )
        return self._session


class PiRpcSession:
    """Minimal JSONL RPC session around one long-lived Pi subprocess."""

    def __init__(
        self,
        *,
        command: tuple[str, ...],
        cwd: Path,
        env: Mapping[str, str],
        process_factory: Callable[..., subprocess.Popen[bytes]] | None = None,
    ) -> None:
        self.command = command
        self.cwd = Path(cwd)
        self.env = dict(env)
        self.process_factory = process_factory or _spawn_process
        self._next_id = 0
        self._closed = False
        self._stdout_queue: queue.Queue[str | object] = queue.Queue()
        self._stderr_chunks: list[str] = []
        self._process = self.process_factory(self.command, cwd=self.cwd, env=self.env)
        self._stdout_thread = threading.Thread(
            target=_read_jsonl_stdout_lines,
            args=(self._process.stdout, self._stdout_queue),
            daemon=True,
        )
        self._stderr_thread = threading.Thread(
            target=_read_stderr_text,
            args=(self._process.stderr, self._stderr_chunks),
            daemon=True,
        )
        self._stdout_thread.start()
        self._stderr_thread.start()

    def prompt(self, prompt: str, *, timeout_seconds: int | None = None) -> str:
        self._ensure_open()
        deadline = time.monotonic() + max(1, timeout_seconds or 3600)
        prompt_id = self._id("prompt")
        self._send({"id": prompt_id, "type": "prompt", "message": prompt})
        response = self._wait_for_response(prompt_id, deadline=deadline)
        if not response.get("success", False):
            raise RuntimeError(str(response.get("error") or "pi rpc prompt rejected"))

        while True:
            record = self._read_record(deadline=deadline)
            if record is None:
                self._abort()
                raise TimeoutError("pi rpc prompt timed out")
            payload = record
            if payload.get("type") == "agent_end":
                break

        return self._last_assistant_text()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _shutdown_process(self._process)

    def _id(self, prefix: str) -> str:
        self._next_id += 1
        return f"{prefix}-{self._next_id}"

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("pi rpc session is closed")
        if self._process.poll() is not None:
            raise RuntimeError(f"pi rpc process exited with code {self._process.returncode}")

    def _send(self, payload: dict[str, Any]) -> None:
        if self._process.stdin is None:
            raise RuntimeError("pi rpc stdin is unavailable")
        self._process.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        self._process.stdin.flush()

    def _wait_for_response(self, response_id: str, *, deadline: float) -> dict[str, Any]:
        while True:
            record = self._read_record(deadline=deadline)
            if record is None:
                self._abort()
                raise TimeoutError(f"timed out waiting for pi rpc response {response_id}")
            if record.get("type") == "response" and record.get("id") == response_id:
                return record

    def _last_assistant_text(self) -> str:
        response_id = self._id("last-assistant")
        self._send({"id": response_id, "type": "get_last_assistant_text"})
        response = self._wait_for_response(response_id, deadline=time.monotonic() + 5)
        if not response.get("success", False):
            raise RuntimeError("pi rpc get_last_assistant_text failed")
        data = response.get("data")
        if not isinstance(data, dict):
            return ""
        text = data.get("text")
        return text if isinstance(text, str) else ""

    def _read_record(self, *, deadline: float) -> dict[str, Any] | None:
        timeout = deadline - time.monotonic()
        if timeout <= 0:
            return None
        try:
            item = self._stdout_queue.get(timeout=timeout)
        except queue.Empty:
            return None
        if item is _QUEUE_EOF:
            stderr = "".join(self._stderr_chunks).strip()
            detail = f": {stderr}" if stderr else ""
            raise RuntimeError(f"pi rpc stream ended{detail}")
        if not isinstance(item, str):
            raise RuntimeError("pi rpc stream returned a non-string item")
        try:
            payload = json.loads(item)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"invalid pi rpc JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("pi rpc record must be a JSON object")
        return payload

    def _abort(self) -> None:
        try:
            self._send({"id": self._id("abort"), "type": "abort"})
        except Exception:
            pass
        finally:
            self.close()


def _spawn_process(
    command: tuple[str, ...],
    *,
    cwd: Path,
    env: Mapping[str, str],
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        command,
        cwd=str(cwd),
        env=dict(env),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
        bufsize=0,
    )


def _read_jsonl_stdout_lines(stream: Any, output_queue: queue.Queue[str | object]) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")()
    buffer = ""
    try:
        while True:
            chunk = stream.read(4096)
            if not chunk:
                break
            buffer += decoder.decode(chunk)
            while True:
                newline_index = buffer.find("\n")
                if newline_index == -1:
                    break
                line = buffer[:newline_index]
                buffer = buffer[newline_index + 1 :]
                output_queue.put(line.rstrip("\r"))
        buffer += decoder.decode(b"", final=True)
        if buffer:
            output_queue.put(buffer.rstrip("\r"))
    finally:
        output_queue.put(_QUEUE_EOF)


def _read_stderr_text(stream: Any, chunks: list[str]) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")()
    while True:
        chunk = stream.read(4096)
        if not chunk:
            break
        chunks.append(decoder.decode(chunk))
    chunks.append(decoder.decode(b"", final=True))


def _shutdown_process(process: subprocess.Popen[bytes]) -> None:
    try:
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
    except OSError:
        pass
    try:
        process.wait(timeout=1)
        return
    except subprocess.TimeoutExpired:
        pass
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=1)
            return
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                return
