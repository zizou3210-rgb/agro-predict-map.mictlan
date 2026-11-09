import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZipFile

PROJECT = Path(__file__).resolve().parents[1]
with patch.object(sys, "path", [str(PROJECT / "installers"), *sys.path]):
    import build_macos_app as mac
    import desktop_installer as installer


class MacInstallerTest(unittest.TestCase):
    def make_archive(self, root):
        payload = root / "payload"
        payload.mkdir()
        for relative in installer.REQUIRED_APP_ENTRIES:
            path = payload / relative
            if (PROJECT / relative).is_dir():
                path.mkdir()
            else:
                path.write_bytes(b"fixture")
        for relative in installer.REQUIRED_APP_FILES:
            path = payload / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
        for relative, content in (
            ("Mictlan-AgriXGBoost_Installer.command", b"#!/bin/bash\nexit 0\n"),
            ("runtime/macos/python-installer/python-3.12.pkg", b"pkg"),
            ("runtime/macos/runtime-libs/libomp.dylib", bytes.fromhex("cffaedfe") + b"fixture"),
        ):
            path = payload / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        archive = root / "native.zip"
        with ZipFile(archive, "w") as zipped:
            for path in payload.rglob("*"):
                if path.is_file():
                    zipped.write(path, f"native/{path.relative_to(payload).as_posix()}")
        return archive

    def test_payload_restores_executable_entrypoint_and_checks_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = self.make_archive(root)
            payload = mac.extract_payload(archive, root / "extracted")
            self.assertTrue((payload / "Mictlan-AgriXGBoost_Installer.command").stat().st_mode & 0o111)
            self.assertTrue(mac.is_macho(payload / "runtime/macos/runtime-libs/libomp.dylib"))

    def test_rejects_zip_path_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root / "bad.zip"
            with ZipFile(archive, "w") as zipped:
                zipped.writestr("../outside.txt", "bad")
            with self.assertRaisesRegex(ValueError, "invalid path"):
                mac.extract_payload(archive, root / "extracted")
            self.assertFalse((root / "outside.txt").exists())

    def test_signing_and_notarization_must_be_configured_together(self):
        with self.assertRaisesRegex(ValueError, "both"):
            mac.build(Path("input.zip"), Path("output.zip"), identity="Developer ID")

    def test_installed_launchers_use_the_bootstrapped_python(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = root / "Mictlan-AgriXGBoost.command"
            python = "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
            with patch.object(installer, "stage_application_snapshot", return_value=(root, ["server.py"])), patch.object(
                installer, "stage_bundled_runtime", return_value="Runtime copied",
            ), patch.object(installer, "ensure_macos_python312", return_value=python), patch.object(
                installer, "bootstrap_featurehero_runtime", return_value="Runtime prepared",
            ), patch.object(installer, "resolve_installed_app_dir", return_value=root / "app"), patch.object(
                installer, "resolve_installed_installers_dir", return_value=root / "app/installers",
            ), patch.object(installer, "mac_targets", return_value=[launcher]), patch.object(installer, "save_state"):
                installer.install_macos()
            self.assertIn(f'"{python}"', launcher.read_text())

    def test_failed_notarization_does_not_publish_unsigned_replacement(self):
        self.check_signed_build("Invalid")

    def test_signed_build_seals_nested_libomp_and_staples_before_publishing(self):
        self.check_signed_build("Accepted")

    def check_signed_build(self, status):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = self.make_archive(root)
            output = root / "output.zip"
            output.write_bytes(b"previous release")
            commands = []

            def command(*args):
                args = [str(value) for value in args]
                commands.append(args)
                if args[0] == "/usr/bin/osacompile":
                    app = Path(args[2])
                    (app / "Contents/Resources").mkdir(parents=True)
                    (app / "Contents/Info.plist").write_bytes(plistlib.dumps({}))
                elif args[0] == "/usr/bin/ditto":
                    Path(args[-1]).write_bytes(b"completed release")

            def submit(args, *, check, stdout):
                commands.append(args)
                json.dump({"status": status, "id": "submission-id"}, stdout)
                return SimpleNamespace(returncode=0 if status == "Accepted" else 1)

            with patch.object(mac, "sys", SimpleNamespace(platform="darwin")), patch.object(
                mac, "run", side_effect=command,
            ), patch.object(mac.subprocess, "run", side_effect=submit):
                if status == "Accepted":
                    mac.build(archive, output, identity="Developer ID", profile="profile", keychain="keychain")
                    self.assertEqual(output.read_bytes(), b"completed release")
                else:
                    with self.assertRaisesRegex(RuntimeError, "did not accept"):
                        mac.build(archive, output, identity="Developer ID", profile="profile", keychain="keychain")
                    self.assertEqual(output.read_bytes(), b"previous release")
            signed_lib = next(i for i, cmd in enumerate(commands)
                if cmd[0] == "/usr/bin/codesign" and cmd[-1].endswith("libomp.dylib"))
            signed_app = next(i for i, cmd in enumerate(commands)
                if cmd[0] == "/usr/bin/codesign" and "--sign" in cmd and cmd[-1].endswith(".app"))
            submitted = next(i for i, cmd in enumerate(commands) if cmd[:3] == ["xcrun", "notarytool", "submit"])
            self.assertLess(signed_lib, signed_app)
            self.assertLess(signed_app, submitted)
            if status == "Accepted":
                stapled = next(i for i, cmd in enumerate(commands) if cmd[:3] == ["xcrun", "stapler", "staple"])
                assessed = next(i for i, cmd in enumerate(commands) if cmd[0] == "/usr/sbin/spctl")
                self.assertLess(submitted, stapled)
                self.assertLess(stapled, assessed)
            else:
                self.assertFalse(any(cmd[:2] == ["xcrun", "stapler"] for cmd in commands))

    @unittest.skipUnless(sys.platform == "darwin", "Requires Apple's app compiler and ditto")
    def test_real_finder_app_compiles_and_preserves_executable_in_zip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = self.make_archive(root)
            output = root / "finder.zip"
            mac.build(archive, output)
            with ZipFile(output) as zipped:
                executable = f"native/{mac.APP_NAME}/Contents/MacOS/applet"
                self.assertIn(executable, zipped.namelist())
                self.assertTrue((zipped.getinfo(executable).external_attr >> 16) & 0o111)

    @unittest.skipUnless(shutil.which("bash"), "Requires bash")
    def test_command_shell_syntax(self):
        subprocess.run(["bash", "-n", str(PROJECT / "installers/Mictlan-AgriXGBoost_Installer.command")], check=True)
