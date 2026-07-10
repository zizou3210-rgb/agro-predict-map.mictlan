#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import messagebox
except ModuleNotFoundError:  # pragma: no cover - depends on local desktop runtime
    tk = None
    messagebox = None


APP_NAME = "Mictlan-AgriXGBoost"
PACKAGE_DIR_NAME = "cimmyt_app"
INSTALLERS_DIR = Path(__file__).resolve().parent
APP_DIR = INSTALLERS_DIR.parent
ROOT_DIR = APP_DIR.parent
LAUNCHER_SCRIPT_NAME = "launch_mictlan_agrixgboost.py"
ICON_RELATIVE_PATH = Path("icons") / "icon-app.svg"
INSTALLER_STATE_NAME = "install_state.json"
REQUIRED_APP_ENTRIES = [
    "__init__.py",
    "config_env.py",
    "index.html",
    "manifest.webmanifest",
    "server.py",
    "service-worker.js",
    "styles.css",
    "workbook_preview.py",
    "ce_pipeline",
    "data",
    "icons",
    "installers",
    "pipeline",
    "preprocess",
    "resources",
    "selecctionProperties",
    "src",
    "template",
]
OPTIONAL_APP_ENTRIES = [
    ".env",
    "documents",
    "package.json",
    "README.md",
    "scripts",
    "source",
]
SKIP_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    ".git",
    ".hg",
    ".svn",
}
SKIP_FILE_SUFFIXES = {
    ".log",
    ".tmp",
    ".temp",
    ".pyc",
    ".pyo",
}
SKIP_FILE_NAMES = {
    ".DS_Store",
}
SKIP_RELATIVE_PATHS = {
    Path("pipeline") / "runs",
    Path("ce_pipeline") / "model",
    Path("preprocess") / "phase01_quality_prepared",
    Path("dist"),
    Path("installers") / "runtimes",
    Path("installers") / "runtime-archives",
    Path("resources") / "featurehero" / ".venv",
}
PIPELINE_MODEL_CODE_FILES = {
    "__init__.py",
    "grain_yield_model.py",
    "runtime_predict.py",
}
PIPELINE_MODEL_BUNDLE_FILES = {
    "metadata.json",
    "best_model_sort_original.pkl",
    "best_features_sort_original.pkl",
    "sort_original.csv",
    "selection_summary.json",
    "optimization_sort_original.csv",
    "optimization_overlap_sort_original.csv",
    "phase04_normalization_stats.json",
    "phase04_selected_fields.csv",
}


def python_launcher() -> str:
    if os.name == "nt":
        base = Path(sys.executable)
        pythonw = base.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return sys.executable


def resolve_install_root() -> Path:
    home = Path.home()
    system = platform.system()
    if system == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")) / APP_NAME
    if system == "Darwin":
        return home / "Applications" / APP_NAME
    return home / ".local" / "share" / APP_NAME


def resolve_installed_app_dir() -> Path:
    return resolve_install_root() / "app" / PACKAGE_DIR_NAME


def resolve_installed_installers_dir() -> Path:
    return resolve_installed_app_dir() / "installers"


def resolve_state_file() -> Path:
    return resolve_install_root() / INSTALLER_STATE_NAME


def resolve_featurehero_runtime_dir(app_dir: Path | None = None) -> Path:
    base_app_dir = app_dir or resolve_installed_app_dir()
    return base_app_dir / "resources" / "featurehero" / ".venv"


def resolve_bundled_runtime_dir(platform_name: str) -> Path:
    return APP_DIR / "runtime" / platform_name


def resolve_bundled_macos_python_pkg(app_dir: Path | None = None) -> Path:
    base_app_dir = app_dir or resolve_installed_app_dir()
    return base_app_dir / "python-installer" / "python-3.12.pkg"


