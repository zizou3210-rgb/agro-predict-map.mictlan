#!/bin/bash

# Script para ejecutar la aplicación phen-ga en modo GUI (no consola)
# y redirigir la salida a un archivo de log.

# 1. Validar que se ha proporcionado un argumento.
if [ "$#" -ne 2 ]; then
  echo "Error: Debes proporcionar exactamente dos argumentos."
  echo "Uso: $0 /ruta/al/archivo.csv nombre_columna_objetivo"
  exit 1
fi

# 2. Obtener el directorio del archivo de entrada.
FILE_PATH=$1
TARGET_COLUMN=$2
DIR_PATH=$(dirname "$FILE_PATH")

# Validar que el archivo exista
if [ ! -f "$FILE_PATH" ]; then
    echo "Error: El archivo no se encontró en la ruta especificada:"
    echo "$FILE_PATH"
    exit 1
fi

# 3. Crear el directorio de logs si no existe.
LOG_DIR="$DIR_PATH/log"
mkdir -p "$LOG_DIR"

# 4. Definir la ruta completa del archivo de log.
LOG_FILE="$LOG_DIR/run.log"

echo "Iniciando la aplicación en modo terminal..."
echo "La salida se guardará en: $LOG_FILE"

# 5. Ejecutar la aplicación con poetry usando el flag -m para tratarlo como un módulo
# y redirigir stdout y stderr al log.
cd .. # Moverse al directorio raíz del proyecto para que poetry funcione correctamente
poetry run python -m featurehero "$FILE_PATH" "$TARGET_COLUMN" > "$LOG_FILE" 2>&1
