Place native runtimes here before building fully self-contained installers.

Expected folders after extracting the platform archives:

- `installers/runtimes/linux/`
- `installers/runtimes/windows/`
- `installers/runtimes/macos/`

Each folder should contain a platform-native runtime tree. Examples:

- Linux:
  `resources/featurehero/.venv/bin/python3`
- Windows:
  `resources/featurehero/.venv/Scripts/python.exe`
  or `python/python.exe`
- macOS:
  `resources/featurehero/.venv/bin/python3`

GitHub Actions now builds and uploads one compressed runtime archive per platform:

- `runtime-linux.tar.gz`
- `runtime-windows.tar.gz`
- `runtime-macos.tar.gz`

The assemble step extracts those archives back into `installers/runtimes/<platform>/` before running the native packaging script.

Build command:

`python3 installers/build_native_runtime_packages.py`