def iter_runtime_python_candidates(venv_dir: Path) -> list[Path]:
    return [
        venv_dir / "bin" / "python3",
        venv_dir / "bin" / "python",
        venv_dir / "Scripts" / "python.exe",
        venv_dir / "Scripts" / "python3.exe",
    ]


def python_version_tuple(python_exec: Path | str) -> tuple[int, int] | None:
    try:
        result = subprocess.run(
            [str(python_exec), "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    output = result.stdout.strip()
    try:
        major, minor = output.split(".", 1)
        return int(major), int(minor)
    except (ValueError, TypeError):
        return None


def resolve_python312_command() -> str | None:
    candidates = [
        shutil.which("python3.12"),
        "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
        "/usr/local/bin/python3.12",
        "/opt/homebrew/bin/python3.12",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        version = python_version_tuple(candidate)
        if version and version >= (3, 12):
            return str(candidate)
    return None


def resolve_bootstrap_python() -> str:
    python312 = resolve_python312_command()
    if python312:
        return python312
    candidates = [
        shutil.which("python3"),
        shutil.which("python"),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return "python3"


def ensure_macos_python312(app_dir: Path) -> str:
    python_exec = resolve_python312_command()
    if python_exec:
        return python_exec

    pkg_path = resolve_bundled_macos_python_pkg(app_dir)
    if not pkg_path.exists():
        raise FileNotFoundError(
            f"Bundled Python 3.12 installer was not found in the app snapshot: {pkg_path}"
        )

    install_command = f"installer -pkg {shlex.quote(str(pkg_path))} -target /"
    if shutil.which("osascript"):
        subprocess.run(
            ["osascript", "-e", f'do shell script {install_command!r} with administrator privileges'],
            check=True,
        )
    else:
        raise RuntimeError(
            "macOS Python 3.12 is required. Install it from the bundled pkg manually: "
            f"{pkg_path}"
        )

    python_exec = resolve_python312_command()
    if python_exec:
        return python_exec
    raise RuntimeError("Python 3.12 installation completed but python3.12 is still not available.")


def bootstrap_featurehero_runtime(app_dir: Path, *, required: bool, allow_create: bool = True, python_exec: str | None = None) -> str:
    featurehero_dir = app_dir / "resources" / "featurehero"
    if not featurehero_dir.exists():
        if required:
            raise FileNotFoundError(f"FeatureHero source was not found in the installed app: {featurehero_dir}")
        return "FeatureHero source directory was not found; runtime bootstrap skipped."

    venv_dir = resolve_featurehero_runtime_dir(app_dir)
    existing_python = next((candidate for candidate in iter_runtime_python_candidates(venv_dir) if candidate.exists()), None)
    if existing_python is not None:
        version = python_version_tuple(existing_python)
        if version and version >= (3, 12):
            return f"FeatureHero runtime detected at {venv_dir}."
        shutil.rmtree(venv_dir, ignore_errors=True)
    if not allow_create:
        raise FileNotFoundError(
            f"FeatureHero bundled runtime was not found in the installer payload: {venv_dir}"
        )

    selected_python = python_exec or resolve_bootstrap_python()
    subprocess.run([selected_python, "-m", "venv", str(venv_dir)], check=True)
    venv_python = next((candidate for candidate in iter_runtime_python_candidates(venv_dir) if candidate.exists()), None)
    if venv_python is None:
        raise FileNotFoundError(f"FeatureHero virtualenv Python was not created in: {venv_dir}")

    subprocess.run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run([str(venv_python), "-m", "pip", "install", "."], cwd=str(featurehero_dir), check=True)
    return f"FeatureHero runtime prepared at {venv_dir}."


def windows_targets() -> list[Path]:
    home = Path.home()
    desktop = home / "Desktop"
    start_menu = Path(os.environ.get("APPDATA", home)) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    return [
        desktop / f"{APP_NAME}.cmd",
        start_menu / APP_NAME / f"{APP_NAME}.cmd",
        desktop / f"Desinstalar {APP_NAME}.cmd",
        start_menu / APP_NAME / f"Desinstalar {APP_NAME}.cmd",
    ]


def linux_targets() -> list[Path]:
    home = Path.home()
    return [
        home / ".local" / "share" / "applications" / "mictlan-agrixgboost.desktop",
        home / "Desktop" / "mictlan-agrixgboost.desktop",
        home / ".local" / "share" / "applications" / "mictlan-agrixgboost-uninstall.desktop",
        home / "Desktop" / "mictlan-agrixgboost-uninstall.desktop",
    ]


def mac_targets() -> list[Path]:
    home = Path.home()
    applications = home / "Applications"
    return [
        applications / f"{APP_NAME}.command",
        home / "Desktop" / f"{APP_NAME}.command",
        applications / f"Desinstalar {APP_NAME}.command",
        home / "Desktop" / f"Desinstalar {APP_NAME}.command",
    ]


def write_windows_cmd(path: Path, command: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"@echo off\r\n{command}\r\n", encoding="utf-8")


def write_shell_launcher(path: Path, command: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"#!/usr/bin/env bash\n{command}\n", encoding="utf-8")
    path.chmod(0o755)


def write_linux_desktop(path: Path, *, name: str, exec_command: str, icon: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        f"Exec={exec_command}\n"
        f"Icon={icon}\n"
        "Terminal=false\n"
        "Categories=Utility;Science;Education;\n"
    )
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def save_state(files: list[Path], install_root: Path) -> None:
    state_file = resolve_state_file()
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "install_root": str(install_root),
                "installed_files": [str(path) for path in files],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def load_state() -> tuple[Path | None, list[Path]]:
    state_file = resolve_state_file()
    if not state_file.exists():
        return None, []
    data = json.loads(state_file.read_text(encoding="utf-8"))
    install_root = Path(data["install_root"]) if data.get("install_root") else None
    installed_files = [Path(item) for item in data.get("installed_files", [])]
    return install_root, installed_files


def _read_json_file(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def resolve_latest_pipeline_model_dir() -> Path | None:
    models_root = APP_DIR / "pipeline" / "model"
    if not models_root.exists():
        return None

    candidates: list[tuple[str, Path]] = []
    for child in models_root.iterdir():
        if not child.is_dir():
            continue
        metadata_path = child / "metadata.json"
        if not metadata_path.exists():
            continue
        metadata = _read_json_file(metadata_path)
        sort_key = str(metadata.get("created_at") or child.name)
        candidates.append((sort_key, child))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def copy_entry(source: Path, destination: Path, relative_path: Path | None = None) -> None:
    normalized_relative_path = relative_path or Path(source.name)
    if should_skip_entry(normalized_relative_path):
        return
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            copy_entry(child, destination / child.name, normalized_relative_path / child.name)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def should_skip_entry(relative_path: Path) -> bool:
    normalized_parts = tuple(part for part in relative_path.parts if part not in {"", "."})
    if not normalized_parts:
        return False
    normalized_path = Path(*normalized_parts)
    pipeline_model_root = Path("pipeline") / "model"
    if normalized_path == pipeline_model_root:
        return False
    if pipeline_model_root in normalized_path.parents:
        latest_model_dir = resolve_latest_pipeline_model_dir()
        latest_model_name = latest_model_dir.name if latest_model_dir is not None else ""
        relative_to_model_root = normalized_path.relative_to(pipeline_model_root)
        if len(relative_to_model_root.parts) == 1:
            entry_name = relative_to_model_root.name
            if entry_name in PIPELINE_MODEL_CODE_FILES:
                return False
            if entry_name == latest_model_name:
                return False
            return True
        model_name = relative_to_model_root.parts[0]
        if model_name != latest_model_name:
            return True
        if relative_to_model_root.name in PIPELINE_MODEL_BUNDLE_FILES:
            return False
        return True
    if normalized_path in SKIP_RELATIVE_PATHS:
        return True
    if any(parent in SKIP_RELATIVE_PATHS for parent in normalized_path.parents):
        return True
    if any(part in SKIP_DIR_NAMES for part in normalized_parts):
        return True
    name = normalized_path.name
    if name in SKIP_FILE_NAMES:
        return True
    if any(name.endswith(suffix) for suffix in SKIP_FILE_SUFFIXES):
        return True
    return False


def stage_bundled_runtime(app_dir: Path, platform_name: str) -> str:
    bundled_runtime_dir = resolve_bundled_runtime_dir(platform_name)
    if not bundled_runtime_dir.exists():
        return f"No bundled runtime was found for {platform_name}; fallback bootstrap will be used."

    copied_any = False
    for child in bundled_runtime_dir.iterdir():
        destination = app_dir / child.name
        if destination.exists():
            if destination.is_dir():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        if child.is_dir():
            shutil.copytree(child, destination, symlinks=True)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(child, destination)
        copied_any = True

    if not copied_any:
        return f"Bundled runtime directory for {platform_name} was empty; fallback bootstrap will be used."
    return f"Bundled runtime copied from {bundled_runtime_dir}."


def stage_application_snapshot() -> tuple[Path, list[str]]:
    install_root = resolve_install_root()
    app_install_dir = resolve_installed_app_dir()
    if app_install_dir.exists():
        shutil.rmtree(app_install_dir)
    app_install_dir.mkdir(parents=True, exist_ok=True)

    copied_entries: list[str] = []
    for entry_name in REQUIRED_APP_ENTRIES + OPTIONAL_APP_ENTRIES:
        source = APP_DIR / entry_name
        if not source.exists():
            if entry_name in REQUIRED_APP_ENTRIES:
                raise FileNotFoundError(f"Missing required app entry for installer snapshot: {source}")
            continue
        if source.is_dir():
            for child in source.iterdir():
                relative_child = Path(entry_name) / child.name
                if should_skip_entry(relative_child):
                    continue
                copy_entry(child, app_install_dir / relative_child, relative_child)
        else:
            if should_skip_entry(Path(entry_name)):
                continue
            copy_entry(source, app_install_dir / entry_name, Path(entry_name))
        copied_entries.append(entry_name)
    return install_root, copied_entries


def install_windows() -> str:
    install_root, copied_entries = stage_application_snapshot()
    runtime_copy_message = stage_bundled_runtime(resolve_installed_app_dir(), "windows")
    bundled_python = resolve_bundled_python_command(resolve_installed_app_dir(), "windows")
    if not bundled_python:
        raise FileNotFoundError("Bundled Python 3.12 was not found for Windows installation.")
    runtime_bootstrap_message = bootstrap_featurehero_runtime(
        resolve_installed_app_dir(),
        required=False,
        python_exec=bundled_python,
    )
    runtime_message = f"{runtime_copy_message} {runtime_bootstrap_message}".strip()
    installed_installers_dir = resolve_installed_installers_dir()
    launch_script = installed_installers_dir / LAUNCHER_SCRIPT_NAME
    installer_script = installed_installers_dir / "desktop_installer.py"
    launch_command = f'start "" "{python_launcher()}" "{launch_script}"'
    uninstall_command = f'start "" "{python_launcher()}" "{installer_script}" --uninstall'

    created_files: list[Path] = [install_root]
    targets = windows_targets()
    for path in targets[:2]:
        write_windows_cmd(path, launch_command)
        created_files.append(path)
    for path in targets[2:]:
        write_windows_cmd(path, uninstall_command)
        created_files.append(path)

    save_state(created_files, install_root)
    return (
        "Instalacion completada en Windows. "
        f"Se actualizo la snapshot local con {len(copied_entries)} componentes y se recrearon los accesos. "
        f"{runtime_message}"
    )


def install_linux() -> str:
    install_root, copied_entries = stage_application_snapshot()
    runtime_copy_message = stage_bundled_runtime(resolve_installed_app_dir(), "linux")
    bundled_python = resolve_bundled_python_command(resolve_installed_app_dir(), "linux")
    if not bundled_python:
        raise FileNotFoundError("Bundled Python 3.12 was not found for Linux installation.")
    runtime_bootstrap_message = bootstrap_featurehero_runtime(
        resolve_installed_app_dir(),
        required=False,
        python_exec=bundled_python,
    )
    runtime_message = f"{runtime_copy_message} {runtime_bootstrap_message}".strip()
    installed_installers_dir = resolve_installed_installers_dir()
    launch_script = installed_installers_dir / LAUNCHER_SCRIPT_NAME
    installer_script = installed_installers_dir / "desktop_installer.py"
    python_exec = shutil.which("python3") or "python3"
    launch_exec = f'{python_exec} "{launch_script}"'
    uninstall_exec = f'{python_exec} "{installer_script}" --uninstall'
    icon_path = resolve_installed_app_dir() / ICON_RELATIVE_PATH

    created_files: list[Path] = [install_root]
    targets = linux_targets()
    for path in targets[:2]:
        write_linux_desktop(path, name=APP_NAME, exec_command=launch_exec, icon=icon_path)
        created_files.append(path)
    for path in targets[2:]:
        write_linux_desktop(
            path,
            name=f"Desinstalar {APP_NAME}",
            exec_command=uninstall_exec,
            icon=icon_path,
        )
        created_files.append(path)

    save_state(created_files, install_root)
    return (
        "Instalacion completada en Linux. "
        f"Se actualizo la snapshot local con {len(copied_entries)} componentes y se recrearon los lanzadores. "
        f"{runtime_message}"
    )


def install_macos() -> str:
    install_root, copied_entries = stage_application_snapshot()
    runtime_copy_message = stage_bundled_runtime(resolve_installed_app_dir(), "macos")
    macos_python = ensure_macos_python312(resolve_installed_app_dir())
    runtime_bootstrap_message = bootstrap_featurehero_runtime(
        resolve_installed_app_dir(),
        required=True,
        allow_create=True,
        python_exec=macos_python,
    )
    runtime_message = f"{runtime_copy_message} {runtime_bootstrap_message}".strip()
    installed_installers_dir = resolve_installed_installers_dir()
    launch_script = installed_installers_dir / LAUNCHER_SCRIPT_NAME
    installer_script = installed_installers_dir / "desktop_installer.py"
    python_exec = shutil.which("python3") or "python3"
    launch_command = f'"{python_exec}" "{launch_script}"'
    uninstall_command = f'"{python_exec}" "{installer_script}" --uninstall'

    created_files: list[Path] = [install_root]
    targets = mac_targets()
    for path in targets[:2]:
        write_shell_launcher(path, launch_command)
        created_files.append(path)
    for path in targets[2:]:
        write_shell_launcher(path, uninstall_command)
        created_files.append(path)

    save_state(created_files, install_root)
    return (
        "Instalacion completada en macOS. "
        f"Se actualizo la snapshot local con {len(copied_entries)} componentes y se recrearon los lanzadores. "
        f"{runtime_message}"
    )


def uninstall_desktop() -> str:
    install_root, installed_files = load_state()
    removed = 0
    for path in installed_files:
        if path.exists() and path.is_file():
            path.unlink()
            removed += 1

    state_file = resolve_state_file()
    if state_file.exists():
        state_file.unlink()

    if install_root and install_root.exists():
        shutil.rmtree(install_root, ignore_errors=True)

    start_menu_dir = Path(os.environ.get("APPDATA", Path.home())) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / APP_NAME
    if start_menu_dir.exists() and not any(start_menu_dir.iterdir()):
        start_menu_dir.rmdir()

    return f"Desinstalacion completada. Archivos eliminados: {removed}."


def install_for_current_platform() -> str:
    system = platform.system()
    if system == "Windows":
        return install_windows()
    if system == "Linux":
        return install_linux()
    if system == "Darwin":
        return install_macos()
    return f"Sistema no soportado por este instalador: {system}"


def build_ui() -> tk.Tk:
    if tk is None or messagebox is None:
        raise RuntimeError(
            "Tkinter is not available in this Python environment. Run the installer with --headless or install tkinter."
        )
    root = tk.Tk()
    root.title(f"{APP_NAME} Installer")
    root.geometry("640x340")
    root.resizable(False, False)
    root.configure(bg="#f4efe6")

    system = platform.system()
    title = tk.Label(
        root,
        text=f"{APP_NAME} Installer",
        font=("Segoe UI", 18, "bold"),
        bg="#f4efe6",
        fg="#1f2a2f",
    )
    title.pack(pady=(20, 8))

    subtitle = tk.Label(
        root,
        text=(
            "Instalador de escritorio con snapshot local de la app.\n"
            f"Sistema detectado: {system}"
        ),
        font=("Segoe UI", 11),
        bg="#f4efe6",
        fg="#54646d",
        justify="center",
    )
    subtitle.pack()

    install_root = resolve_install_root()
    status_var = tk.StringVar(
        value=(
            "Puedes instalar o desinstalar la snapshot local de la app desde aqui.\n"
            f"Destino de instalacion: {install_root}"
        )
    )

    status_label = tk.Label(
        root,
        textvariable=status_var,
        wraplength=560,
        justify="center",
        font=("Segoe UI", 10),
        bg="#f4efe6",
        fg="#243a40",
    )
    status_label.pack(pady=(22, 18))

    buttons = tk.Frame(root, bg="#f4efe6")
    buttons.pack()

    def on_install() -> None:
        try:
            message = install_for_current_platform()
            status_var.set(message)
            messagebox.showinfo("Instalacion completada", message)
        except Exception as exc:
            status_var.set(str(exc))
            messagebox.showerror("Error", str(exc))

    def on_uninstall() -> None:
        try:
            message = uninstall_desktop()
            status_var.set(message)
            messagebox.showinfo("Desinstalacion completada", message)
        except Exception as exc:
            status_var.set(str(exc))
            messagebox.showerror("Error", str(exc))

    install_button = tk.Button(
        buttons,
        text="Instalar",
        width=18,
        command=on_install,
        bg="#2f7d32",
        fg="white",
        activebackground="#256528",
        activeforeground="white",
        relief="flat",
        padx=10,
        pady=8,
    )
    install_button.grid(row=0, column=0, padx=12)

    uninstall_button = tk.Button(
        buttons,
        text="Desinstalar",
        width=18,
        command=on_uninstall,
        bg="#b75c3b",
        fg="white",
        activebackground="#9c4d31",
        activeforeground="white",
        relief="flat",
        padx=10,
        pady=8,
    )
    uninstall_button.grid(row=0, column=1, padx=12)

    close_button = tk.Button(
        root,
        text="Cerrar",
        width=16,
        command=root.destroy,
        bg="#e8dccd",
        fg="#243a40",
        relief="flat",
        padx=8,
        pady=6,
    )
    close_button.pack(pady=(26, 0))

    return root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Desktop installer for Mictlan-AgriXGBoost.")
    parser.add_argument("--uninstall", action="store_true", help="Remove the installed snapshot and shortcuts.")
    parser.add_argument("--install", action="store_true", help="Install or refresh the local snapshot and shortcuts.")
    parser.add_argument("--headless", action="store_true", help="Run without the Tk UI.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.headless or args.install or args.uninstall:
        message = uninstall_desktop() if args.uninstall else install_for_current_platform()
        print(message)
        return
    if tk is None or messagebox is None:
        message = install_for_current_platform()
        print(message)
        return
    root = build_ui()
    root.mainloop()


if __name__ == "__main__":
    main()
