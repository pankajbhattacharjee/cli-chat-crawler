"""FastAPI orchestration layer: chat -> intent -> validate -> CLI -> parse -> summary."""
from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config
from .executor import Executor
from .llm import Interpreter, template_summary
from .security import redact
from .validator import ValidationError, validate_crawl_request

app = FastAPI(title="CLI-driven AI chat", docs_url=None, redoc_url=None)
executor = Executor()
interpreter = Interpreter()
crawl_slots = asyncio.Semaphore(config.MAX_CONCURRENT)
_hits: dict[str, deque] = defaultdict(deque)
_daily = {"day": time.strftime("%Y-%m-%d"), "n": 0}

REQUIRED_KEYS = {"task", "target", "status", "stats", "pages", "errors"}


class Msg(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class ChatRequest(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=20)


def ev(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False) + "\n"


def rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    q, now = _hits[ip], time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= config.RATE_LIMIT_PER_MIN:
        raise HTTPException(429, "Too many requests; please wait a minute.")
    today = time.strftime("%Y-%m-%d")
    if _daily["day"] != today:
        _daily.update(day=today, n=0)
    if _daily["n"] >= config.MAX_REQUESTS_PER_DAY:
        raise HTTPException(429, "Daily request limit reached; try again tomorrow.")
    _daily["n"] += 1
    q.append(now)


def load_result(path: str):
    """Parse + validate the CLI's JSON file. Returns (data|None, problem|None)."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None, "CLI produced no result file"
    if size > config.MAX_OUTPUT_BYTES:
        return None, f"result file too large ({size} bytes)"
    try:
        data = json.load(open(path, encoding="utf-8"))
    except (ValueError, OSError) as e:
        return None, f"result file is not valid JSON ({e})"
    missing = REQUIRED_KEYS - set(data) if isinstance(data, dict) else REQUIRED_KEYS
    if missing:
        return None, f"result JSON is missing fields: {sorted(missing)}"
    return data, None


def failure_message(data, res, problem) -> str:
    if res.cancelled:
        return "The crawl was cancelled. No result is available."
    if res.timed_out:
        return f"The crawl timed out after {config.CRAWL_TIME_BUDGET + config.HARD_KILL_GRACE}s and was killed."
    lines = []
    if data and data.get("errors"):
        lines = [f"{e.get('code')}: {e.get('message')}" for e in data["errors"][:3]]
    elif res.stderr.strip():
        lines = [res.stderr.strip().splitlines()[-1]]
    if problem:
        lines.append(problem)
    return "The crawl failed. " + (" | ".join(lines) if lines else f"Exit code {res.exit_code}.")


async def orchestrate(messages: list[Msg]):
    hist = [m.model_dump() for m in messages]
    user_request = next((m["content"] for m in reversed(hist) if m["role"] == "user"), "")
    yield ev(type="status", message="Understanding your request…")
    intent = await interpreter.interpret(hist)
    meta = {"intent_source": intent.get("source"), "llm_note": intent.get("note")}

    if intent["action"] == "reply":
        yield ev(type="result", status="info", message=redact(intent["text"]), **meta)
        return

    try:
        args = validate_crawl_request(intent.get("url"), intent.get("max_pages"), intent.get("depth"))
    except ValidationError as e:
        yield ev(type="result", status="rejected", message=f"Request not run: {e}", **meta)
        return

    run_id = uuid.uuid4().hex[:12]
    plan = {"tool": "crawl_site", "url": args.url, "max_pages": args.max_pages,
            "depth": args.depth, "adjustments": args.notes}
    yield ev(type="run", run_id=run_id, plan=plan)
    yield ev(type="status", message="Validated. Starting crawler CLI…")

    if crawl_slots.locked():
        yield ev(type="status", message="Waiting for a free crawler slot…")
    async with crawl_slots:
        res = None
        async for kind, payload in executor.run(run_id, args):
            if kind == "log":
                yield ev(type="log", line=payload)
            else:
                res = payload

    yield ev(type="status", message="Crawler finished. Validating output…")
    data, problem = load_result(res.output_path)
    execution = {"command": res.command_display, "exit_code": res.exit_code,
                 "duration_sec": res.duration_sec, "timed_out": res.timed_out,
                 "cancelled": res.cancelled, "stderr": res.stderr, "log": res.stdout_lines[-60:]}

    ok = bool(data) and not problem and res.exit_code == 0 and not res.timed_out \
        and not res.cancelled and data.get("status") in ("success", "partial") \
        and data.get("stats", {}).get("pages_crawled", 0) > 0
    if not ok:
        yield ev(type="result", status="cancelled" if res.cancelled else "failed",
                 message=redact(failure_message(data, res, problem)), execution=execution,
                 data=data, plan=plan, **meta)
        return

    yield ev(type="status", message="Writing summary…")
    summary, summary_source = await interpreter.summarize(data, user_request)
    if data["status"] == "partial":
        summary += "\n\nNote: this is a PARTIAL result; some pages failed or limits were hit (see JSON errors)."
    if args.notes:
        summary += "\n\nAdjusted to safe limits: " + "; ".join(args.notes) + "."
    yield ev(type="result", status=data["status"], message=redact(summary), execution=execution,
             data=data, plan=plan, summary_source=summary_source, **meta)


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    rate_limit(request)
    return StreamingResponse(orchestrate(req.messages), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/cancel/{run_id}")
async def cancel(run_id: str):
    return {"cancelled": executor.cancel(run_id)}


@app.get("/api/health")
async def health():
    return {"ok": True, "llm_mode": interpreter.mode, "model": interpreter.model,
            "cli_present": config.CLI_PATH.exists(),
            "limits": {"max_pages": config.MAX_PAGES_CAP, "max_depth": config.MAX_DEPTH_CAP,
                       "time_budget_sec": config.CRAWL_TIME_BUDGET}}


@app.get("/")
async def index():
    return FileResponse(config.STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=config.STATIC_DIR), name="static")
