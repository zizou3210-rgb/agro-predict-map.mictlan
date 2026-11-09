"""Wrap the native payload in a Finder app; optionally sign and notarize it."""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zipfile import ZipFile

from desktop_installer import validate_required_app_entries

SCRIPTS = Path(__file__).resolve().parent
APP_NAME = "Instalar Mictlan-AgriXGBoost.app"
MACHO_MAGICS = {bytes.fromhex(value) for value in (
    "feedface", "cefaedfe", "feedfacf", "cffaedfe",
    "cafebabe", "bebafeca", "cafebabf", "bfbafeca",
)}


def run(*args):
    return subprocess.run([str(arg) for arg in args], check=True)


def extract_payload(archive: Path, destination: Path) -> Path:
    with ZipFile(archive) as zipped:
        for member in zipped.infolist():
            path = (destination / member.filename).resolve()
            if not path.is_relative_to(destination.resolve()):
                raise ValueError("Installer archive contains an invalid path")
        zipped.extractall(destination)
    roots = [path for path in destination.iterdir() if path.is_dir() and path.name != "__MACOSX"]
    if len(roots) != 1:
        raise ValueError("Expected one native installer directory")
    payload = roots[0]
    validate_required_app_entries(payload)
    for marker in ("Mictlan-AgriXGBoost_Installer.command",
                   "runtime/macos/python-installer/python-3.12.pkg",
                   "runtime/macos/runtime-libs/libomp.dylib"):
        if not (payload / marker).is_file():
            raise ValueError(f"Missing macOS installer payload: {marker}")
    for path in payload.rglob("*"):
        if path.is_file() and path.suffix in {".command", ".sh"}:
            path.chmod(path.stat().st_mode | 0o111)
    return payload


def is_macho(path: Path) -> bool:
    if not path.is_file() or path.is_symlink() or path.suffix == ".class":
        return False
    with path.open("rb") as handle:
        return handle.read(4) in MACHO_MAGICS


def sign_app(app: Path, identity: str, keychain: str) -> None:
    options = ["--force", "--timestamp", "--options", "runtime", "--sign", identity]
    if keychain:
        options.extend(["--keychain", keychain])
    # Sign nested code first, including libomp; then seal the whole app.
    for path in sorted(app.rglob("*")):
        if is_macho(path):
            run("/usr/bin/codesign", *options, path)
    run("/usr/bin/codesign", *options, app)
    run("/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", app)


def build(archive: Path, output: Path, *, identity="", profile="", keychain="") -> None:
    if bool(identity) != bool(profile):
        raise ValueError("Signing identity and notarization profile must both be provided")
    if sys.platform != "darwin":
        raise RuntimeError("The Finder installer must be built on macOS")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mictlan-macos-") as temporary:
        work = Path(temporary)
        payload = extract_payload(archive, work / "source")
        distribution = work / archive.stem
        distribution.mkdir()
        app = distribution / APP_NAME
        run("/usr/bin/osacompile", "-o", app, SCRIPTS / "macos_installer.applescript")
        resources = app / "Contents" / "Resources"
        shutil.copytree(payload, resources / "payload")
        plist = app / "Contents" / "Info.plist"
        with plist.open("rb") as handle:
            info = plistlib.load(handle)
        info.update(CFBundleIdentifier="org.mictlan.agrixgboost.installer",
                    CFBundleName="Instalar Mictlan-AgriXGBoost",
                    CFBundleShortVersionString="1.0.0", CFBundleVersion="1.0.0")
        with plist.open("wb") as handle:
            plistlib.dump(info, handle)
        if identity:
            sign_app(app, identity, keychain)
            submission = work / "notarization.zip"
            run("/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", app, submission)
            authentication = ["--keychain-profile", profile]
            if keychain:
                authentication.extend(["--keychain", keychain])
            result_file = work / "notarization.json"
            with result_file.open("w") as handle:
                submission_result = subprocess.run(["xcrun", "notarytool", "submit", str(submission),
                    *authentication, "--wait", "--timeout", "60m", "--output-format", "json"],
                    check=False, stdout=handle)
            try:
                result = json.loads(result_file.read_text())
            except ValueError as error:
                raise RuntimeError("Apple notarization returned no valid result; check the Actions log") from error
            if submission_result.returncode != 0 or result.get("status") != "Accepted":
                if result.get("id"):
                    run("xcrun", "notarytool", "log", result["id"], *authentication)
                raise RuntimeError("Apple did not accept the installer for notarization")
            run("xcrun", "stapler", "staple", app)
            run("xcrun", "stapler", "validate", app)
            run("/usr/sbin/spctl", "--assess", "--type", "execute", "--verbose=2", app)
        status = "Firmado y notarizado por Apple." if identity else "SIN FIRMA: compilación de desarrollo; macOS puede solicitar autorización manual."
        (distribution / "LEEME.txt").write_text(
            f"Abre {APP_NAME} con doble clic para instalar.\n{status}\n"
            "Necesita Internet. Puede solicitar tu contraseña para instalar Python 3.12.\n"
            "Registro: ~/Library/Logs/Mictlan-AgriXGBoost/installation.log\n", encoding="utf-8")
        # ditto preserves app metadata and executable permissions. Publish only
        # after successful signing, notarization and Gatekeeper assessment.
        completed = work / "completed.zip"
        run("/usr/bin/ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", distribution, completed)
        staged = output.with_suffix(".zip.tmp")
        try:
            shutil.copyfile(completed, staged)
            os.replace(staged, output)
        finally:
            staged.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--identity", default="")
    parser.add_argument("--profile", default="")
    parser.add_argument("--keychain", default="")
    args = parser.parse_args()
    build(args.archive, args.output, identity=args.identity, profile=args.profile, keychain=args.keychain)


if __name__ == "__main__":
    main()
