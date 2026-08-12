# -*- coding: utf-8 -*-
"""Stockgood Windows system-tray host: start services, tray menu, stop on exit."""
from __future__ import annotations

import atexit
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "缺少 pystray / Pillow。请在 backend\\.venv 中执行:\n"
        "  pip install pystray Pillow"
    ) from exc

BACKEND_PORT = 8002
FRONTEND_PORT = 5174
UI_URL = f"http://localhost:{FRONTEND_PORT}"
DOCS_URL = f"http://localhost:{BACKEND_PORT}/docs"

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
LOGS = ROOT / "logs"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
PYTHONW = BACKEND / ".venv" / "Scripts" / "pythonw.exe"
LOCK_FILE = LOGS / "tray.lock"

_icon: pystray.Icon | None = None
_stopping = False


def _log(msg: str) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    try:
        with (LOGS / "tray.log").open("a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass


def _port_listening(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        try:
            return sock.connect_ex((host, port)) == 0
        except OSError:
            return False


def _wait_port(port: int, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _port_listening(port):
            return True
        time.sleep(0.5)
    return False


def _db_mode() -> str:
    return (os.environ.get("STOCKGOOD_DB_MODE") or "production").strip() or "production"


def _run_backup(reason: str) -> None:
    script = ROOT / "scripts" / "backup-db.ps1"
    if not script.is_file():
        return
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-Reason",
                reason,
            ],
            cwd=str(ROOT),
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    except OSError as exc:
        _log(f"backup {reason} failed: {exc}")


def _kill_port(port: int) -> None:
    """Kill processes listening on port (Windows), matching stop.bat behavior."""
    if sys.platform != "win32":
        return
    try:
        out = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.CalledProcessError):
        return
    pids: set[int] = set()
    needle = f":{port}"
    for line in out.splitlines():
        if "LISTENING" not in line.upper():
            continue
        if needle not in line:
            continue
        parts = line.split()
        if not parts:
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        if pid > 0:
            pids.add(pid)
    for pid in pids:
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid), "/T"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )


