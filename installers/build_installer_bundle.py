#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile, ZipInfo

from desktop_installer import (
    OPTIONAL_APP_ENTRIES,
    REQUIRED_APP_ENTRIES,
    REQUIRED_APP_FILES,
    copy_entry,
    resolve_latest_pipeline_model_dir,
    validate_required_app_entries,
)


INSTALLERS_DIR = Path(__file__).resolve().parent
APP_DIR = INSTALLERS_DIR.parent
DIST_DIR = APP_DIR / "dist"
BUNDLE_DIR = DIST_DIR / "Mictlan-AgriXGBoost-installer"


def write_installer_archive(
    bundle_dir: Path, archive_path: Path, archive_root: str, *,
    include=None, notes: dict[str, str] | None = None, entrypoints: tuple[str, ...] = (),
) -> Path:
    """Publish only a complete archive whose required files match current sources."""
    validate_required_app_entries(bundle_dir)
    temporary = archive_path.with_suffix(archive_path.suffix + ".tmp")
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with ZipFile(temporary, "w", compression=ZIP_STORED, allowZip64=True) as zipped:
            for source in sorted(bundle_dir.rglob("*")):
                if not source.is_file():
                    continue
                relative = source.relative_to(bundle_dir)
                if include is None or include(relative):
                    member = f"{archive_root}/{relative.as_posix()}"
                    if source.suffix in {".command", ".sh"}:
                        info = ZipInfo.from_file(source, arcname=member)
                        info.create_system = 3
                        info.external_attr = 0o100755 << 16
                        zipped.writestr(info, source.read_bytes())
                    else:
                        zipped.write(source, arcname=member)
            for name, contents in (notes or {}).items():
                zipped.writestr(f"{archive_root}/{name}", contents)
        with ZipFile(temporary) as zipped:
            names = set(zipped.namelist())
            required_files = {entry for entry in REQUIRED_APP_ENTRIES if (APP_DIR / entry).is_file()}
            required_files.update(REQUIRED_APP_FILES)
            required_files.update(entrypoints)
            for relative in sorted(required_files):
                member = f"{archive_root}/{relative}"
                if member not in names:
                    raise ValueError(f"Installer archive is missing required file: {relative}")
                source = APP_DIR / relative
                # Root launchers are copied from installers/ into the ZIP root.
                if relative in entrypoints:
                    source = INSTALLERS_DIR / relative
                if zipped.read(member) != source.read_bytes():
                    raise ValueError(f"Installer archive contains an outdated or altered file: {relative}")
            for entry in REQUIRED_APP_ENTRIES:
                if (APP_DIR / entry).is_dir() and not any(
                    name.startswith(f"{archive_root}/{entry}/") for name in names
                ):
                    raise ValueError(f"Installer archive is missing required directory: {entry}")
        temporary.replace(archive_path)
    finally:
        temporary.unlink(missing_ok=True)
    return archive_path


def main() -> None:
    validate_required_app_entries(APP_DIR)
    if BUNDLE_DIR.exists():
        shutil.rmtree(BUNDLE_DIR)
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

    copied_entries: list[str] = []
    for entry_name in REQUIRED_APP_ENTRIES + OPTIONAL_APP_ENTRIES:
        source = APP_DIR / entry_name
        if not source.exists():
            continue
        copy_entry(source, BUNDLE_DIR / entry_name)
        copied_entries.append(entry_name)

    validate_required_app_entries(BUNDLE_DIR)

    latest_model_dir = resolve_latest_pipeline_model_dir()
    latest_model_name = latest_model_dir.name if latest_model_dir is not None else "none"

    for installer_name in [
        "Mictlan-AgriXGBoost_Installer.sh",
        "Mictlan-AgriXGBoost_Installer.command",
        "Mictlan-AgriXGBoost_Installer.bat",
    ]:
        source = INSTALLERS_DIR / installer_name
        if source.exists():
            copy_entry(source, BUNDLE_DIR / installer_name)

    readme_path = BUNDLE_DIR / "README-INSTALLER.txt"
    readme_path.write_text(
        (
            "Mictlan-AgriXGBoost installer bundle\n"
            "\n"
            "This bundle already includes the latest app snapshot copied from the current project.\n"
            "Run the installer file that matches your platform:\n"
            "- Windows: Mictlan-AgriXGBoost_Installer.bat\n"
            "- Linux: Mictlan-AgriXGBoost_Installer.sh\n"
            "- macOS: Mictlan-AgriXGBoost_Installer.command\n"
            "\n"
            f"Included pipeline model: {latest_model_name}\n"
            f"Copied app entries: {len(copied_entries)}\n"
        ),
        encoding="utf-8",
    )
    print(f"Installer bundle created at: {BUNDLE_DIR}")
    print(f"Copied app entries: {len(copied_entries)}")


if __name__ == "__main__":
    main()
