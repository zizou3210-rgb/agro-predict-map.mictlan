# Lectura climática por bloques (2026-10-04)

Phase03 usa lotes de hasta 128 píxeles cuando Rasterio y la caché diaria están activos. Cada lote recorre las fechas; para cada fuente/fecha, agrupa los píxeles por bloque nativo y lee una ventana que los contiene. Usa los mismos índices, valores de relleno, reglas para NaN, temperatura y precipitación que la ruta por píxel. Conserva las fechas de referencia, ventanas y agregaciones.

Los planes de rutas se comparten entre lotes. Se guardan muestras diarias en transacciones de hasta aproximadamente 4096 filas; las series se persisten al completar cada lote. Las corridas grandes no retienen todas las series diarias en RAM. La cola tiene como máximo una tarea por worker y la agregación retiene como máximo 128 series, con referencias explícitas para evitar reutilizar resultados por un `id()` reciclado. La ruta anterior también limita su cola y persiste cada grupo terminado.

El planificador conserva límites de fechas por píxel en lugar de conjuntos con todos sus días. Reutiliza ventanas y años de referencia para filas con las mismas fechas, consulta la caché de series en grupos de 128 y deja de consultar rangos diarios cuando ya sabe que todas sus fechas requieren un ráster por algún otro píxel. Publica avance durante la planificación.

## Validación

Pasaron 35 pruebas de clima, caché, lectura por bloques y pipeline de modelo. Incluyen GeoTIFF reales con valores de relleno y NaN, equivalencia exacta de series, caché completa y reparación parcial, límites de agregación, y equivalencia de salidas climáticas para los cinco años 2021–2025 con temperaturas diferentes por año y Tmin ausente algunos días.

La suite ampliada de casos de uso contiene pruebas que requieren `tests/source/AGG_2024_2025_V5.xlsx` (ausente), referencias al paquete antiguo `cimmyt_app` (no disponible) y una expectativa sobre conservación de filas que no corresponde al comportamiento actual de esa función, que no se modificó. No se afirma que esa suite completa pase ni que se haya completado una predicción integral de la región grande.

## Medición local

Se ejecutó `scripts/benchmark_chc_block_reading.py` sobre 64 píxeles contiguos de la corrida `20261004-164126-28b43ac1`, 90 días desde 2021-04-07 y seis workers configurados. Usó rásteres locales existentes y una caché temporal aislada; no descargó ni alteró los datos de la corrida. La comparación incluyó generación de las variables climáticas y dio salidas exactamente iguales.

| Ruta | Tiempo | Aperturas de ráster |
| --- | ---: | ---: |
| Por píxel, control | 14.470 s | 17 280 |
| Por lote, caché diaria vacía | 0.306 s | 270 |
| Por lote, caché diaria llena | 0.070 s | 0 |

El bloque frío fue 47.3 veces más rápido en esta medición. El bloque de 64 píxeles cabe en una sola tarea de la ruta nueva; la ruta anterior distribuye píxeles entre workers. Estos tiempos no representan la predicción completa, ni prueban un factor de mejora constante en toda la región, especialmente para puntos dispersos o periodos/fuentes diferentes.

Para repetir con una corrida disponible:

```bash
resources/featurehero/.venv/bin/python scripts/benchmark_chc_block_reading.py \
  --input-csv /ruta/a/phase03/dataInput.csv \
  --pixels 64 --days 90 --start 2021-04-07 --workers 6 \
  --output /tmp/chc-block-benchmark.json
```

La mejora se aplica a procesos nuevos. Un proceso de predicción que ya estaba ejecutándose conserva el código cargado antes del cambio; reiniciar únicamente el servidor no lo reemplaza.
