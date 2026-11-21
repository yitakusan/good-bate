"""Native messaging host: start the local Stockgood service if it is down."""
from __future__ import annotations

import json
import struct
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HEALTH = "http://127.0.0.1:8002/api/health"
CREATE_NO_WINDOW = 0x08000000


def send(payload: dict) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(raw)))
    sys.stdout.buffer.write(raw)
    sys.stdout.buffer.flush()


def read_message() -> dict | None:
    header = sys.stdin.buffer.read(4)
    if len(header) < 4:
        return None
    size = struct.unpack("<I", header)[0]
    if size > 1_000_000:
        return None
    body = sys.stdin.buffer.read(size)
    if len(body) < size:
        return None
    data = json.loads(body.decode("utf-8"))
    return data if isinstance(data, dict) else None


def healthy() -> bool:
    try:
        with urllib.request.urlopen(HEALTH, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def launch() -> None:
    script = ROOT / "scripts" / "start-bg.ps1"
    subprocess.Popen(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
        ],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )


def main() -> None:
    if read_message() is None:
        return
    if healthy():
        send({"ok": True, "already": True})
        return
    python = ROOT / "backend" / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        send({"ok": False, "error": "missing venv"})
        return
    launch()
    for _ in range(25):
        time.sleep(1)
        if healthy():
            send({"ok": True, "already": False})
            return
    send({"ok": False, "error": "health timeout"})


if __name__ == "__main__":
    main()
