#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

from desktop_installer import OPTIONAL_APP_ENTRIES, REQUIRED_APP_ENTRIES, copy_entry


INSTALLERS_DIR = Path(__file__).resolve().parent
APP_DIR = INSTALLERS_DIR.parent
DIST_DIR = APP_DIR / "dist"
BUNDLE_DIR = DIST_DIR / "Mictlan-AgriXGBoost-installer"


def main() -> None:
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
            f"Copied app entries: {len(copied_entries)}\n"
        ),
        encoding="utf-8",
    )
    print(f"Installer bundle created at: {BUNDLE_DIR}")
    print(f"Copied app entries: {len(copied_entries)}")


if __name__ == "__main__":
    main()
