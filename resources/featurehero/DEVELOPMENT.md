# Guía de Desarrollo de Feature Hero

Esta sección es para quienes desean contribuir o modificar el código fuente de `Feature Hero`.

## 1. Configuración del Entorno de Desarrollo

1.  **Clonar el repositorio**:
    ```bash
    git clone <URL_DEL_REPOSITORIO>
    cd featurehero # O el nombre de tu directorio
    ```
2.  **Instalar Python 3.12**: Asegúrate de tener Python 3.12 o una versión compatible.
3.  **Instalar Poetry**: Sigue las instrucciones en python-poetry.org.
4.  **Configurar el entorno del proyecto**: Desde la raíz del proyecto, ejecuta:
    ```bash
    poetry install
    ```
    Esto instalará todas las dependencias (incluidas las de desarrollo) y el propio proyecto en modo editable, lo que te permitirá modificar el código y ver los cambios reflejados inmediatamente.

## 2. Building the Package

To build the distribution packages (sdist and wheel) that can be published or installed with `pip`:

```bash
poetry build
```
Los archivos generados se encontrarán en el directorio `dist/`.

## 3. Consideraciones al Modificar el Código

*   **Formato de Código**: Se recomienda seguir las convenciones de estilo de Python (PEP 8). Considera usar herramientas como `black` para el formateo automático y `pylint` o `flake8` para el análisis estático de código.

*   **Actualización de Dependencias**: Si agregas o modificas dependencias, usa `poetry add <package>` o `poetry update` para gestionar los archivos `pyproject.toml` y `poetry.lock`.

*   **Actualización de la Versión**: Si cambias la versión en `pyproject.toml`, recuerda que `poetry install` actualizará el entorno virtual para reflejar la nueva versión.

*   **Ejecución de Comandos**: Durante el desarrollo, recuerda prefijar tus comandos con `poetry run` para ejecutarlos dentro del entorno virtual gestionado por Poetry.
    ```bash
    poetry run featurehero --help
    ```