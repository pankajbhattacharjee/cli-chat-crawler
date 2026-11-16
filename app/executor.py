"""Runs the approved CLI as a subprocess and captures everything.

* Argument LIST + create_subprocess_exec -> no shell, no injection.
* Fixed command template: only validated values are substituted.
* Minimal environment: API keys and other secrets are NOT inherited.
* Live stdout streaming, stderr capture, hard timeout, cancellation.
"""
from __future__ import annotations

import asyncio
import os
import shlex
import sys
import time
from dataclasses import dataclass, field
from typing import AsyncIterator

from . import config
from .security import redact
from .validator import CrawlArgs


@dataclass
class ExecResult:
    command_display: str
    exit_code: int | None
    duration_sec: float
    stdout_lines: list[str] = field(default_factory=list)
    stderr: str = ""
    timed_out: bool = False
    cancelled: bool = False
    output_path: str = ""


def _minimal_env() -> dict[str, str]:
    env = {"PATH": os.environ.get("PATH", ""), "PYTHONUNBUFFERED": "1",
           "PYTHONIOENCODING": "utf-8"}
    for k in ("SYSTEMROOT", "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "HOME"):
        if k in os.environ:
            env[k] = os.environ[k]
    return env


class Executor:
    def __init__(self) -> None:
        self._procs: dict[str, asyncio.subprocess.Process] = {}
        self._cancelled: set[str] = set()

    def cancel(self, run_id: str) -> bool:
        proc = self._procs.get(run_id)
        if proc and proc.returncode is None:
            self._cancelled.add(run_id)
            proc.kill()
            return True
        return False

    def build_command(self, run_id: str, args: CrawlArgs):
        out = config.RUNS_DIR / f"{run_id}.json"
        cmd = [sys.executable, str(config.CLI_PATH),
               "--url", args.url,
               "--max-pages", str(args.max_pages),
               "--depth", str(args.depth),
               "--timeout", str(config.CRAWL_TIME_BUDGET),
               "--out", str(out)]
        if config.DEV_ALLOW_PRIVATE:
            cmd.append("--allow-private")
        display = ["python", "cli/sitecrawl.py"] + cmd[2:]
        display = shlex.join(display).replace(str(out), f"runs/{run_id}.json")
        return cmd, out, display

    async def run(self, run_id: str, args: CrawlArgs) -> AsyncIterator[tuple[str, object]]:
        cmd, out, display = self.build_command(run_id, args)
        t0 = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env=_minimal_env(), cwd=str(config.RUNS_DIR),
            stdin=asyncio.subprocess.DEVNULL)
        self._procs[run_id] = proc
        q: asyncio.Queue = asyncio.Queue()
        out_lines: list[str] = []
        err_lines: list[str] = []
        timed_out = False

        async def pump(stream, kind):
            try:
                async for raw in stream:
                    await q.put((kind, raw.decode("utf-8", "replace").rstrip()))
            except Exception:
                pass
            await q.put((kind, None))

        tasks = [asyncio.create_task(pump(proc.stdout, "out")),
                 asyncio.create_task(pump(proc.stderr, "err"))]
        open_streams = 2
        deadline = time.monotonic() + config.CRAWL_TIME_BUDGET + config.HARD_KILL_GRACE
        try:
            while open_streams:
                remaining = deadline - time.monotonic()
                try:
                    if remaining <= 0:
                        raise asyncio.TimeoutError
                    kind, line = await asyncio.wait_for(q.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    timed_out = True
                    proc.kill()
                    break
                if line is None:
                    open_streams -= 1
                    continue
                line = redact(line)
                if kind == "out":
                    if len(out_lines) < config.MAX_LOG_LINES:
                        out_lines.append(line)
                        yield ("log", line)
                elif len(err_lines) < config.MAX_LOG_LINES:
                    err_lines.append(line)
            await proc.wait()
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()
            for t in tasks:
                t.cancel()
            self._procs.pop(run_id, None)
        cancelled = run_id in self._cancelled
        self._cancelled.discard(run_id)
        yield ("done", ExecResult(
            command_display=display, exit_code=proc.returncode,
            duration_sec=round(time.monotonic() - t0, 2), stdout_lines=out_lines,
            stderr=redact("\n".join(err_lines))[-4000:], timed_out=timed_out,
            cancelled=cancelled, output_path=str(out)))
