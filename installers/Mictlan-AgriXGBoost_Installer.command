#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$SCRIPT_DIR/desktop_installer.py" ]; then
  INSTALLER_SCRIPT="$SCRIPT_DIR/desktop_installer.py"
else
  INSTALLER_SCRIPT="$SCRIPT_DIR/installers/desktop_installer.py"
fi
python3 "$INSTALLER_SCRIPT" --headless --install