def _start_backend() -> None:
    if _port_listening(BACKEND_PORT):
        _log(f"backend already on {BACKEND_PORT}")
        return
    if not PYTHON.is_file():
        raise FileNotFoundError(f"missing venv python: {PYTHON}")
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / "backend.log"
    env = os.environ.copy()
    env["STOCKGOOD_DB_MODE"] = _db_mode()
    # No --reload for tray/autostart (lower overhead).
    cmd = [
        str(PYTHON),
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(BACKEND_PORT),
    ]
    with log_path.open("a", encoding="utf-8") as logf:
        subprocess.Popen(
            cmd,
            cwd=str(BACKEND),
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    _log("backend started")


def _start_frontend() -> None:
    if _port_listening(FRONTEND_PORT):
        _log(f"frontend already on {FRONTEND_PORT}")
        return
    if not (FRONTEND / "node_modules").is_dir():
        raise FileNotFoundError(f"missing frontend\\node_modules under {FRONTEND}")
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / "frontend.log"
    # Use cmd so npm.cmd resolves on Windows.
    cmd = f'cd /d "{FRONTEND}" && npm run dev -- --host --port {FRONTEND_PORT}'
    with log_path.open("a", encoding="utf-8") as logf:
        subprocess.Popen(
            cmd,
            shell=True,
            stdout=logf,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
    _log("frontend started")


def _ensure_services() -> None:
    _run_backup("start")
    _start_backend()
    time.sleep(1.5)
    _start_frontend()
    if not _wait_port(BACKEND_PORT, 45):
        _log("WARN: backend port not ready")
    if not _wait_port(FRONTEND_PORT, 90):
        _log("WARN: frontend port not ready")


def _stop_services() -> None:
    global _stopping
    if _stopping:
        return
    _stopping = True
    _log("stopping services")
    _kill_port(BACKEND_PORT)
    _kill_port(FRONTEND_PORT)
    time.sleep(1)
    _run_backup("stop")
    _release_lock()


def _browser_exe() -> Path | None:
    local = os.environ.get("LOCALAPPDATA", "")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    candidates = [
        Path(pf86) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(pf) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(pf) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(local) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for path in candidates:
        if path.is_file():
            return path
    return None


def _find_window_hwnd(needles: tuple[str, ...]) -> int | None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        title = buf.value or ""
        lowered = title.lower()
        for needle in needles:
            if needle.lower() in lowered:
                found.append(int(hwnd))
                return False
        return True

    user32.EnumWindows(_enum, 0)
    return found[0] if found else None


def _activate_hwnd(hwnd: int) -> bool:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    sw_restore = 9
    user32.ShowWindow(hwnd, sw_restore)
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    cur = kernel32.GetCurrentThreadId()
    dummy = wintypes.DWORD()
    fg_tid = user32.GetWindowThreadProcessId(fg, ctypes.byref(dummy))
    tgt_tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(dummy))
    user32.AttachThreadInput(cur, fg_tid, True)
    user32.AttachThreadInput(cur, tgt_tid, True)
    try:
        user32.BringWindowToTop(hwnd)
        return bool(user32.SetForegroundWindow(hwnd))
    finally:
        user32.AttachThreadInput(cur, fg_tid, False)
        user32.AttachThreadInput(cur, tgt_tid, False)


def _open_or_focus(url: str, title_needles: tuple[str, ...]) -> None:
    hwnd = _find_window_hwnd(title_needles)
    if hwnd and _activate_hwnd(hwnd):
        _log(f"focused existing window hwnd={hwnd} url={url}")
        return
    exe = _browser_exe()
    if exe is not None:
        try:
            subprocess.Popen(
                [str(exe), f"--app={url}"],
                close_fds=True,
            )
            _log(f"opened app window {exe.name} {url}")
            return
        except OSError as exc:
            _log(f"app window failed: {exc}")
    webbrowser.open(url, new=0)
    _log(f"opened browser fallback {url}")


def _make_icon_image() -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (4, 4, size - 5, size - 5),
        radius=14,
        fill=(42, 111, 106, 255),
    )
    draw.rectangle((18, 22, 46, 28), fill=(245, 248, 247, 255))
    draw.rectangle((18, 34, 46, 40), fill=(245, 248, 247, 255))
    draw.rectangle((18, 46, 34, 52), fill=(245, 248, 247, 255))
    return img


def _open_ui(icon: pystray.Icon | None = None, item: pystray.MenuItem | None = None) -> None:
    _open_or_focus(UI_URL, ("Stockgood 库存", "localhost:5174"))


def _open_docs(icon: pystray.Icon | None = None, item: pystray.MenuItem | None = None) -> None:
    _open_or_focus(DOCS_URL, ("Stockgood API",))


def _quit(icon: pystray.Icon, item: pystray.MenuItem | None = None) -> None:
    try:
        _stop_services()
    finally:
        icon.stop()


def _acquire_lock() -> bool:
    LOGS.mkdir(parents=True, exist_ok=True)
    if LOCK_FILE.is_file():
        try:
            old_pid = int(LOCK_FILE.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            old_pid = 0
        if old_pid > 0 and _pid_alive(old_pid):
            _log(f"another tray instance running pid={old_pid}")
            return False
    LOCK_FILE.write_text(str(os.getpid()), encoding="utf-8")
    return True


def _release_lock() -> None:
    try:
        if LOCK_FILE.is_file():
            text = LOCK_FILE.read_text(encoding="utf-8").strip()
            if text == str(os.getpid()):
                LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            text=True,
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return str(pid) in out
    except (OSError, subprocess.CalledProcessError):
        return False


def _msgbox(text: str, title: str = "Stockgood") -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)
    except OSError:
        pass


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("tray host is Windows-only")
    if not _acquire_lock():
        # Still offer to open UI if services are up.
        if _port_listening(FRONTEND_PORT):
            _open_ui()
        raise SystemExit(0)

    atexit.register(_stop_services)
    mode = _db_mode()
    _log(f"tray start mode={mode}")

    try:
        _ensure_services()
    except Exception as exc:
        _log(f"start failed: {exc}")
        _release_lock()
        _msgbox(f"Stockgood 启动失败:\n{exc}\n\n详见 logs\\tray.log")
        raise SystemExit(1) from exc

    menu = pystray.Menu(
        pystray.MenuItem("打开界面", _open_ui, default=True),
        pystray.MenuItem("打开 API 文档", _open_docs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("停止并退出", _quit),
    )
    global _icon
    _icon = pystray.Icon(
        "stockgood",
        _make_icon_image(),
        f"Stockgood ({mode})",
        menu,
    )
    _icon.run()


if __name__ == "__main__":
    main()
