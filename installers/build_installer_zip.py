#!/usr/bin/env python3
from __future__ import annotations

from build_installer_bundle import BUNDLE_DIR, DIST_DIR, main as build_bundle, write_installer_archive


ZIP_BASE_NAME = DIST_DIR / "Mictlan-AgriXGBoost-installer"
ZIP_PATH = ZIP_BASE_NAME.with_suffix(".zip")


def main() -> None:
    build_bundle()
    write_installer_archive(
        BUNDLE_DIR, ZIP_PATH, BUNDLE_DIR.name,
        entrypoints=("Mictlan-AgriXGBoost_Installer.bat", "Mictlan-AgriXGBoost_Installer.sh",
            "Mictlan-AgriXGBoost_Installer.command"),
    )
    print(f"Installer zip created at: {ZIP_PATH}")


if __name__ == "__main__":
    main()
