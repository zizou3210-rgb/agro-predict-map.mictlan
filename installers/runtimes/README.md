Place platform-native Python 3.12 payloads here before building the native installer archives.

Expected folders after extracting the platform archives:

- `installers/runtimes/linux/`
- `installers/runtimes/windows/`
- `installers/runtimes/macos/`

Each folder should contain the Python 3.12 payload that the installer will use to create `resources/featurehero/.venv` locally on the destination machine.
The `.venv` itself is not bundled ahead of time; the installer creates it during installation and validates that required modules such as `rasterio` were installed successfully.

Examples:

- Linux:
  `python-runtime/bin/python3`
- Windows:
  `python-runtime/python.exe`
- macOS:
  `python-installer/python-3.12.pkg`

GitHub Actions now builds and uploads one compressed runtime archive per platform:

- `runtime-linux.tar.gz`
- `runtime-windows.tar.gz`
- `runtime-macos.tar.gz`

The assemble step extracts those archives back into `installers/runtimes/<platform>/` before running the native packaging script.

Build command:

`python3 installers/build_native_runtime_packages.py`
