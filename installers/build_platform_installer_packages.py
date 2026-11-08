#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from build_installer_bundle import BUNDLE_DIR, DIST_DIR, main as build_bundle, write_installer_archive


PLATFORMS = ("linux", "windows", "macos")
ENTRYPOINT_BY_PLATFORM = {
    "linux": "Mictlan-AgriXGBoost_Installer.sh",
    "windows": "Mictlan-AgriXGBoost_Installer.bat",
    "macos": "Mictlan-AgriXGBoost_Installer.command",
}
EXCLUDED_TOP_LEVEL_BY_PLATFORM = {
    "linux": {"Mictlan-AgriXGBoost_Installer.bat", "Mictlan-AgriXGBoost_Installer.command"},
    "windows": {"Mictlan-AgriXGBoost_Installer.sh", "Mictlan-AgriXGBoost_Installer.command"},
    "macos": {"Mictlan-AgriXGBoost_Installer.sh", "Mictlan-AgriXGBoost_Installer.bat"},
}
EXCLUDED_INSTALLERS_BY_PLATFORM = {
    "linux": {"Mictlan-AgriXGBoost_Installer.bat", "Mictlan-AgriXGBoost_Installer.command"},
    "windows": {"Mictlan-AgriXGBoost_Installer.sh", "Mictlan-AgriXGBoost_Installer.command"},
    "macos": {"Mictlan-AgriXGBoost_Installer.sh", "Mictlan-AgriXGBoost_Installer.bat"},
}


def _platform_note(platform_name: str) -> str:
    if platform_name == "linux":
        return (
            "Linux package\n"
            "\n"
            "Use: ./Mictlan-AgriXGBoost_Installer.sh\n"
            "This package includes a bundled Python 3.12 runtime for Linux.\n"
            "During installation, the installer rebuilds the FeatureHero .venv locally from resources/featurehero.\n"
        )
    if platform_name == "windows":
        return (
            "Windows package\n"
            "\n"
            "Use: Mictlan-AgriXGBoost_Installer.bat\n"
            "This package includes a bundled Python 3.12 runtime for Windows.\n"
            "During installation, the installer rebuilds the FeatureHero .venv locally from resources/featurehero.\n"
        )
    return (
        "macOS package\n"
        "\n"
        "Use: Mictlan-AgriXGBoost_Installer.command\n"
        "This package includes a bundled Python 3.12 installer for macOS.\n"
        "The installer includes a bundled Python 3.12 package and rebuilds the FeatureHero .venv locally during installation.\n"
    )


def should_include(relative_path: Path, platform_name: str) -> bool:
    normalized = Path(*[part for part in relative_path.parts if part not in {"", "."}])
    if not normalized.parts:
        return False

    if platform_name in {"windows", "macos"}:
        if normalized == Path("resources") / "featurehero" / ".venv":
            return False
        if Path("resources") / "featurehero" / ".venv" in normalized.parents:
            return False

    if len(normalized.parts) == 1 and normalized.name in EXCLUDED_TOP_LEVEL_BY_PLATFORM[platform_name]:
        return False

    if normalized.parts[0] == "installers" and normalized.name in EXCLUDED_INSTALLERS_BY_PLATFORM[platform_name]:
        return False

    return True


def build_platform_zip(platform_name: str) -> Path:
    archive_root = f"Mictlan-AgriXGBoost-installer-{platform_name}"
    archive_path = DIST_DIR / f"{archive_root}.zip"
    write_installer_archive(
        BUNDLE_DIR, archive_path, archive_root,
        include=lambda relative: should_include(relative, platform_name),
        entrypoints=(ENTRYPOINT_BY_PLATFORM[platform_name],),
        notes={"PLATFORM-NOTES.txt": _platform_note(platform_name)},
    )

    return archive_path


def main() -> None:
    build_bundle()
    for platform_name in PLATFORMS:
        archive_path = build_platform_zip(platform_name)
        print(f"{platform_name}: {archive_path}")
        print(f"entrypoint: {ENTRYPOINT_BY_PLATFORM[platform_name]}")


if __name__ == "__main__":
    main()
