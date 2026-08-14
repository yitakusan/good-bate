"""Local Cloudflare quick-tunnel status + start/stop for the UI."""

# ============================================================
# FEATURE: TUNNEL
#
# [接口] /api/tunnel*
# [脚本] scripts/run-tunnel.ps1
# [代码索引] docs/CODE_INDEX.md#feature-tunnel
# ============================================================

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from fastapi import HTTPException

from app.settings import BACKEND_ROOT

ROOT = BACKEND_ROOT.parent
LOGS = ROOT / "logs"
URL_FILE = LOGS / "tunnel-url.txt"
PID_FILE = LOGS / "tunnel.pid"
LOG_FILE = LOGS / "tunnel.log"
FRONTEND_URL = "http://127.0.0.1:5174"
# Match Stockgood's tunnel only — ignore other apps' cloudflared processes.
_OUR_TARGET_RE = re.compile(r"127\.0\.0\.1:5174|localhost:5174", re.I)

_URL_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")
_reader_lock = threading.Lock()
_log_lock = threading.Lock()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        out = (completed.stdout or "") + (completed.stderr or "")
        return str(pid) in out
    except Exception:
        return False


def _list_cloudflared() -> list[tuple[int, str]]:
    """Return (pid, command_line) for every cloudflared.exe."""
    if os.name != "nt":
        return []
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name = 'cloudflared.exe'\" "
                "| ForEach-Object { '{0}\t{1}' -f $_.ProcessId, $_.CommandLine }",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        return []
    rows: list[tuple[int, str]] = []
    for line in (completed.stdout or "").splitlines():
        text = line.strip()
        if not text or "\t" not in text:
            continue
        pid_s, cmd = text.split("\t", 1)
        try:
            pid = int(pid_s)
        except ValueError:
            continue
        rows.append((pid, cmd or ""))
    return rows


def _our_tunnel_pids() -> list[int]:
    """PIDs that belong to Stockgood's frontend tunnel (port 5174)."""
    found: list[int] = []
    seen: set[int] = set()
    for pid, cmd in _list_cloudflared():
        if _OUR_TARGET_RE.search(cmd):
            if pid not in seen:
                found.append(pid)
                seen.add(pid)
    # PID file from a previous start (may still be alive even if cmdline parse failed)
    try:
        if PID_FILE.is_file():
            raw = PID_FILE.read_text(encoding="utf-8").strip()
            if raw.isdigit():
                pid = int(raw)
                if pid not in seen and _pid_alive(pid):
                    # Only trust pid file if cmdline points at us, or no cmdline available
                    cmdline = next((c for p, c in _list_cloudflared() if p == pid), "")
                    if not cmdline or _OUR_TARGET_RE.search(cmdline):
                        found.append(pid)
                        seen.add(pid)
    except Exception:
        pass
    return found


def _cloudflared_running() -> bool:
    return bool(_our_tunnel_pids())


def _find_cloudflared() -> str | None:
    path = shutil.which("cloudflared") or shutil.which("cloudflared.exe")
    return path


def _read_url() -> str:
    try:
        if not URL_FILE.is_file():
            return ""
        text = URL_FILE.read_text(encoding="utf-8").strip()
        match = _URL_RE.search(text)
        return match.group(0) if match else ""
    except Exception:
        return ""


def get_tunnel_status() -> dict[str, object]:
    running = _cloudflared_running()
    url = _read_url()
    return {
        "running": running,
        "url": url,
        "stale": bool(url) and not running,
    }


def write_tunnel_url(url: str) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    match = _URL_RE.search(url or "")
    if not match:
        return
    URL_FILE.write_text(match.group(0) + "\n", encoding="utf-8")


def clear_tunnel_url() -> None:
    for path in (URL_FILE, PID_FILE):
        try:
            if path.is_file():
                path.unlink()
        except Exception:
            pass


def _read_stream_for_url(stream, log) -> None:
    try:
        for line in stream:
            text = line.rstrip("\n")
            with _log_lock:
                log.write(text + "\n")
                log.flush()
            match = _URL_RE.search(text)
            if match:
                write_tunnel_url(match.group(0))
    except Exception:
        pass
    finally:
        try:
            stream.close()
        except Exception:
            pass


def _pipe_reader(proc: subprocess.Popen[str]) -> None:
    """Read cloudflared stdout/stderr concurrently and persist public URL."""
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        log = open(LOG_FILE, "a", encoding="utf-8")
    except Exception:
        return

    threads: list[threading.Thread] = []
    try:
        for stream in (proc.stdout, proc.stderr):
            if stream is None:
                continue
            t = threading.Thread(
                target=_read_stream_for_url, args=(stream, log), daemon=True
            )
            t.start()
            threads.append(t)
        for t in threads:
            t.join()
    finally:
        try:
            log.close()
        except Exception:
            pass


def start_tunnel() -> dict[str, object]:
    if _cloudflared_running():
        status = get_tunnel_status()
        status["ok"] = True
        status["message"] = "隧道已在运行"
        return status

    binary = _find_cloudflared()
    if not binary:
        raise HTTPException(
            status_code=500,
            detail="未找到 cloudflared，请先安装并加入 PATH",
        )

    LOGS.mkdir(parents=True, exist_ok=True)
    clear_tunnel_url()

    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(
            subprocess, "CREATE_NO_WINDOW", 0
        )

    try:
        proc = subprocess.Popen(
            [binary, "tunnel", "--url", FRONTEND_URL],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"启动 cloudflared 失败: {exc}"
        ) from exc

    PID_FILE.write_text(str(proc.pid) + "\n", encoding="utf-8")
    with _reader_lock:
        threading.Thread(target=_pipe_reader, args=(proc,), daemon=True).start()

    # Brief wait for URL to appear in logs.
    for _ in range(40):
        time.sleep(0.25)
        if _read_url():
            break
        if proc.poll() is not None:
            raise HTTPException(
                status_code=500,
                detail="cloudflared 已退出，请检查 logs/tunnel.log",
            )

    status = get_tunnel_status()
    status["ok"] = True
    status["message"] = "隧道已启动" if status.get("url") else "隧道已启动，等待公网地址…"
    return status


def stop_tunnel() -> dict[str, object]:
    pids = _our_tunnel_pids()
    if not pids and not _read_url():
        status = get_tunnel_status()
        status["ok"] = True
        status["message"] = "隧道未在运行"
        return status

    try:
        if os.name == "nt":
            for pid in pids:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F", "/T"],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
        else:
            for pid in pids:
                subprocess.run(
                    ["kill", "-TERM", str(pid)],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    check=False,
                )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"关闭隧道失败: {exc}"
        ) from exc

    clear_tunnel_url()
    # Give OS a moment to drop the process from tasklist.
    time.sleep(0.4)
    status = get_tunnel_status()
    status["ok"] = True
    status["message"] = "隧道已关闭"
    return status
