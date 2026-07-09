Place native runtimes here before building fully self-contained installers.

Expected folders:

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

Build command:

`python3 cimmyt_app/installers/build_native_runtime_packages.py`
