#!/usr/bin/env python3
"""
Local web UI to start/stop the Startd8 MCP stdio server.

This is intentionally simple and dependency-free (standard library only).
It never writes to stdout of the MCP server process (it runs MCP in a child process).
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
import urllib.parse
import argparse
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional


ROOT_DIR = Path(__file__).resolve().parent
HTML_PATH = ROOT_DIR / "mcp_control.html"
DEFAULT_CMD = str(ROOT_DIR / "run_mcp.sh")
DEFAULT_HOST = os.getenv("STARTD8_MCP_CONTROL_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.getenv("STARTD8_MCP_CONTROL_PORT", "5178"))


def _env_flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    return v not in {"", "0", "false", "no", "off"}


# HTTP request logging is noisy because the UI polls frequently.
# Enable only when debugging the controller itself.
LOG_HTTP = _env_flag("STARTD8_MCP_CONTROL_LOG_HTTP", default=False)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_bytes(obj: Any) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _read_json_body(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    length = int(handler.headers.get("content-length") or "0")
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


@dataclass
class ProcState:
    cmd: list[str] = field(default_factory=list)
    cwd: str = str(ROOT_DIR)
    proc: Optional[subprocess.Popen[str]] = None
    started_at: Optional[float] = None
    last_exit_code: Optional[int] = None
    last_exit_time: Optional[str] = None
    last_error: Optional[str] = None

    # Log capture
    log_cursor: int = 0
    log_lines: deque[tuple[int, str, str]] = field(default_factory=lambda: deque(maxlen=10_000))
    log_file: str = str(ROOT_DIR / "logs" / "mcp-control.log")

    # Re-entrant so helper logging can be called from within guarded sections.
    lock: threading.RLock = field(default_factory=threading.RLock)

    def is_running(self) -> bool:
        p = self.proc
        return p is not None and p.poll() is None


STATE = ProcState()


def _append_log(stream: str, line: str) -> None:
    with STATE.lock:
        STATE.log_cursor += 1
        cur = STATE.log_cursor
        STATE.log_lines.append((cur, stream, line.rstrip("\n")))
        log_path = Path(STATE.log_file).expanduser()
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as fh:
                fh.write(f"{_utc_now_iso()} {stream} {line}")
        except Exception:
            # Best effort; ignore log write failures.
            pass


def _reader_thread(stream_name: str, pipe) -> None:
    try:
        for line in iter(pipe.readline, ""):
            if not line:
                break
            _append_log(stream_name, line)
    except Exception as e:
        _append_log("controller", f"{stream_name} reader exception: {e}\n")
    finally:
        try:
            pipe.close()
        except Exception:
            pass


def _start_process(env_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    with STATE.lock:
        if STATE.is_running():
            return {"ok": True, "running": True, "pid": STATE.proc.pid if STATE.proc else None}

        cmd = STATE.cmd or [DEFAULT_CMD]
        cwd = STATE.cwd

        env = os.environ.copy()
        if env_overrides:
            for k, v in env_overrides.items():
                if v is None:
                    continue
                env[str(k)] = str(v)

        # Reset log buffer on start
        STATE.log_cursor = 0
        STATE.log_lines.clear()
        STATE.last_error = None

        _append_log("api", f"start requested cmd={cmd} cwd={cwd} env_keys={sorted(env_overrides.keys()) if env_overrides else []}\n")
        try:
            p = subprocess.Popen(
                cmd,
                cwd=cwd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                start_new_session=True,
            )
        except Exception as e:
            STATE.last_error = str(e)
            _append_log("controller", f"spawn failed: {e}\n")
            return {"ok": False, "running": False, "error": str(e)}
        STATE.proc = p
        STATE.started_at = time.time()
        STATE.last_exit_code = None
        STATE.last_exit_time = None

        if p.stdout:
            threading.Thread(target=_reader_thread, args=("stdout", p.stdout), daemon=True).start()
        if p.stderr:
            threading.Thread(target=_reader_thread, args=("stderr", p.stderr), daemon=True).start()

        def _watch() -> None:
            try:
                code = p.wait()
            except Exception as e:
                _append_log("controller", f"watcher exception: {e}\n")
                return
            with STATE.lock:
                if STATE.proc is p:
                    STATE.last_exit_code = code
                    STATE.last_exit_time = _utc_now_iso()
                    STATE.proc = None
            _append_log("controller", f"exited pid={p.pid} exit_code={code}\n")

        threading.Thread(target=_watch, daemon=True).start()

        _append_log("controller", f"spawned pid={p.pid} cmd={cmd} cwd={cwd}\n")

        return {"ok": True, "running": True, "pid": p.pid}


def _stop_process(timeout_sec: float = 3.0) -> dict[str, Any]:
    with STATE.lock:
        p = STATE.proc
        if p is None or p.poll() is not None:
            STATE.proc = None
            return {"ok": True, "running": False}

        pid = p.pid

    # Try graceful: close stdin, then SIGTERM, then SIGKILL.
    _append_log("api", f"stop requested pid={pid}\n")
    try:
        if p.stdin:
            try:
                p.stdin.close()
            except Exception:
                pass
    except Exception:
        pass

    try:
        os.killpg(pid, signal.SIGTERM)
    except Exception:
        try:
            p.terminate()
        except Exception:
            pass

    try:
        p.wait(timeout=timeout_sec)
    except Exception:
        try:
            os.killpg(pid, signal.SIGKILL)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        try:
            p.wait(timeout=1.0)
        except Exception:
            pass

    with STATE.lock:
        code = p.poll()
        STATE.last_exit_code = code
        STATE.last_exit_time = _utc_now_iso()
        STATE.proc = None
    _append_log("controller", f"stopped pid={pid} exit_code={code}\n")
    return {"ok": True, "running": False, "last_exit_code": code}


def _status() -> dict[str, Any]:
    with STATE.lock:
        running = STATE.is_running()
        pid = STATE.proc.pid if STATE.proc else None
        started_at = None
        uptime = None
        if STATE.started_at and running:
            started_at = datetime.fromtimestamp(STATE.started_at, tz=timezone.utc).isoformat().replace("+00:00", "Z")
            uptime = int(time.time() - STATE.started_at)
        return {
            "running": running,
            "pid": pid,
            "started_at": started_at,
            "uptime_sec": uptime,
            "cwd": STATE.cwd,
            "command": " ".join(STATE.cmd or [DEFAULT_CMD]),
            "last_exit_code": STATE.last_exit_code,
            "last_exit_time": STATE.last_exit_time,
            "last_error": STATE.last_error,
            "log_file": STATE.log_file,
        }


def _logs(since: int = 0, include_stdout: bool = False) -> dict[str, Any]:
    with STATE.lock:
        cursor = STATE.log_cursor
        out: list[str] = []
        for cur, stream, line in list(STATE.log_lines):
            if cur <= since:
                continue
            if stream == "stdout" and not include_stdout:
                continue
            out.append(f"[{stream}] {line}")
        return {"cursor": cursor, "lines": out}


class Handler(BaseHTTPRequestHandler):
    server_version = "Startd8McpControl/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep the controller quiet; logs go to the captured log buffer.
        return

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        # Log only errors by default (polling endpoints are noisy).
        if status >= 400:
            try:
                _append_log("http", f"{getattr(self, 'command', '?')} {self.path} -> {status}\n")
            except Exception:
                pass
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("cache-control", "no-store")
        # Allow file:// pages to call this API (Origin: null).
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-methods", "GET,POST,OPTIONS")
        self.send_header("access-control-allow-headers", "content-type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        if LOG_HTTP:
            _append_log("http", f"OPTIONS {self.path}\n")
        self._send(HTTPStatus.NO_CONTENT, b"", "text/plain; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        if LOG_HTTP:
            _append_log("http", f"GET {self.path}\n")
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query or "")

        if path == "/" or path == "/index.html":
            try:
                html = HTML_PATH.read_text(encoding="utf-8")
            except Exception as e:
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, _json_bytes({"error": str(e)}), "application/json; charset=utf-8")
                return
            self._send(HTTPStatus.OK, html.encode("utf-8"), "text/html; charset=utf-8")
            return

        if path == "/api/status":
            self._send(HTTPStatus.OK, _json_bytes(_status()), "application/json; charset=utf-8")
            return

        if path == "/api/logs":
            since = 0
            try:
                since = int((qs.get("since") or ["0"])[0])
            except Exception:
                since = 0
            include_stdout = ((qs.get("stdout") or ["0"])[0] == "1")
            self._send(HTTPStatus.OK, _json_bytes(_logs(since=since, include_stdout=include_stdout)), "application/json; charset=utf-8")
            return

        self._send(HTTPStatus.NOT_FOUND, _json_bytes({"error": "not_found"}), "application/json; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802
        if LOG_HTTP:
            _append_log("http", f"POST {self.path}\n")
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/start":
            body = _read_json_body(self)
            env = body.get("env") if isinstance(body, dict) else None
            if env is not None and not isinstance(env, dict):
                env = None
            env_overrides = {str(k): str(v) for k, v in (env or {}).items()}
            try:
                result = _start_process(env_overrides=env_overrides)
                self._send(HTTPStatus.OK, _json_bytes(result), "application/json; charset=utf-8")
            except Exception as e:
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, _json_bytes({"error": str(e)}), "application/json; charset=utf-8")
            return

        if path == "/api/stop":
            try:
                result = _stop_process()
                self._send(HTTPStatus.OK, _json_bytes(result), "application/json; charset=utf-8")
            except Exception as e:
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, _json_bytes({"error": str(e)}), "application/json; charset=utf-8")
            return

        self._send(HTTPStatus.NOT_FOUND, _json_bytes({"error": "not_found"}), "application/json; charset=utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Startd8 MCP control web UI (local)")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Bind port (default: 5178)")
    parser.add_argument("--cmd", default=DEFAULT_CMD, help="Command to start MCP (default: ./run_mcp.sh)")
    parser.add_argument("--cwd", default=str(ROOT_DIR), help="Working directory for the MCP command")
    parser.add_argument("--log-file", default=STATE.log_file, help="Controller log file path")
    args = parser.parse_args()

    # Normalize state
    STATE.cmd = [args.cmd]
    STATE.cwd = args.cwd
    STATE.log_file = args.log_file
    Path(STATE.log_file).expanduser().parent.mkdir(parents=True, exist_ok=True)
    _append_log("controller", f"controller started host={args.host} port={args.port}\n")

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[mcp-control] listening on http://{args.host}:{args.port}", flush=True)
    print(f"[mcp-control] serving {HTML_PATH}", flush=True)
    print(f"[mcp-control] command: {args.cmd}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            _stop_process(timeout_sec=1.0)
        except BaseException:
            pass
        server.server_close()


if __name__ == "__main__":
    main()

