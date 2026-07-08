#!/usr/bin/env python3
from __future__ import annotations

if __package__ in {None, ""}:
    import sys
    from pathlib import Path

    APP_BOOT_DIR = Path(__file__).resolve().parent
    PACKAGE_PARENT = APP_BOOT_DIR.parent
    if str(PACKAGE_PARENT) not in sys.path:
        sys.path.insert(0, str(PACKAGE_PARENT))

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
WATCH_EXTENSIONS = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".py",
    ".svg",
    ".txt",
    ".webmanifest",
    ".yml",
    ".yaml",
}
IGNORED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "dist",
    "node_modules",
}
IGNORED_RELATIVE_PARTS = {
    "cimmyt_app/pipeline/model",
    "cimmyt_app/resources/featurehero/.venv",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the cimmyt_app server and restart it when files under cimmyt_app/ change."
    )
    parser.add_argument("--port", type=int, default=3000, help="Port to bind.")
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Polling interval in seconds for file change detection.",
    )
    return parser


def should_watch(path: Path) -> bool:
    relative = path.relative_to(ROOT_DIR).as_posix()
    if any(part in IGNORED_DIR_NAMES for part in path.parts):
        return False
    if any(relative == ignored or relative.startswith(f"{ignored}/") for ignored in IGNORED_RELATIVE_PARTS):
        return False
    if path.is_dir():
        return True
    return path.suffix.lower() in WATCH_EXTENSIONS


def iter_watch_files() -> list[Path]:
    files: list[Path] = []
    for root, dir_names, file_names in os.walk(APP_DIR):
        root_path = Path(root)
        dir_names[:] = [
            dir_name
            for dir_name in dir_names
            if should_watch(root_path / dir_name)
        ]
        for file_name in file_names:
            file_path = root_path / file_name
            if should_watch(file_path):
                files.append(file_path)
    return sorted(files)


def snapshot_files() -> dict[str, int]:
    snapshot: dict[str, int] = {}
    for file_path in iter_watch_files():
        try:
            stat_result = file_path.stat()
        except FileNotFoundError:
            continue
        snapshot[str(file_path)] = stat_result.st_mtime_ns
    return snapshot


def start_server(port: int) -> subprocess.Popen[str]:
    command = [sys.executable, str(APP_DIR / "server.py"), "--port", str(port)]
    return subprocess.Popen(command, cwd=str(APP_DIR))


def stop_server(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    args = build_parser().parse_args()
    previous_snapshot = snapshot_files()
    server_process = start_server(args.port)
    print(f"[dev-autoreload] serving http://0.0.0.0:{args.port}/app/")
    print("[dev-autoreload] watching cimmyt_app/ for changes")

    try:
        while True:
            time.sleep(args.interval)
            current_snapshot = snapshot_files()
            if current_snapshot != previous_snapshot:
                print("[dev-autoreload] change detected, restarting server")
                stop_server(server_process)
                server_process = start_server(args.port)
                previous_snapshot = current_snapshot
                continue

            if server_process.poll() is not None:
                print("[dev-autoreload] server exited, starting again")
                server_process = start_server(args.port)
    except KeyboardInterrupt:
        pass
    finally:
        stop_server(server_process)


if __name__ == "__main__":
    main()
