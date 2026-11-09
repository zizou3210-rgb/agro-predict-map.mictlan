#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/desktop_installer.py" ]; then
  INSTALLER_SCRIPT="$SCRIPT_DIR/desktop_installer.py"
else
  INSTALLER_SCRIPT="$SCRIPT_DIR/installers/desktop_installer.py"
fi
PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
if [ ! -x "$PYTHON_BIN" ]; then
  PAYLOAD_DIR="$(cd "$(dirname "$INSTALLER_SCRIPT")/.." && pwd)"
  PYTHON_PKG="$PAYLOAD_DIR/runtime/macos/python-installer/python-3.12.pkg"
  if [ ! -f "$PYTHON_PKG" ]; then
    echo "No se encontro el instalador incluido de Python 3.12: $PYTHON_PKG" >&2
    exit 1
  fi
  /usr/bin/osascript - "$PYTHON_PKG" <<'APPLESCRIPT'
on run argv
  do shell script "/usr/sbin/installer -pkg " & quoted form of (item 1 of argv) & " -target /" with administrator privileges
end run
APPLESCRIPT
fi
"$PYTHON_BIN" "$INSTALLER_SCRIPT" --headless --install
