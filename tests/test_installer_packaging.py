"""Check the Windows archive and installed snapshot without a Windows runtime."""
from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import tomllib
from unittest import mock
from zipfile import ZipFile


PROJECT_DIR = Path(__file__).resolve().parents[1]
with mock.patch.object(sys, "path", [str(PROJECT_DIR / "installers"), *sys.path]):
    import desktop_installer as installer
    import build_installer_bundle as bundle
    import build_native_runtime_packages as native
    import launch_mictlan_agrixgboost as launcher


class InstallerPackagingTest(unittest.TestCase):
    def make_source(self, root: Path) -> Path:
        """Use real root Python modules; avoid copying models or private .env data."""
        source = root / "source"
        source.mkdir()
        for entry in installer.REQUIRED_APP_ENTRIES:
            original = PROJECT_DIR / entry
            target = source / entry
            if original.is_dir():
                target.mkdir()
                (target / "fixture.txt").write_text("test directory", encoding="utf-8")
            else:
                shutil.copy2(original, target)
        for entry in installer.REQUIRED_APP_FILES:
            target = source / entry
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(PROJECT_DIR / entry, target)
        return source

    def test_active_python_imports_have_runtime_dependencies(self):
        local = {path.stem for path in PROJECT_DIR.glob("*.py")} | {
            "pipeline", "preprocess", "ce_pipeline", "featurehero",
        }
        paths = list(PROJECT_DIR.glob("*.py"))
        for directory in ("pipeline", "preprocess", "ce_pipeline", "resources/featurehero/featurehero"):
            paths.extend((PROJECT_DIR / directory).rglob("*.py"))
        for path in paths:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module.split(".")[0]]
                elif isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                for name in names:
                    if name in local or name in sys.stdlib_module_names:
                        continue
                    self.assertIn(name, installer.FEATUREHERO_RUNTIME_MODULES, f"{path} imports {name}")
        tree = ast.parse((PROJECT_DIR / "server.py").read_text(encoding="utf-8"))
        assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "PIPELINE_RUNTIME_MODULES" for target in node.targets))
        self.assertEqual(ast.literal_eval(assignment.value), installer.FEATUREHERO_RUNTIME_MODULES)
        declared = tomllib.loads((PROJECT_DIR / "resources/featurehero/pyproject.toml").read_text())["tool"]["poetry"]["dependencies"]
        aliases = {"PIL":"Pillow", "sklearn":"scikit-learn", "numbers_parser":"numbers-parser"}
        # These two are installed by scikit-learn / pykrige.
        for module in installer.FEATUREHERO_RUNTIME_MODULES:
            if module not in {"featurehero", "scipy", "joblib"}:
                self.assertIn(aliases.get(module, module), declared)

    def test_local_web_assets_are_included(self):
        def check_asset(path):
            relative = path.resolve().relative_to(PROJECT_DIR)
            self.assertTrue(path.is_file(), str(relative))
            self.assertIn(relative.parts[0], installer.REQUIRED_APP_ENTRIES)
            self.assertFalse(installer.should_skip_entry(relative), str(relative))
        html = (PROJECT_DIR / "index.html").read_text()
        for reference in re.findall(r'(?:src|href)="(\./[^"?]+)', html):
            check_asset(PROJECT_DIR / reference)
        manifest = json.loads((PROJECT_DIR / "manifest.webmanifest").read_text())
        for icon in manifest["icons"]:
            check_asset(PROJECT_DIR / icon["src"])
        for directory in ("src", "selecctionProperties"):
            for path in (PROJECT_DIR / directory).glob("*.js"):
                for reference in re.findall(r'from\s+["\'](\.[^"\']+)', path.read_text()):
                    check_asset(path.parent / reference)
        installer.validate_required_app_entries(PROJECT_DIR)

    def test_launcher_prefers_environment_with_app_dependencies(self):
        with tempfile.TemporaryDirectory(prefix="launcher_runtime_") as temporary:
            app = Path(temporary)
            python = app / "resources/featurehero/.venv/Scripts/python.exe"
            python.parent.mkdir(parents=True)
            python.write_bytes(b"interpreter marker")
            with (
                mock.patch.object(launcher, "APP_DIR", app),
                mock.patch.dict(os.environ, {}, clear=True),
                mock.patch.object(launcher, "resolve_bundled_python_command", return_value="base-python"),
            ):
                self.assertEqual(launcher.resolve_python_command(), str(python))
                python.unlink()
                self.assertEqual(launcher.resolve_python_command(), "base-python")
                os.environ["PYTHON3"] = "explicit-python"
                self.assertEqual(launcher.resolve_python_command(), "explicit-python")

    def test_launcher_removes_inherited_python_paths(self):
        with mock.patch.dict(os.environ, {"PYTHONHOME":"old-runtime", "PYTHONPATH":"old-packages"}):
            env = launcher.build_runtime_env()
        self.assertNotIn("PYTHONHOME", env)
        self.assertNotIn("PYTHONPATH", env)

    def test_import_check_reports_broken_installed_dependencies(self):
        failure = subprocess.CalledProcessError(1, ["python"], stderr="ModuleNotFoundError: pandas")
        with mock.patch.object(installer.subprocess, "run", side_effect=failure):
            with self.assertRaisesRegex(RuntimeError, "pandas"):
                installer.validate_installed_app_imports(Path("app"), "python")

    @unittest.skipUnless(os.environ.get("APP_INSTALLER_TEST_PYTHON"), "Set APP_INSTALLER_TEST_PYTHON to run actual snapshot imports")
    def test_actual_snapshot_imports_with_python312(self):
        with tempfile.TemporaryDirectory(prefix="installer_imports_") as temporary:
            target = Path(temporary) / "app"
            with (
                mock.patch.object(bundle, "BUNDLE_DIR", target),
                mock.patch.object(bundle, "OPTIONAL_APP_ENTRIES", []),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                bundle.main()
                installer.validate_installed_app_imports(target, os.environ["APP_INSTALLER_TEST_PYTHON"])

    def test_root_python_dependencies_are_packaged(self):
        required = set(installer.REQUIRED_APP_ENTRIES)
        self.assertIn("tabular_io.py", required)
        # Catch future local imports omitted from the installer manifest as well.
        local_modules = {path.stem: path.name for path in PROJECT_DIR.glob("*.py")}
        for entry in required:
            if not entry.endswith(".py"):
                continue
            tree = ast.parse((PROJECT_DIR / entry).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                imports = []
                if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imports = [node.module.split(".")[0]]
                elif isinstance(node, ast.Import):
                    imports = [alias.name.split(".")[0] for alias in node.names]
                for name in imports:
                    if name in local_modules:
                        self.assertIn(local_modules[name], required, f"{entry} imports {name}")

    def test_windows_archive_and_installed_snapshot_include_tabular_io(self):
        with tempfile.TemporaryDirectory(prefix="installer_packaging_") as temporary:
            root = Path(temporary)
            source = self.make_source(root)
            dist = root / "dist"
            bundled = dist / "bundle"
            runtime = root / "runtimes" / "windows" / "python-runtime"
            runtime.mkdir(parents=True)
            (runtime / "python.exe").write_bytes(b"runtime marker, not an executable")
            with (
                mock.patch.object(installer, "APP_DIR", source),
                mock.patch.object(bundle, "APP_DIR", source),
                mock.patch.object(bundle, "INSTALLERS_DIR", source / "installers"),
                mock.patch.object(bundle, "BUNDLE_DIR", bundled),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                bundle.main()
            with (
                mock.patch.object(native, "BUNDLE_DIR", bundled),
                mock.patch.object(native, "DIST_DIR", dist),
                mock.patch.object(native, "RUNTIMES_DIR", root / "runtimes"),
            ):
                archive = native.build_platform_archive("windows")
            with ZipFile(archive) as zipped:
                archive_root = "Mictlan-AgriXGBoost-installer-windows-native"
                for entry in installer.REQUIRED_APP_FILES:
                    self.assertIn(f"{archive_root}/{entry}", zipped.namelist())
                self.assertIn(f"{archive_root}/tabular_io.py", zipped.namelist())
                self.assertIn(f"{archive_root}/runtime/windows/python-runtime/python.exe", zipped.namelist())
                extracted = root / "extracted"
                zipped.extractall(extracted)
            install_root = root / "LocalAppData" / installer.APP_NAME
            installed = install_root / "app" / installer.PACKAGE_DIR_NAME
            with (
                mock.patch.object(installer, "APP_DIR", extracted / archive_root),
                mock.patch.object(installer, "resolve_install_root", return_value=install_root),
                mock.patch.object(installer, "resolve_installed_app_dir", return_value=installed),
                mock.patch.object(installer.platform, "system", return_value="Windows"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                _, copied = installer.stage_application_snapshot()
            self.assertIn("tabular_io.py", copied)
            self.assertEqual((installed / "tabular_io.py").read_bytes(), (PROJECT_DIR / "tabular_io.py").read_bytes())
            # Isolated resolution cannot accidentally find the source checkout.
            probe = subprocess.run([
                sys.executable, "-I", "-c",
                "import importlib.util, sys; from pathlib import Path; "
                "root=Path(sys.argv[1]); sys.path.insert(0, str(root)); "
                "spec=importlib.util.find_spec('tabular_io'); "
                "assert spec is not None; "
                "assert Path(spec.origin).resolve() == (root/'tabular_io.py').resolve()",
                str(installed),
            ], cwd=root, capture_output=True, text=True, check=False)
            self.assertEqual(probe.returncode, 0, probe.stderr)

    def test_incomplete_source_does_not_replace_existing_bundle(self):
        with tempfile.TemporaryDirectory(prefix="installer_missing_") as temporary:
            root = Path(temporary)
            source = self.make_source(root)
            (source / "tabular_io.py").unlink()
            bundled = root / "bundle"
            bundled.mkdir()
            sentinel = bundled / "previous.txt"
            sentinel.write_text("previous working bundle", encoding="utf-8")
            with (
                mock.patch.object(bundle, "APP_DIR", source),
                mock.patch.object(bundle, "BUNDLE_DIR", bundled),
            ):
                with self.assertRaisesRegex(FileNotFoundError, "tabular_io.py"):
                    bundle.main()
            self.assertTrue(sentinel.is_file())

    def test_incomplete_source_does_not_modify_installed_app(self):
        with tempfile.TemporaryDirectory(prefix="installer_missing_") as temporary:
            root = Path(temporary)
            source = self.make_source(root)
            (source / "tabular_io.py").unlink()
            installed = root / "installed"
            installed.mkdir()
            sentinel = installed / "previous.txt"
            sentinel.write_text("previous working installation", encoding="utf-8")
            with (
                mock.patch.object(installer, "APP_DIR", source),
                mock.patch.object(installer, "resolve_installed_app_dir", return_value=installed),
                mock.patch.object(installer, "resolve_install_root", return_value=root),
                mock.patch.object(installer, "stop_running_windows_processes") as stop,
            ):
                with self.assertRaisesRegex(FileNotFoundError, "tabular_io.py"):
                    installer.stage_application_snapshot()
                stop.assert_not_called()
            self.assertTrue(sentinel.is_file())


if __name__ == "__main__":
    unittest.main()
