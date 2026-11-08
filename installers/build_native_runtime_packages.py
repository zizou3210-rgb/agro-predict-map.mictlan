#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from build_installer_bundle import BUNDLE_DIR, DIST_DIR, main as build_bundle, write_installer_archive


INSTALLERS_DIR = Path(__file__).resolve().parent
RUNTIMES_DIR = INSTALLERS_DIR / "runtimes"
PLATFORMS = ("linux", "windows", "macos")
EXPECTED_RUNTIME_MARKERS = {
    "linux": [
        Path("python-runtime") / "bin" / "python3",
        Path("python-runtime") / "bin" / "python",
    ],
    "windows": [
        Path("python-runtime") / "python.exe",
        Path("python-runtime") / "python3.exe",
    ],
    "macos": [
        Path("python-installer") / "python-3.12.pkg",
        Path("runtime-libs") / "libomp.dylib",
    ],
}


def runtime_dir(platform_name: str) -> Path:
    return RUNTIMES_DIR / platform_name


def has_runtime(platform_name: str) -> bool:
    base = runtime_dir(platform_name)
    if not base.exists():
        return False
    markers = EXPECTED_RUNTIME_MARKERS[platform_name]
    if platform_name == "macos":
        return all((base / marker).exists() for marker in markers)
    return any((base / marker).exists() for marker in markers)


def ensure_runtime(platform_name: str) -> Path:
    base = runtime_dir(platform_name)
    if not has_runtime(platform_name):
        expected = "\n".join(f"- {marker.as_posix()}" for marker in EXPECTED_RUNTIME_MARKERS[platform_name])
        raise FileNotFoundError(
            f"Missing native runtime for {platform_name}.\n"
            f"Create it under: {base}\n"
            f"Expected at least one of these paths:\n{expected}"
        )
    return base


def clean_previous_platform_runtime(bundle_root: Path) -> None:
    target_runtime_root = bundle_root / "runtime"
    if target_runtime_root.exists():
        shutil.rmtree(target_runtime_root)


def stage_platform_runtime(bundle_root: Path, platform_name: str) -> None:
    source_runtime = ensure_runtime(platform_name)
    target_runtime = bundle_root / "runtime" / platform_name
    shutil.copytree(source_runtime, target_runtime)


def build_platform_archive(platform_name: str) -> Path:
    archive_root = f"Mictlan-AgriXGBoost-installer-{platform_name}-native"
    archive_path = DIST_DIR / f"{archive_root}.zip"
    ensure_runtime(platform_name)
    clean_previous_platform_runtime(BUNDLE_DIR)
    stage_platform_runtime(BUNDLE_DIR, platform_name)
    entrypoint = {
        "windows": "Mictlan-AgriXGBoost_Installer.bat",
        "linux": "Mictlan-AgriXGBoost_Installer.sh",
        "macos": "Mictlan-AgriXGBoost_Installer.command",
    }[platform_name]
    write_installer_archive(
        BUNDLE_DIR, archive_path, archive_root, entrypoints=(entrypoint,),
        notes={"RUNTIME-NOTES.txt": f"Native runtime package for {platform_name}\n"},
    )
    return archive_path


def main() -> None:
    build_bundle()
    built: list[Path] = []
    errors: list[str] = []

    for platform_name in PLATFORMS:
        try:
            archive = build_platform_archive(platform_name)
            built.append(archive)
            print(f"{platform_name}: {archive}")
        except FileNotFoundError as error:
            errors.append(str(error))

    clean_previous_platform_runtime(BUNDLE_DIR)

    if errors:
        print("\nMissing runtimes:")
        for item in errors:
            print()
            print(item)
        sys.exit(1)


if __name__ == "__main__":
    main()
