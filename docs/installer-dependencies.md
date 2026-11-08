# Dependencias del instalador

La instalación copia el código de la app y crea un entorno Python **3.12** en `resources/featurehero/.venv`. Las dependencias se instalan desde `resources/featurehero/pyproject.toml`; el servidor y los procesos de predicción deben usar ese entorno, no solamente el Python base incluido en el paquete.

## Bibliotecas verificadas

Se comprueba la presencia y la importación real de `featurehero`, `pandas`, `numpy`, `openpyxl`, `certifi`, `PIL` (Pillow), `rasterio`, `psutil`, `pykrige`, `sklearn` (scikit-learn), `xgboost`, `matplotlib`, `seaborn`, `numbers_parser`, `scipy` y `joblib`. SciPy y joblib son dependencias transitivas de las bibliotecas declaradas; también se validan porque el código las utiliza.

La instalación ejecuta también los scripts de las fases CE con `--help` en procesos separados y sin `PYTHONPATH` heredado. Esto comprueba la misma forma de arranque que utiliza New Workspace.

La instalación importa los puntos de entrada del servidor, preprocesamiento, entrenamiento, predicción y FeatureHero antes de declararse terminada. Esto detecta archivos faltantes, dependencias binarias incompatibles y módulos instalados en un intérprete distinto.

`resources/phen_transform_dataset` está incluido como recurso, pero sus servicios Celery/Redis y su entorno Docker no se ejecutan en el flujo de escritorio actual; su antiguo `requirements.txt` no se mezcla con el entorno de FeatureHero.

## Archivos incluidos y comprobados

- Módulos raíz: `server.py`, `config_env.py`, `shared_cache.py`, `tabular_io.py`, `workbook_preview.py` y `__init__.py`.
- Interfaz: HTML, CSS, manifiesto, iconos, `src` y `selecctionProperties`. Incluye los módulos de estadísticas y colores.
- Procesamiento: `pipeline`, `preprocess`, `ce_pipeline`, sus scripts por fase y el código de inferencia de modelos.
- Recursos: código y configuración de FeatureHero, mapas de países y plantilla canónica.
- Lanzadores y metadatos: `installers` y `package.json`.
- Modelo entrenado: se conserva la regla existente de empaquetar el modelo más reciente cuando está disponible, sin incorporar las corridas temporales.

Los generadores del ZIP universal, los paquetes por plataforma y los paquetes nativos de Windows/Linux/macOS utilizan la misma función de escritura y validación. Antes de publicar el ZIP, comprueban que los archivos obligatorios estén presentes y que sus bytes coincidan con el código fuente actual. Un archivo faltante, filtrado por error o desactualizado impide publicar el paquete. La escritura usa un archivo temporal y conserva el ZIP anterior si la validación falla.

`REQUIRED_APP_ENTRIES` y `REQUIRED_APP_FILES`, en `installers/desktop_installer.py`, definen la validación. Si falta un archivo obligatorio, se rechaza el paquete antes de modificar una instalación anterior. `.env` continúa siendo opcional en la copia; la compilación de CI lo obtiene de los secretos configurados.

## Servicios externos

El instalador mantiene el uso actual de Internet para instalar dependencias, obtener datos de clima y suelo, cargar mapas base y descargar las bibliotecas web D3, JSZip y Choices desde sus CDN. No es un paquete de operación completamente desconectada.

## Pruebas

```bash
python3 -m unittest discover -s tests -p test_installer_packaging.py -v
```

Para incluir la prueba real de imports de una copia completa empaquetada, configurar `APP_INSTALLER_TEST_PYTHON` con la ruta de un Python 3.12 que tenga instalado FeatureHero y sus dependencias. CI ejecuta esa prueba en sus tres plataformas después de archivar el intérprete base, evitando incorporar al archivo de runtime las dependencias instaladas solamente para las pruebas.
