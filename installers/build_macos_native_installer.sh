#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FEATUREHERO_DIR="$APP_DIR/resources/featurehero"
MACOS_RUNTIME_DIR="$SCRIPT_DIR/runtimes/macos"
MACOS_RUNTIME_PYTHON_DIR="$MACOS_RUNTIME_DIR/python-installer"
MACOS_RUNTIME_LIBOMP_DIR="$MACOS_RUNTIME_DIR/runtime-libs"

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

echo "Preparando payload nativo de macOS..."
rm -rf "$MACOS_RUNTIME_DIR"
mkdir -p "$MACOS_RUNTIME_PYTHON_DIR" "$MACOS_RUNTIME_LIBOMP_DIR"

curl -L --fail --retry 3 \
  https://www.python.org/ftp/python/3.12.4/python-3.12.4-macos11.pkg \
  -o "$MACOS_RUNTIME_PYTHON_DIR/python-3.12.pkg"

if command -v brew >/dev/null 2>&1; then
  brew install libomp
  libomp_prefix="$(brew --prefix libomp)"
  cp "$libomp_prefix/lib/libomp.dylib" "$MACOS_RUNTIME_LIBOMP_DIR/libomp.dylib"
else
  echo "Homebrew no esta disponible; no se pudo preparar libomp.dylib."
  exit 1
fi

echo "El instalador reconstruira resources/featurehero/.venv localmente en la maquina destino."

echo "Generando paquete instalador nativo para macOS..."
"$PYTHON_BIN" "$SCRIPT_DIR/build_native_runtime_packages.py"

echo
echo "Listo."
echo "Paquete generado:"
echo "  $APP_DIR/dist/Mictlan-AgriXGBoost-installer-macos-native.zip"
