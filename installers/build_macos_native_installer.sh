#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FEATUREHERO_DIR="$APP_DIR/resources/featurehero"
FEATUREHERO_VENV_DIR="$FEATUREHERO_DIR/.venv"
MACOS_RUNTIME_DIR="$SCRIPT_DIR/runtimes/macos"
MACOS_RUNTIME_FEATUREHERO_DIR="$MACOS_RUNTIME_DIR/resources/featurehero"
MACOS_RUNTIME_VENV_DIR="$MACOS_RUNTIME_FEATUREHERO_DIR/.venv"

if command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN="python3.12"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
else
  echo "No se encontro python3 ni python3.12 en PATH."
  exit 1
fi

echo "Usando Python: $PYTHON_BIN"
echo "Proyecto: $APP_DIR"

if [ ! -d "$FEATUREHERO_DIR" ]; then
  echo "No existe el directorio esperado: $FEATUREHERO_DIR"
  exit 1
fi

echo "Preparando runtime nativo de macOS para FeatureHero..."
rm -rf "$FEATUREHERO_VENV_DIR"
"$PYTHON_BIN" -m venv "$FEATUREHERO_VENV_DIR"
"$FEATUREHERO_VENV_DIR/bin/python" -m pip install --upgrade pip
"$FEATUREHERO_VENV_DIR/bin/python" -m pip install "$FEATUREHERO_DIR"

echo "Copiando runtime a installers/runtimes/macos..."
rm -rf "$MACOS_RUNTIME_VENV_DIR"
mkdir -p "$MACOS_RUNTIME_FEATUREHERO_DIR"
cp -R "$FEATUREHERO_VENV_DIR" "$MACOS_RUNTIME_VENV_DIR"

echo "Generando paquete instalador nativo para macOS..."
"$PYTHON_BIN" "$SCRIPT_DIR/build_native_runtime_packages.py"

echo
echo "Listo."
echo "Paquete generado:"
echo "  $APP_DIR/dist/Mictlan-AgriXGBoost-installer-macos-native.zip"
