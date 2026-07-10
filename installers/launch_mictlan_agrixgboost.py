#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


INSTALLERS_DIR = Path(__file__).resolve().parent
APP_DIR = INSTALLERS_DIR.parent
ROOT_DIR = APP_DIR.parent
APP_URL_PATH = "/app/"
DEFAULT_PORT = int(os.environ.get("MICTLAN_APP_PORT", "8000"))
SERVER_SCRIPT = APP_DIR / "server.py"


def resolve_server_port(preferred_port: int = DEFAULT_PORT) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", preferred_port))
            return preferred_port
        except OSError:
            pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def resolve_bundled_python_command() -> str | None:
    candidates = [
        APP_DIR / "python-runtime" / "bin" / "python3",
        APP_DIR / "python-runtime" / "bin" / "python",
        APP_DIR / "python-runtime" / "python.exe",
        APP_DIR / "python-runtime" / "python3.exe",
        Path("/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"),
        Path("/usr/local/bin/python3.12"),
        Path("/opt/homebrew/bin/python3.12"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def browser_candidates() -> list[str]:
    if sys.platform == "darwin":
        return [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]

    if os.name == "nt":
        local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        program_files = Path(os.environ.get("PROGRAMFILES", "C:/Program Files"))
        program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)"))
        return [
            str(program_files / "Google" / "Chrome" / "Application" / "chrome.exe"),
            str(program_files_x86 / "Google" / "Chrome" / "Application" / "chrome.exe"),
            str(program_files / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
            str(program_files_x86 / "Microsoft" / "Edge" / "Application" / "msedge.exe"),
            str(local_app_data / "Chromium" / "Application" / "chrome.exe"),
        ]

    return [
        candidate
        for candidate in (
            shutil.which("google-chrome"),
            shutil.which("google-chrome-stable"),
            shutil.which("chromium"),
            shutil.which("chromium-browser"),
            shutil.which("microsoft-edge"),
            shutil.which("brave-browser"),
        )
        if candidate
    ]


def launch_browser_window(url: str) -> None:
    for candidate in browser_candidates():
        executable = Path(candidate)
        if executable.exists() or not executable.is_absolute():
            subprocess.Popen([candidate, f"--app={url}"])
            return

    webbrowser.open(url, new=1)


def wait_for_server(url: str, timeout_seconds: float = 12.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=1.2) as response:
                if response.status < 500:
                    return
        except URLError:
            time.sleep(0.2)
        except OSError:
            time.sleep(0.2)


def resolve_python_command() -> str:
    env_python = str(os.environ.get("PYTHON3", "")).strip()
    if env_python:
        return env_python
    bundled_python = resolve_bundled_python_command()
    if bundled_python:
        return bundled_python
    if os.name == "nt":
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return sys.executable


def ensure_server_script() -> None:
    if SERVER_SCRIPT.is_file():
        return
    raise FileNotFoundError(
        f"The installed app snapshot is incomplete. Missing server script: {SERVER_SCRIPT}"
    )


def main() -> None:
    ensure_server_script()
    port = resolve_server_port()
    app_url = f"http://127.0.0.1:{port}{APP_URL_PATH}"
    server_process = subprocess.Popen(
        [resolve_python_command(), str(SERVER_SCRIPT), "--port", str(port)],
        cwd=str(ROOT_DIR),
    )
    try:
        wait_for_server(app_url)
        launch_browser_window(app_url)
        server_process.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if server_process.poll() is None:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()


if __name__ == "__main__":
    os.chdir(ROOT_DIR)
    main()
