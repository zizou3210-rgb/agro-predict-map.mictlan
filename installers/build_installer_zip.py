#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from build_installer_bundle import BUNDLE_DIR, DIST_DIR, main as build_bundle


ZIP_BASE_NAME = DIST_DIR / "Mictlan-AgriXGBoost-installer"
ZIP_PATH = ZIP_BASE_NAME.with_suffix(".zip")
TMP_ZIP_PATH = DIST_DIR / f"{ZIP_PATH.name}.tmp"


def main() -> None:
    build_bundle()
    if TMP_ZIP_PATH.exists():
        TMP_ZIP_PATH.unlink()

    zip_binary = shutil.which("zip")
    if zip_binary:
        subprocess.run(
            [zip_binary, "-r", "-0", str(TMP_ZIP_PATH), BUNDLE_DIR.name],
            cwd=str(DIST_DIR),
            check=True,
        )
    else:
        temp_base = TMP_ZIP_PATH.with_suffix("")
        archive_path = shutil.make_archive(
            str(temp_base),
            "zip",
            root_dir=str(DIST_DIR),
            base_dir=BUNDLE_DIR.name,
        )
        os.replace(archive_path, TMP_ZIP_PATH)

    os.replace(TMP_ZIP_PATH, ZIP_PATH)
    print(f"Installer zip created at: {ZIP_PATH}")


if __name__ == "__main__":
    main()
