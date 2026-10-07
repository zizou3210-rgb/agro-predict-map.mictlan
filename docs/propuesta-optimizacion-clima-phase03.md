# Propuesta ajustada: reutilización de valores climáticos diarios en Phase03

## Resumen y decisión

La propuesta original planteaba separar la descarga de rásteres del cálculo. Esa separación ya existe parcialmente: `create_phase03_workbook` calcula las fechas requeridas, completa `prefetch_chc_rasters` y después inicia la precomputación y el cálculo de las series climáticas.

El cambio nuevo que se propone aquí es persistir en SQLite los valores climáticos diarios ya muestreados para cada píxel CHC, y calcular las ventanas desde esos valores en vez de volver a leer los GeoTIFF. La persistencia debe ser incremental y reutilizable entre ejecuciones; no se debe afirmar que será más rápida hasta medirla.

La mejora tiene mayor potencial cuando hay muchas series con fechas superpuestas y los mismos píxeles se vuelven a consultar en corridas posteriores. Para una primera corrida sin caché diaria, materializar los valores añade trabajo de escritura y no elimina la lectura de los rásteres necesaria para obtener las muestras.

## Contexto observado

La corrida `20260826-162146-8d184287` reporta una bounding box de 80 píxeles, diez filas de `CIM-RT-EAPP1-E -001`, 40 pares de fechas por píxel y una unión de 1.632 días (`2019-04-04` a `2023-09-21`). La caché de características tuvo cero aciertos en esa corrida, según las métricas disponibles.

Se recuperó el directorio de salida de esa corrida y se fijó este snapshot de referencia, sin volver a ejecutar el pipeline ni limpiar cachés:

- 10 filas de entrada, 108 celdas de la grilla manual y 80 píxeles CHC únicos.
- 8 pares de fechas fuente con 5 años de referencia; 3.200 series de precomputación en 80 grupos de píxel y 640 series climáticas únicas.
- 6 workers reportados; 0 aciertos y 640 fallos de caché de características; 1.080 filas de salida climática y 1.080 filas de predicción.
- Artefactos de referencia: `output.csv` SHA-256 `e61f553965eeb47103d8e2a2d12311ef6707bc4c2595626750da48bd84ef9c42`; `weekly_windows_audit.csv` SHA-256 `e476970db4eb17910fde1e94eb3c3c69151877e2450fb524cf782b9417d28d2f`; `prediction.csv` SHA-256 `b35bc5d94f129465fdb3909f95830fb09c35dddb4cbd47f1ccba6b6b70dfec65`.

Este snapshot protege la igualdad de resultados, pero **no es aún un benchmark frío/caliente**: el resumen guardado no contiene duración por etapa ni conteo de rásteres descargados. Esos datos deben medirse en ejecuciones controladas posteriores.

El código ya contiene estos mecanismos:

- `collect_required_chc_dates` deduplica fechas requeridas, incluye las ventanas climáticas y resuelve pares de años de referencia cuando aplica.
- `prefetch_chc_rasters` prepara las combinaciones de fecha y fuente antes de iniciar los workers de cálculo.
- `precompute_chc_series_batches` agrupa series por píxel y recorre una vez la unión de fechas que necesita cada grupo, reutilizando las muestras entre ventanas superpuestas.
- `_CHC_PIXEL_DAILY_SAMPLE_CACHE` evita repetir una muestra fuente/píxel/fecha durante la ejecución actual; es una caché en memoria y se limpia al terminar Phase03.
- La aplicación persiste series climáticas por píxel y rango de fechas, además de resultados de características. No persiste hoy una tabla canónica de valores diarios por píxel.
- La lectura de rásteres está limitada por worker y por un máximo configurable de archivos abiertos. El backend Rasterio lee ventanas puntuales; el backend PIL mantiene la imagen y accede al píxel.

Por eso, esta propuesta no vuelve a implementar el prefetch ni la agrupación por píxel. Se enfoca en hacer la reutilización diaria durable entre ejecuciones y en evitar descargas/lecturas cuando los datos requeridos ya estén completos en caché.

## Objetivo

Para cada combinación única de píxel CHC y fecha requerida:

1. Reutilizar el valor diario persistido si existe y corresponde a las versiones vigentes de las fuentes.
2. Si falta, leer los rásteres locales ya preparados, calcular precipitación (`PRECTOTCORR`) y temperatura diaria (`T2M`) con las mismas reglas actuales, y guardar el resultado por lotes.
3. Calcular las ventanas y generar las salidas usando los valores diarios, preservando exactamente las métricas actuales.

Se deben mantener la caché de series/features existente, el límite de archivos abiertos, la deduplicación de series y la posibilidad de reparar datos ausentes o inválidos de forma controlada.

## Diseño propuesto

### 1. Determinar primero el trabajo climático efectivo

- Construir las filas climáticas efectivas y los píxeles CHC después de aplicar las expansiones de localidades o de la grilla manual. No inferir el conjunto de píxeles sólo de las filas fuente: en modo de grilla las coordenadas calculadas pueden diferir.
- Resolver las fechas de todas las ventanas y de todos los años de referencia. Conservar la deduplicación por fecha y por clave píxel/fecha.
- Consultar la caché de características antes de descargar rásteres. Si todas las filas requeridas son aciertos válidos de características, no hace falta descargar ni materializar datos diarios para esa corrida.
- Para las características faltantes, consultar también la caché de series actual y determinar qué claves diarias aún no están materializadas.

### 2. Definir una caché durable de muestras diarias

- Añadir una tabla SQLite versionada para muestras diarias. Clave lógica recomendada: `pixel_id + fecha + climate_data_version`.
- Guardar como mínimo `T2M`, `PRECTOTCORR` y un estado explícito de validez/sin dato. `T2M` debe seguir usando las mismas reglas que hoy: promedio de Tmax/Tmin cuando ambas existen y el único valor disponible si falta una de ellas. La precipitación debe conservar las reglas actuales para NoData y valores de relleno.
- La versión debe permitir invalidar o recalcular las muestras si cambian las fuentes, la resolución CHC, la transformación de píxel o las reglas de cálculo. No reutilizar silenciosamente registros creados con una versión incompatible.
- Usar índices que soporten consultas por píxel y rango de fechas. Guardar filas en lotes y transacciones, no hacer una escritura por cada valor aislado.
- Mantener la caché en SQLite bajo el modo WAL existente. Evitar que todos los workers escriban a la vez: usar un escritor por lotes o una cola acotada y medir la contención del bloqueo SQLite.

Para el ejemplo observado, el límite teórico si los 80 píxeles fueran únicos es 130.560 filas diarias combinadas (`80 × 1.632`), con hasta 391.680 lecturas puntuales de fuente (`80 × 1.632 × 3`) en una caché diaria inicialmente vacía. Son dimensiones de referencia, no una estimación de tiempo ni garantía de que todos los días/píxeles deban procesarse.

### 3. Preparar rásteres y materializar faltantes

- Descargar cada combinación única `dataset + fecha` sólo cuando haya muestras diarias faltantes que necesiten esa fuente.
- Validar los archivos existentes en caché y los recién descargados como rásteres legibles antes de marcarlos preparados. El prefetch actual acepta archivos por existencia; eso no basta para descartar archivos truncados o inválidos.
- Recorrer las fechas faltantes en orden ascendente. Para cada fecha, resolver CHIRPS, CHIRTS Tmax y CHIRTS Tmin, abrir cada ráster una vez por worker/proceso de extracción cuando sea posible y extraer los valores de todos los píxeles requeridos ese día.
- Investigar una lectura por bloques/ventanas que agrupe píxeles próximos. No asumir que cientos de lecturas puntuales repetidas por ráster son más baratas que la consulta SQLite que se intenta evitar.
- Escribir las muestras diarias en lotes. Limitar en vuelo el trabajo de extracción y las filas pendientes de escritura para controlar memoria y presión sobre SQLite.
- Si una descarga, validación o extracción falla, no insertar una fila que parezca válida. Informar fuente, fecha, píxel y error, y dejar disponible una reparación/reintento acotado.

La expansión de grilla/localidades y la consulta de caché de características ocurren hoy dentro del procesamiento posterior al prefetch. Para aprovechar el fast path y conocer los píxeles reales antes de descargar, el planificador deberá adelantar o compartir esa preparación sin duplicarla ni alterar el orden/contrato de las salidas.

### 4. Calcular exclusivamente desde muestras diarias

- Para el cálculo normal, consultar el rango diario requerido por píxel desde SQLite o desde una caché de memoria acotada, y luego construir la serie `T2M`/`PRECTOTCORR` que consumen las funciones actuales de agregación.
- Conservar la agregación rápida de ventanas, el formato de fechas, los NoData y la estructura actual de auditoría y salida.
- En el modo estricto, una muestra ausente no debe activar una descarga implícita desde un worker de cálculo. Debe provocar un error explícito con clave píxel/fecha/fuente, o pasar por una etapa de reparación antes de reintentar el cálculo.
- Mantener el flujo antiguo tras una bandera de configuración durante el piloto para permitir comparación y reversión. Retirar esa ruta sólo después de validar igualdad y rendimiento.

### 5. Medir antes de fijar concurrencia o prometer ahorros

Registrar por separado y con contadores agregados:

- aciertos/faltantes de caché de features, series y muestras diarias;
- archivos requeridos, válidos en caché, descargados, inválidos y reintentados;
- duración de descarga, validación, apertura de ráster, extracción, lectura SQLite, escritura SQLite y agregación;
- lecturas de píxel realizadas, píxeles materializados y filas consultadas/escritas;
- esperas por locks de descarga y SQLite, memoria máxima aproximada y workers activos por etapa.

Publicar en `progress.json` el total y avance de tareas, fase actual y contadores. ETA y tasa sólo deben mostrarse cuando haya suficientes muestras y con una unidad inequívoca. Evitar loggear cada píxel/día en modo normal.

La instrumentación inicial registra en `progress.json` la tasa/ETA de archivos y acumulados de resolución, validación y resolución de descargas. `metadata.json` registra tiempos para lookup de features, plan de cachés/fechas, prefetch, precomputación/muestreo y cálculo de series/salidas. El acumulado llamado `download_resolution_seconds` incluye resolución del archivo y cualquier espera asociada; no debe interpretarse como tiempo de red puro.

### Resultado del primer benchmark local aislado (2026-10-04)

Se ejecutó `scripts/benchmark_phase03_daily_cache.py` con el runtime de la app (Rasterio), las 4.896 combinaciones de ráster requeridas ya existentes, hard links en un `APP_RUNTIME_DIR` temporal y el modo estricto activo. La caché de features se omitió, y la caché NASA de series se deshabilitó para las tres pasadas. No hubo descargas de red. Las mismas 80 agrupaciones de píxel y 3.200 series de referencia se usaron en cada pasada.

| Pasada | Tiempo de pared | Muestras de ráster | Filas diarias SQLite |
| --- | ---: | ---: | ---: |
| Control, lectura desde ráster | 298.455 s | 391.680 | sin usar |
| Llenado de caché diaria fría | 305.444 s | 391.680 | 130.560 escritas |
| Caché diaria caliente | 2.136 s | 0 | 130.560 reutilizadas |

El llenado costó 6.989 s adicionales (+2.34%) en esta máquina y carga; la pasada caliente fue 139.73× más rápida que el control (99.28% menos tiempo). La SQLite aislada terminó con 24.637.440 bytes (~23.5 MiB). **No extrapolar estos tiempos directamente** a otros equipos, ni al tiempo de red: los TIFF se leyeron desde la caché local y se usaron seis workers.

Las tres pasadas tuvieron cero diferencias en las 13.440 comparaciones de las 21 variables climáticas para 640 series, con tolerancia absoluta `1e-6`. Los hashes de `output.csv`, `weekly_windows_audit.csv` y `prediction.csv` de la corrida histórica siguen intactos. Las predicciones Phase04 no se recalcularon en este benchmark; el resultado demuestra igualdad de las variables climáticas Phase03, no una prueba de inferencia downstream.

El sandbox queda bajo `~/.local/share/MictlanAgriXGBoost/phase03-daily-cache-benchmark-gyytac8_`; contiene los hard links y la SQLite temporal. Es independiente de la caché compartida y no se borró al concluir para conservar evidencia/repetibilidad.

No fijar todavía 3 descargas ni 4–6 workers de cálculo como requisito. Mantener las variables de configuración actuales y comparar concurrencias acotadas; seleccionar valores tras medir errores del proveedor, CPU, disco, memoria y contención de SQLite.

## Cambios previstos

- [ce_pipeline/phase03/script03.py](../ce_pipeline/phase03/script03.py)
  - Reorganizar el planificador para identificar filas expandidas, píxeles y aciertos de caché antes del prefetch, sin duplicar la expansión actual.
  - Añadir la lectura/escritura por lotes de muestras diarias y una ruta de cálculo que consuma esas muestras.
  - Validar los rásteres antes de marcarlos preparados y hacer explícito el modo estricto sin descargas implícitas en cálculo.
  - Añadir métricas por etapa y conservar inicialmente una ruta de comparación con la implementación actual.
- [shared_cache.py](../shared_cache.py)
  - Añadir esquema versionado, consultas por píxel/rango de fechas, inserciones idempotentes por lotes e invalidación/migración segura de datos incompatibles.
  - Mantener transacciones de escritura acotadas y evitar que el bloqueo global serialice trabajo innecesario.
- [tests/test_climate_performance_regression.py](../tests/test_climate_performance_regression.py)
  - Probar deduplicación de claves píxel/fecha y reutilización entre ventanas solapadas.
  - Probar recuperación de caché diaria caliente sin descarga ni apertura de ráster.
  - Probar que faltantes/inválidos se detectan antes del cálculo estricto y no se persisten como datos válidos.
  - Comparar las 21 variables climáticas/auditables con el flujo actual usando fixtures idénticos.
- [tests/test_shared_cache.py](../tests/test_shared_cache.py)
  - Probar round-trip, inserción por lotes, consulta de rangos, valores nulos/NoData, versionado e idempotencia.
- Pruebas de integración de pipeline
  - Comparar el workbook Phase03 y, con los mismos datos/modelo/configuración, las predicciones generadas después por Phase04. Phase03 calcula/enriquece características; la predicción ocurre en la etapa posterior, por lo que se validan por separado.

## Estado de implementación

- **Completado:** recuperado y registrado el snapshot de salida de la corrida de referencia; corregidos dos tests preexistentes que no correspondían a la firma actual de `precompute_chc_series_batches` ni al tipo de recurso que cierra la caché de rásteres.
- **Completado:** añadida en `shared_cache.py` la tabla versionada `daily_climate_cache`, con lectura por claves y rangos, inserción idempotente por lotes y soporte de valores sin dato como filas válidas. Las pruebas usan SQLite temporal.
- **Completado:** conectado el precompute por píxel a la lectura de muestras diarias y persistencia de días faltantes, detrás de `APP_PHASE03_DAILY_CLIMATE_CACHE_ENABLED`; la bandera está apagada por defecto.
- **Completado:** el prefetch se ejecuta ahora después de expandir las filas de localidad/grilla y consultar las cachés de features y series. Sólo prepara fechas necesarias para series sin feature/series cache; con caché diaria activa, excluye fechas ya almacenadas. Una corrida completamente cubierta por features no programa ninguna fecha ni descarga.
- **Completado:** el prefetch valida los rásteres existentes y recién resueltos. Si detecta un archivo inválido, lo repara una vez antes del cómputo; si la reparación también falla, aborta antes de iniciar los workers.
- **Completado:** precomputación y cómputo corren en modo estricto: una ruta ausente o una lectura inválida genera un error explícito; el worker no elimina ni descarga rásteres bajo demanda. El estado global se restaura en `finally`.
- **Completado:** añadidas mediciones agregadas del prefetch y tiempos de las etapas de Phase03; añadidas pruebas para expansión→feature-cache→prefetch sin tareas, aciertos de caché de serie, caché diaria caliente, selección de fechas faltantes, reparación previa, validación TIFF en Rasterio/PIL, fallback de agregación y errores strict sin descarga. Los módulos focalizados de Phase03/SQLite pasan (29 tests en el runtime Rasterio).
- **Completado:** benchmark local aislado con salida idéntica en las 13.440 variables climáticas comparadas; el llenado produjo 130.560 muestras en 305.444 s y la repetición caliente tomó 2.136 s. Ver tabla y condiciones arriba.
- **Pendiente:** recalcular Phase04 con los datos climáticos del benchmark y comparar sus predicciones contra una ejecución downstream equivalente. El benchmark actual no volvió a ejecutar Phase04; tampoco midió una caché fría de red.

## Plan de implementación y validación

1. **Congelar referencia:** ejecutar el caso representativo con el flujo actual y registrar configuración, métricas, `output.csv`, `weekly_windows_audit.csv`, workbook Phase03 y predicciones downstream. Usar las mismas fuentes/archivos para toda comparación.
2. **Añadir pruebas y métricas sin cambiar resultados:** cubrir ventanas, referencias, expansión manual y caché de características. Confirmar qué filas/píxeles/fechas son realmente necesarias.
3. **Implementar el almacenamiento diario detrás de una bandera:** agregar esquema SQLite y acceso por lotes; mantener el flujo de ráster como referencia/fallback controlado.
4. **Validar igualdad:** comparar valores diarios, las 21 variables climáticas, auditoría, filas/columnas/orden, salidas del workbook y predicciones Phase04. Investigar cualquier diferencia antes de seguir.
5. **Benchmark frío y caliente:** medir por separado una primera corrida sin muestras diarias y una repetición con caché diaria completa; añadir una repetición con caché de features completa para verificar que no descargue rásteres.
6. **Evaluar criterios de aceptación:** exigir cero descargas desde workers de cálculo en modo estricto, igualdad exacta salvo tolerancias numéricas previamente definidas, ausencia de filas inválidas en SQLite, y mejora medible en la carga repetida sin regresión inaceptable en la carga fría.
7. **Despliegue gradual:** habilitar para un caso controlado, preservar la opción de volver al flujo anterior y sólo retirar el modo de comparación después de observar varias ejecuciones satisfactorias.

## Criterios para decidir si se conserva el cambio

- **Correctitud:** mismos valores diarios, métricas climáticas, auditoría y predicciones para las mismas entradas y fuentes.
- **Caché caliente:** no se descargan ni abren rásteres cuando todas las muestras requeridas son válidas; tampoco cuando todas las features pueden servirse desde la caché de features.
- **Recuperación:** las claves ausentes o de versión obsoleta se identifican y reconstruyen sin bloquear silenciosamente el cálculo ni contaminar SQLite.
- **Rendimiento:** la repetición con caché diaria mejora el tiempo total de manera reproducible; la primera corrida no sufre una regresión que invalide el caso de uso. Reportar tiempos medidos y percentiles, no rangos estimados sin benchmark.
- **Recursos:** tamaño de SQLite, uso de memoria, CPU, lecturas/escrituras y contención dentro de límites aceptados para los equipos objetivo.

## Riesgos y mitigaciones

| Riesgo | Mitigación |
| --- | --- |
| Cache diaria desactualizada después de cambiar fuentes o reglas | Incluir versión de datos/cálculo en las claves y probar invalidación. |
| Muchas lecturas puntuales de Rasterio siguen siendo costosas | Agrupar píxeles por bloque/ventana; medir extracción antes de adoptar el esquema. |
| SQLite se convierte en cuello de botella por locks o muchas escrituras | Escritura única por lotes, consultas por rango, WAL y métricas de espera. |
| Crecimiento de la base compartida | Medir bytes por muestra, aplicar política de retención/limpieza versionada y no duplicar datos por serie. |
| Píxeles de grilla diferentes a los de las filas fuente | Planificar usando las filas climáticas expandidas y sus IDs CHC efectivos. |
| Faltantes que vuelven a descargar durante el cómputo | Prefetch/reparación antes del cálculo y modo estricto que falle con diagnóstico explícito. |
| Caché de features consultada después de iniciar el prefetch | Mover la consulta de features antes de decidir fechas/raster necesarios; el caso completamente caliente debe saltarse ambos. |
| Predicciones cambian pese a métricas climáticas aparentemente iguales | Validar también el workbook Phase03, contrato Phase04 y predicciones con modelos fijos. |

## Plan de trabajo: descarga y procesamiento de suelos en Phase03

### Objetivo y diagnóstico de partida

Reducir el tiempo de enriquecimiento de suelos y permitir su recuperación entre corridas, conservando coordenadas, filas, orden, columnas, reglas de clasificación y trazabilidad de los datos. Las mejoras de suelos no deben modificar las ventanas climáticas ni los cinco años de referencia de la predicción.

En la corrida `20261004-172147-0b5d247d`, la consulta de estado observada el `2026-10-05T00:58:25Z` reportó 29 de 128.544 puntos procesados, cero aciertos de caché, cero consultas exitosas y 29 resultados `fallback_default`. Es un diagnóstico parcial de esa corrida, no un benchmark ni su resultado final.

El código presenta cuatro problemas concretos:

- En `enrich_soils`, el bloqueo `payload_lock` abarca también la consulta HTTP. Los cuatro workers configurados terminan consultando de forma serial.
- Se envían todos los puntos al executor de una vez, acumulando futuros en memoria.
- El progreso vuelve a sumar todos los puntos resueltos en cada actualización, aumentando el trabajo conforme avanza la corrida.
- El payload de caché se guarda al terminar todos los puntos; una interrupción puede perder los resultados nuevos aún no persistidos.

Además, la resolución captura fallos de red y devuelve textura `Loam` y profundidad `100cm o mas`. Estos registros se almacenan en caché y pueden reutilizarse como aciertos. También debe comprobarse que una respuesta HTTP exitosa contenga realmente las propiedades necesarias: el código puede construir valores predeterminados aunque no haya extraído textura válida.

Al revisar el proveedor, su documentación oficial informa que la API REST está temporalmente pausada y recomienda alternativas como WCS para obtener subconjuntos de mapas. Su disponibilidad deberá verificarse nuevamente al implementar. Fuente: [documentación oficial de SoilGrids y aviso de disponibilidad](https://docs.isric.org/globaldata/soilgrids/index.html), consultada el 2026-10-05 UTC. Aumentar workers por sí solo no resuelve la falta de servicio.

### Etapa 1 — Fijar el contrato y medir la referencia

**Prioridad: inmediata. Dependencia: ninguna.**

1. Guardar entradas, configuración y muestras de respuestas válidas del proveedor, cuando estén disponibles. Incluir coordenadas interiores, límites de píxel, valores ausentes y puntos fuera de cobertura.
2. Documentar las propiedades solicitadas (`sand`, `silt`, `clay`, `depth_to_bedrock`, `depth`), selección de profundidad, estadístico `mean`, unidades y reglas que convierten las fracciones a clase USDA y a las categorías del pipeline.
3. Validar el parser contra respuestas reales o fixtures oficiales: estructura, unidades, NoData y campos obligatorios. Separar HTTP exitoso, dato válido, dato parcial y valor predeterminado en las métricas.
4. Medir tiempos de consulta, espera por locks, lectura/escritura de caché, clasificación y construcción de salidas; registrar memoria, peticiones y motivos de fallback.

**Entregable:** referencia reproducible y contrato de datos. Si se descubre un defecto de interpretación, documentarlo como una corrección funcional separada: comparar contra un parser defectuoso no garantiza resultados correctos.

### Etapa 2 — Corregir ejecución y recuperación del flujo actual

**Prioridad: alta. Dependencia: contrato de referencia.**

- Separar lookup de caché, consulta remota y actualización de caché. Mantener locks breves para el estado compartido y ejecutar la red fuera del bloqueo. Conservar la deduplicación actual de coordenadas a seis decimales.
- Usar una cola de futuros acotada, inicialmente proporcional al número de workers, y reponer tareas al completarse. Configurar concurrencia según límites del proveedor; medirla antes de aumentarla.
- Mantener un contador incremental de filas procesadas. Publicar progreso con una frecuencia acotada, además de una actualización inicial y final.
- Persistir resultados por lotes en SQLite, reutilizando `upsert_soil_cache_entries`; mantener compatibilidad con el JSON por corrida y con la importación/mezcla existente. Usar un escritor coordinado y transacciones breves.
- Vaciar el lote pendiente durante una cancelación controlada. Una terminación abrupta debe perder, como máximo, el lote aún no confirmado; al reiniciar, programar sólo las claves faltantes.
- Registrar fallos por categoría y aplicar reintentos acotados únicamente cuando sean recuperables, respetando `Retry-After` si existe. Evitar repetir consultas masivas cuando la fuente está declarada indisponible; informar ese estado explícitamente.

**Entregable:** ejecución con memoria acotada, resultados persistidos durante el avance y recuperación verificable. Estas correcciones mejoran la mecánica, pero no garantizan datos reales mientras REST esté indisponible.

### Etapa 3 — Diseñar la descarga regional de rásteres

**Prioridad: alta para grillas grandes. Dependencia: validación de fuentes y contrato.**

1. Crear un proveedor de suelos intercambiable: flujo REST de referencia y flujo regional de rásteres, seleccionables mediante configuración. Mantener el nuevo flujo desactivado hasta validarlo.
2. Evaluar WCS para recortes regionales y WebDAV/VRT para teselas necesarias. Probar disponibilidad, límites de tamaño y rendimiento; no asumir que esos servicios estarán siempre operativos.
3. Construir el plan desde los puntos efectivos de la grilla. Descargar únicamente propiedades, profundidades y teselas necesarias para las claves no cubiertas por caché. Para regiones amplias o puntos dispersos, comparar teselas contra un único recorte que pueda incluir mucha superficie sin uso.
4. Conservar resolución y alineación nativas, CRS, estadístico, profundidad y unidades. Añadir el margen requerido por la selección de píxel sin introducir interpolación ni promedios espaciales.
5. Guardar archivos temporales y publicarlos mediante renombrado atómico tras validar legibilidad, cobertura, bandas y metadatos. Registrar fuente, versión y huella del archivo; reparar archivos incompletos antes del muestreo.
6. Limitar descargas simultáneas y tamaño de solicitudes. Reutilizar teselas entre corridas y evitar descargas duplicadas de la misma clave.

**Punto de decisión obligatorio:** comprobar la disponibilidad de una fuente compatible para profundidad hasta roca. No asumir que las capas actuales de textura incluyen `depth_to_bedrock`, ni mezclar versiones de SoilGrids silenciosamente. Si no hay equivalencia demostrable, conservar el tratamiento actual de profundidad y presentar cualquier sustitución como un cambio funcional independiente.

**Entregable:** manifiesto de fuentes y descarga regional validada. Consultar la [documentación oficial de acceso WCS](https://docs.isric.org/globaldata/soilgrids/wcs.html) y [acceso WebDAV](https://docs.isric.org/globaldata/soilgrids/WebDav.html) antes de fijar el mecanismo definitivo.

### Etapa 4 — Muestrear y clasificar por lotes

**Prioridad: alta. Dependencia: rásteres preparados y validados.**

- Transformar cada coordenada al CRS de cada capa y determinar su píxel con la regla compatible con la referencia; comprobar especialmente bordes y ejes.
- Agrupar puntos por tesela y bloque nativo. Leer ventanas acotadas con Rasterio y reutilizar cada lectura entre puntos del mismo bloque; limitar archivos abiertos y buffers en memoria.
- Reutilizar las funciones de clasificación existentes y conservar factores de escala, unidades y reglas de NoData. Compartir muestras entre puntos del mismo píxel sólo cuando se haya demostrado equivalencia.
- Persistir valores originales y derivados por lotes, con claves que incluyan fuente/versión, propiedad, profundidad, estadístico y versión de clasificación. Mantener la asociación con las coordenadas y filas originales.
- Separar descarga, muestreo y clasificación en el progreso. Calcular tasa y ETA con unidades claras y suficientes muestras, sin presentar el porcentaje de etapa como porcentaje exacto del tiempo restante.

**Entregable:** procesamiento local reutilizable; con caché completa y compatible, la repetición no debe descargar ni abrir rásteres para volver a obtener las mismas muestras.

### Etapa 5 — Gestionar caché y valores predeterminados

**Prioridad: alta. Dependencia: esquema versionado y política explícita.**

- Distinguir datos válidos, parciales, NoData y `fallback_default`. Un fallo de servicio no debe contarse como adquisición válida de suelo.
- Diseñar caducidad/reintento para fallos temporales y una migración compatible de registros antiguos. Cambiar cuándo se reutiliza un fallback puede modificar salidas: activar esta política por separado y registrar su efecto.
- Conservar las categorías predeterminadas actuales en el modo compatible. Mostrar su procedencia y cantidades en progreso/metadatos; cualquier modo que exija suelo real deberá ser configurable.
- Verificar invalidación al cambiar fuente, profundidad, estadístico, resolución o clasificación. No reutilizar sólo por coincidencia de coordenadas una muestra incompatible.

**Entregable:** caché recuperable y auditable, con cobertura real diferenciada de cobertura por valores predeterminados.

### Etapa 6 — Validar, medir y activar gradualmente

**Dependencia: etapas anteriores y fuentes disponibles para comparación.**

| Caso | Validación requerida |
| --- | --- |
| REST controlado frente al flujo optimizado de consultas | Mismos registros, categorías, fuentes y orden; sin pérdida ni duplicación de puntos bajo concurrencia. |
| REST válido frente a ráster equivalente | Comparar valores originales, unidades, profundidad, píxel y categorías. No usar fallbacks como prueba de igualdad de suelos reales. |
| Caché fría, parcial y caliente | Medir descarga, muestreo, clasificación, persistencia y tiempo total; verificar que sólo se resuelvan faltantes. |
| Cancelación y reinicio | Reutilizar lotes confirmados y completar los faltantes sin modificar entradas ni duplicar registros. |
| Servicio caído, respuesta inválida y ráster truncado | Diagnóstico explícito, reintentos limitados y conservación de la política de fallback seleccionada. |
| Pipeline completo con modelo fijo | Comparar workbook Phase03 y predicciones posteriores; preservar filas, columnas y orden. |

Usar tres tamaños: fixtures pequeños para igualdad, una grilla mediana para ajustar recursos y la grilla representativa de 128.544 puntos para evaluar escala. Medir caché fría de red por separado de archivos locales y de caché caliente. Registrar hardware, configuración y cobertura real; repetir las mediciones y reportar variación, sin prometer un factor de aceleración antes del benchmark.

**Criterios de aceptación:** ninguna diferencia no explicada con las mismas fuentes y reglas; memoria y trabajo pendiente acotados; recuperación de lotes confirmados; ausencia de solicitudes para datos ya válidos en caché; mejora reproducible del tiempo total sin degradar cobertura real; fallbacks identificados explícitamente. Si cambia la fuente de profundidad o la interpretación de datos, validar y aprobar ese cambio funcional por separado.

### Archivos previstos y orden de entrega

- `preprocess/soil_enrichment.py`: contrato de propiedades, validación de respuestas, proveedores, clasificación compartida y política de fallback.
- `ce_pipeline/phase03/script03.py`: cola acotada, separación de locks, planificación, procesamiento por bloques, persistencia incremental y progreso.
- `shared_cache.py`: consultas/escrituras por lotes, procedencia, versionado y migración compatible.
- Pruebas focalizadas nuevas de suelos y ampliación de `tests/test_shared_cache.py`: equivalencia, concurrencia, límites de píxel, NoData y recuperación.
- Un benchmark reproducible de suelos bajo `scripts/`, con cachés aisladas para no alterar las corridas de la aplicación.

Orden recomendado: **contrato y métricas → ejecución/caché incremental → piloto de descarga regional → muestreo por bloques → validación integral → activación gradual**. Mantener una opción de reversión al proveedor anterior. Después de cada cambio en el código, reiniciar la aplicación según la instrucción del usuario; hacer el piloto en una corrida controlada y coordinar las interrupciones de ejecuciones activas.

Este apartado documenta trabajo propuesto. Su incorporación no implementa las mejoras de suelos ni modifica la corrida actual.

## Plan transversal: progreso y registro de actividad en la UI

### Problema y objetivo

El usuario observó que la UI no mostró el porcentaje del cálculo de ventanas ni el avance de otros procesos intermedios hasta llegar al enriquecimiento de suelos. Instrumentar la ejecución completa para que siempre se pueda identificar la etapa actual, cuánto trabajo ha terminado y si la aplicación sigue activa. El nuevo proveedor regional de suelos deberá publicar su progreso desde su primera implementación.

Esta mejora debe acompañar las etapas de optimización anteriores: comenzar con el contrato de progreso y las métricas, completar la cobertura del flujo actual y ampliar la misma presentación al nuevo flujo. No requiere cambiar los cálculos climáticos, las ventanas de cinco años ni las reglas de predicción.

### Cobertura requerida por proceso

| Proceso | Información visible y unidad de avance |
| --- | --- |
| Lectura, validación y preparación de entrada | Etapa actual; filas o archivos procesados cuando exista un total conocido. |
| Expansión de grilla y planificación | Celdas/puntos preparados y consultas de caché completadas; indicar cuando todavía se está determinando el total. |
| Preparación de rásteres climáticos | Archivos revisados, disponibles en caché, descargados, pendientes y reintentados. |
| Muestreo y precomputación climática | Píxeles o series completadas sobre el total efectivo; distinguir reutilización de caché y procesamiento nuevo. |
| Cálculo de ventanas climáticas y referencias de cinco años | Series completadas sobre las requeridas y porcentaje de esta etapa; incluir ventanas terminadas si se instrumentan como unidad independiente. No confundir series con ventanas ni años. |
| Construcción y guardado de CSV, auditoría y workbook | Nombre comprensible del artefacto y filas escritas cuando sea medible. Durante una operación de escritura indivisible, mostrar actividad y tiempo transcurrido. |
| Planificación y caché de suelos | Puntos totales, puntos cubiertos por caché válida y pendientes; indicar el proveedor utilizado. |
| Descarga regional de suelos | Teselas o recortes completados sobre el total; bytes y tamaño total sólo cuando se conozcan. |
| Validación y muestreo de suelos | Archivos validados y puntos muestreados sobre sus respectivos totales. |
| Clasificación y persistencia de suelos | Puntos clasificados y guardados; datos reales, parciales, NoData y valores predeterminados separados. |
| Predicción y fases posteriores aplicables | Fase actual, lotes o filas terminadas cuando sea medible y preparación de los resultados finales. |
| Preparación del mapa y finalización | Validación de los resultados y preparación del mapa; publicar completado únicamente cuando los artefactos sean válidos y estén disponibles. |

### Trabajo de backend

1. Definir un contrato común con identificador de etapa, nombre, estado, mensaje, unidades completadas/totales, porcentaje de etapa, fecha de actualización y tiempo transcurrido. Conservar los campos actuales `status`, `percent`, `stage`, `message` y `details` para compatibilidad.
2. Separar el porcentaje de etapa del avance global. El porcentaje de etapa será `completadas / total` cuando el total sea conocido. Si se mantiene una barra global, documentar sus pesos y presentarla como avance aproximado del flujo, no como fracción exacta del tiempo restante.
3. Instrumentar inicio, avance y fin de cada proceso, especialmente la agregación de ventanas y la escritura de salidas entre clima y suelos. Contar aciertos de caché como trabajo resuelto y actualizar correctamente los totales al omitir tareas; evitar que una etapa completa quede en 99,9%.
4. Centralizar las actualizaciones en un coordinador para evitar que los workers sobrescriban una etapa nueva con mensajes atrasados. Añadir secuencia de actualización y escritura atómica de `progress.json`; mantener un snapshot coherente en la API de estado.
5. Publicar avances con frecuencia acotada, inicialmente cada 1–2 segundos, y una señal de actividad cada 5–10 segundos durante operaciones largas sin contador disponible. Medir el costo de instrumentación y evitar una escritura por punto o ventana.
6. Distinguir actividad reciente de avance medible. Si no llegan actualizaciones, informar el tiempo desde la última señal sin declarar automáticamente que el proceso falló o sigue avanzando. Registrar errores, reintentos, cancelación y recuperación con su etapa correspondiente.
7. Conservar un historial acotado de eventos por corrida, adicional al snapshot actual, para consultar las transiciones y recuperar la presentación después de recargar la página.

### Trabajo de UI

- Mostrar el nombre de la etapa, su porcentaje y un contador con unidad: por ejemplo, «Calculando ventanas climáticas · 62% · 6.200 de 10.000 series». Los números del ejemplo son ilustrativos.
- Mostrar duración, última actualización y, cuando la tasa sea estable, ETA de la etapa. Una ETA global sólo se ofrecerá si hay evidencia suficiente para las etapas restantes.
- Para tareas sin total medible, mostrar un indicador de actividad y una descripción concreta, como «Guardando el archivo de resultados». No inventar porcentajes para simular progreso.
- Añadir un registro de actividad compacto con hora, inicio/fin de etapa y avisos relevantes; mantener un número limitado de eventos y permitir consultar los anteriores. Evitar mensajes por cada punto y actualizaciones que bloqueen la interfaz.
- Mostrar errores de fuente y uso de valores predeterminados con cantidades claras. Una descarga fallida no debe aparecer como adquisición exitosa de suelo.
- Al pasar a la siguiente etapa, sustituir los contadores y la ETA anteriores. Tras recargar la página, recuperar la etapa vigente; ante cancelación o error, conservar el último estado y su explicación.

### Archivos, validación y aceptación

Ampliar `ce_pipeline/phase03/script03.py` y los ejecutores de las fases posteriores para emitir eventos; `preprocess/soil_enrichment.py` para reportar el nuevo flujo; `server.py` para entregar snapshots e historial coherentes; y `src/main.js` junto con el HTML/CSS correspondiente para presentar el progreso y la actividad. Reutilizar la consulta de estado existente, evitando mecanismos duplicados de seguimiento.

Validar con una corrida controlada que muestre todas las transiciones, una corrida con caché completa, operaciones largas de guardado, descargas fallidas, cancelación y recuperación tras recargar. Comprobar el contrato de progreso y su presentación, sin añadir pruebas que simplemente reproduzcan la implementación.

**Criterios de aceptación:** el cálculo de ventanas muestra porcentaje y contador propios; todas las etapas largas muestran avance o actividad reciente; el nuevo proceso regional de suelos reporta planificación, descarga, validación, muestreo, clasificación y persistencia; los porcentajes usan unidades consistentes; no aparecen contadores ni ETA de una etapa anterior; la UI permanece interactiva; y el 100% global coincide con resultados finales válidos. Medir que la instrumentación no introduzca una regresión relevante de rendimiento.

Este apartado amplía el plan de trabajo; todavía no implementa cambios en el backend ni en la UI.

## Primera entrega de suelos y progreso — 2026-10-05 UTC

Se inició la implementación con las mejoras de ejecución, recuperación y visibilidad del flujo existente:

- **Implementado:** las consultas de suelos usan payloads independientes; ningún bloqueo de caché abarca la espera de red. La cola mantiene como máximo dos tareas pendientes por worker, en lugar de enviar toda la grilla al executor.
- **Implementado:** lectura de puntos de suelo desde SQLite por lotes, sin abrir y recorrer el JSON legado por cada fallo de caché.
- **Implementado:** guardado incremental en SQLite cada 64 resultados nuevos o después de cinco segundos con resultados pendientes; vaciado del lote pendiente ante una excepción controlada y exportación final del JSON compatible. Una terminación abrupta puede perder resultados aún no confirmados, pero permite recuperar los lotes persistidos desde SQLite.
- **Implementado:** contadores incrementales de puntos y filas, porcentaje por etapa, cantidad de resultados predeterminados, puntos persistidos y tareas pendientes. Se conservan las categorías, coordenadas y reglas actuales de fallback.
- **Implementado:** límite de cinco solicitudes por minuto, dentro de cada proceso del pipeline, para `rest.isric.org`. El límite procede de la [política oficial de acceso de ISRIC](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_02.html). Los endpoints personalizados no reciben automáticamente ese límite. La coordinación de cuota entre varias corridas simultáneas sigue pendiente; el piloto REST debe usar una sola corrida activa.
- **Implementado:** progreso independiente para preparación de series diarias y cálculo de ventanas. Las ventanas se cuentan al terminar cada serie efectiva, incluidos aciertos de caché, y publican 100% de su etapa al completarse. Los hooks de muestreo no sobrescriben ese avance durante la agregación.
- **Implementado:** avisos antes de expandir la grilla, consultar caché, persistir características, construir filas y guardar CSV, auditoría, workbook climático, metadatos y workbook de clima/suelos.
- **Implementado:** snapshots de progreso escritos mediante renombrado atómico, señal de actividad cada cinco segundos durante la ejecución, historial de las últimas 30 etapas y recuperación del historial al reanudar un proceso.
- **Implementado:** la UI muestra porcentaje y contador de etapa cuando conoce el total, duración, última actividad, ETA de etapa cuando hay suficientes resultados, valores predeterminados de suelo, puntos persistidos e historial desplegable. Limpia los contadores/ETA al cambiar de etapa. La barra conserva el avance aproximado del flujo existente; no representa tiempo restante.

### Validación de esta entrega

Pasaron 47 pruebas focalizadas de suelos/progreso, regresión climática, lectura por bloques, caché compartida, pipeline de modelo y estado del servidor. Las pruebas nuevas verifican consultas concurrentes, cola acotada, conservación de filas/orden, persistencia antes de un fallo, aciertos de caché sin red, lectura de más de un lote SQLite, cuota REST con reloj simulado, snapshots legibles bajo concurrencia, heartbeat sin alterar contadores e historial recuperado.

La sintaxis del módulo JavaScript pasó la comprobación de Node en modo módulo. Una comprobación aislada de su presentación verificó contadores, cambios de etapa, eliminación de ETA anterior, historial y datos de suelo predeterminados; no sustituye una prueba visual en un navegador real.

El benchmark aislado usó 64 puntos, cuatro workers, una respuesta válida controlada y 10 ms de latencia simulada por consulta. No hizo solicitudes reales ni modificó las cachés de la aplicación:

| Caso | Tiempo | Consultas simuladas | Aciertos de caché |
| --- | ---: | ---: | ---: |
| Referencia con bloqueo alrededor de la consulta | 0.658 s | 64 | 0 |
| Cola acotada, caché fría | 0.179 s | 64 | 0 |
| Repetición con caché SQLite completa | 0.002 s | 0 | 64 |

No hubo diferencias en textura, profundidad categórica, procedencia ni clase USDA para los mismos datos controlados. La comparación fría mostró aproximadamente 3,68× de mejora en esta simulación. **No extrapolarla a la red real:** no ejercita la disponibilidad ni la cuota REST de ISRIC, y no constituye una validación integral de predicciones para la grilla grande.

### Alcance pendiente y aplicación a corridas

Quedan pendientes la validación de respuestas reales y propiedades/profundidades, el proveedor regional WCS/WebDAV, el muestreo de suelos por bloques, la política separada de caducidad de fallbacks y el benchmark completo con datos reales. Esta entrega conserva el proveedor REST; no resuelve por sí sola su indisponibilidad.

Se reinició el servidor después de los cambios de código, conservando el proceso de la corrida `20261004-172147-0b5d247d`. Esa corrida mantiene el código que ya había cargado: la optimización del backend se aplica a nuevas corridas. Al recargar la página, la UI puede mostrar los contadores de suelos que ya emite el proceso anterior, pero éste no genera el nuevo historial ni señales de actividad periódicas.

### Corrección del porcentaje total y diagnóstico de REST

En la corrida posterior `20261004-193604-c124c512`, el backend reportaba 94% de avance global, pero la UI reemplazaba ese indicador con el porcentaje de suelos. Se corrigió la presentación: el indicador principal conserva `Total 94%`, y el porcentaje de etapa aparece junto al contador de puntos. Los avances positivos menores de 0,1% se muestran con más precisión para evitar que se redondeen a cero. Se verificó el caso de 15/128.544 puntos: total 94% y etapa 0,012%.

La revisión confirmó cuatro workers y ocho tareas pendientes en esa corrida; el proveedor utilizado sigue siendo REST por punto, sin descarga de rásteres de suelo. En el snapshot posterior había 24 puntos procesados, cero respuestas exitosas y 24 valores predeterminados. El cuello de botella es la espera/cuota del servicio, no una lectura local de rásteres que pueda acelerarse aumentando workers. El siguiente cambio necesario para esa escala es el proveedor regional pendiente, con validación de propiedades y profundidad antes de activarlo. Se reinició el servidor tras la corrección de UI sin interrumpir esta corrida.

## Descarga regional de suelos implementada y habilitada — 2026-10-05 UTC

La aplicación local usa ahora `APP_PHASE03_SOIL_PROVIDER=rasters`. El proveedor REST queda disponible mediante configuración explícita, pero el flujo regional no lo utiliza como fallback cuando una descarga falla.

### Fuente, geometría y reglas conservadas

- Nuevo proveedor en `preprocess/soil_rasters.py`, conectado a `enrich_soils` de Phase03.
- Descarga mediante WCS 2.0.1 de `sand_0-5cm_mean`, `silt_0-5cm_mean` y `clay_0-5cm_mean`. Se conserva la primera profundidad de textura de la preferencia existente y el estadístico solicitado `mean`.
- Se verifican las descripciones de las tres capas y que compartan la misma grilla nativa de 250 m. Las fracciones se conservan en g/kg y se clasifican con las funciones actuales; no se usa el producto agregado de 5 km ni interpolación para reemplazar el píxel nativo. Referencias: [capas y unidades oficiales](https://docs.isric.org/globaldata/soilgrids/SoilGrids_faqs_01.html) y [acceso WCS](https://docs.isric.org/globaldata/soilgrids/wcs.html).
- Cada punto se transforma desde WGS84 a la proyección nativa Homolosine. Se agrupan los puntos en recortes alineados de 512 × 512 píxeles; sólo se solicitan los recortes que contienen puntos faltantes. Esto limita cada solicitud a aproximadamente 128 × 128 km y permite reutilizar archivos entre corridas.
- El GeoTIFF real de MapServer puede omitir el CRS y NoData. Antes de asignar el CRS declarado en WCS se comprueban transformación, resolución y dimensiones del recorte. Valores negativos, mayores de 1.000 g/kg, enmascarados o fracciones con suma cero se consideran sin dato; no se presentan como textura real.
- Las capas actuales de textura no aportan profundidad hasta roca. Se conserva una profundidad válida de la caché histórica cuando existe; de lo contrario se usa la categoría actual `100cm o mas`, con procedencia y contador de profundidad predeterminada explícitos. No se sustituye esa variable por el intervalo 0–5 cm de la capa de textura.

### Descarga, muestreo, caché y progreso

- Dos workers de descarga y cuatro de muestreo en la configuración local; ambas colas mantienen como máximo dos tareas pendientes por worker.
- Descarga a archivos temporales, límite de tamaño y hasta dos intentos; publicación mediante renombrado atómico después de decodificar y validar el TIFF completo. Un archivo inválido de caché se repara antes del muestreo.
- Muestreo local agrupado por bloque, con ventanas recortadas y tres capas abiertas por tarea. Se reutilizan las lecturas entre puntos cercanos y se conserva la asociación y el orden de las filas.
- Persistencia incremental de muestras clasificadas en SQLite por lotes de 512 puntos o cada cinco segundos con resultados pendientes. Las claves de puntos y directorios de archivos incluyen una firma de fuente, revisión, profundidad, estadístico, unidades y clasificación. No se reutilizan los antiguos `fallback_default` de REST como si fueran muestras de ráster válidas.
- Una caché completa de puntos evita tanto la red como las aperturas de ráster; una caché parcial reutiliza recortes y resuelve únicamente puntos faltantes. Las muestras NoData conservan su procedencia y no cuentan como textura válida.
- La UI reporta comprobación de caché, planificación de capas, descarga de archivos, muestreo por bloques, persistencia y finalización. Incluye cantidades descargadas/reutilizadas, puntos muestreados, workers y profundidades predeterminadas. El total global y el porcentaje de etapa permanecen separados.
- Se corrigió la cancelación de procesos recuperados tras reiniciar el servidor: el endpoint de cancelación también detecta el ejecutor del pipeline fuera del registro de `Popen` y marca su corrida como cancelada. La identificación verifica el ejecutable Python y el argumento exacto del script, evitando coincidencias por texto dentro de otros comandos.

Configuración local aplicada:

```dotenv
APP_PHASE03_SOIL_PROVIDER=rasters
APP_SOIL_DOWNLOAD_MAX_WORKERS=2
APP_PHASE03_SOIL_MAX_WORKERS=4
APP_SOIL_RASTER_TILE_PIXELS=512
APP_SOIL_DOWNLOAD_TIMEOUT_SECONDS=60
APP_SOIL_DATA_VERSION=soilgrids2-mean-v1
```

El endpoint configurable es `APP_SOIL_WCS_ENDPOINT`, cuyo valor por defecto es `https://maps.isric.org/mapserv`. La revisión `APP_SOIL_DATA_VERSION` es una revisión explícita de la caché de la aplicación, no una fecha de publicación certificada por ISRIC. Debe cambiarse al adoptar una actualización de mapas o reglas que requiera invalidación; no se afirma que WCS entregue una versión histórica fijada o que la aplicación detecte automáticamente toda actualización de mapas sin cambios de metadatos.

### Validación y corrida activa

Pasaron **59 pruebas focalizadas** incluyendo diez pruebas nuevas del proveedor regional: igualdad de categorías para fracciones conocidas, filas duplicadas/orden, descarga compartida, caché fría/parcial/caliente, cambio de revisión, NoData, conservación de profundidad histórica, archivo truncado, recorte desplazado, rechazo de grillas incompatibles y conexión con Phase03. Las dos pruebas adicionales de servidor cubren cancelación tras un reinicio e identificación de procesos.

También se ejecutó una prueba real aislada con dos puntos próximos a `(1.25, 32.5)`, tres recortes y ninguna llamada a REST. La primera pasada tomó **4,291 s**, produjo textura válida para ambos puntos y reutilizó las funciones actuales de clasificación. La segunda tomó **0,000307 s**, con dos aciertos de caché, cero descargas y cero aperturas/lecturas de ráster. La profundidad de ambos puntos permaneció predeterminada y así se reportó. Los artefactos de esta prueba están en `/tmp/soil-raster-live-smoke/`; estos tiempos no representan una estimación de la grilla completa ni una validación integral de predicciones downstream.

Se calculó el plan de la grilla actual: **128.544 puntos, 221 recortes espaciales y 663 archivos** para las tres propiedades, sin puntos fuera de la cobertura global. Se conservó el ID `20261004-193604-c124c512` y se reinició la corrida con sus mismos argumentos, entrada y cachés para aplicar el proveedor nuevo. El proceso anterior PID 40200 terminó antes de iniciar su reemplazo PID 41927; se verificó que sólo queda una corrida. Los detalles del reinicio quedan en `soil_provider_restart.json` dentro de esa corrida.

Queda por medir el tiempo total y la cobertura real de la grilla grande, y comparar sus salidas/modelo con las mismas fuentes regionales. La profundidad hasta roca sigue requiriendo una fuente compatible independiente; la implementación no inventa ese dato ni afirma que los anteriores resultados predeterminados sean equivalentes a las nuevas texturas reales.

### Porcentaje por etapa en la preparación y salida de predicción — 2026-10-04

Se añadieron contadores al flujo manual de predicción: normalización por pasos, estandarización y codificación por columnas, escritura de workbooks por filas o celdas, carga/preparación y combinación por operaciones completadas, inferencia por lotes de 4,096 filas y generación de GeoJSON por registros examinados (incluidos los que no tienen coordenadas válidas). Las lecturas indivisibles de pandas y las exportaciones CSV no simulan un avance temporal: el contador de operaciones cambia al finalizar la operación. El porcentaje del proceso se muestra separado del porcentaje global aproximado.

El historial conserva el último porcentaje y los contadores de cada etapa; una etapa que comunica el 100% queda terminada aunque aún no haya comenzado la siguiente. La UI utiliza el porcentaje explícito para no anunciar el 100% mientras se cierra el archivo Excel o se guarda el GeoJSON. Las exportaciones pandas conservan su formateador y motor Excel; la inferencia sin callback mantiene la ruta anterior, y con callback procesa los mismos datos por lotes sin alterar su orden.

La validación incluye equivalencia de normalización, valores/tipos/formatos Excel, orden y valores de inferencia, un subproceso real de predicción, preparación completa de phase04, recuento de filas GeoJSON con coordenadas inválidas y conservación del historial. Dos pruebas antiguas de selección del modelo dependen de archivos externos de `EA_merged` ausentes en este entorno y no pueden completarse aquí. Los resultados históricos anteriores a este cambio no contienen los nuevos contadores; los porcentajes adicionales se generan en las siguientes corridas.

La transición entre phase04 y phase05 también reporta `Checking selected identifier`, `Loading identifier restoration workbooks`, `Restoring selected identifier` y `Saving restored identifier workbook`, con contadores por pasos, archivos y celdas. Antes de cargar los datos completos se inspeccionan los encabezados: si el identificador no está en phase03 o ya existe en phase04, se omiten ambas lecturas completas y se conserva el archivo de salida sin modificaciones. La lectura pandas informa operaciones completadas (0/2, 1/2, 2/2), no un porcentaje ficticio de filas. Cinco pruebas adicionales cubren esos casos, alineación por `CE Row ID`, restauración por posición y conservación del archivo cuando no coinciden las filas.

### Auditoría de reportes del flujo por Farm — 2026-10-06

Se instrumentaron los procesos adicionales de esta ruta sin cambiar su selección por `Farm`: lectura y preparación de perfiles; agrupación de series climáticas; consulta y guardado de caché; construcción, indexación y unión de filas climáticas; CSV y auditoría; restauración del identificador; preparación y normalización para el modelo; países; inferencia; exportación de predicciones; agrupación por identificador; selección de la predicción representativa por celda; análisis y anotación de perfiles; ordenamiento de archivos cuando aplica; GeoJSON y resumen final. Las operaciones de lectura indivisibles reportan pasos y actividad; los bucles reportan filas, columnas o celdas. La escritura CSV por fragmentos conserva los mismos valores y formato.

El historial conserva hasta 200 etapas, en lugar de 30. El contador de codificación categórica se colocó en el bucle que genera los dummies; anteriormente empezaba en la preparación de columnas y podía dejar un registro duplicado al 0%. Se separaron las operaciones anidadas para cerrar sus contadores antes de cambiar de etapa.

Validación: 74 pruebas aplicables, más una prueba del renderizador de la UI con 45 etapas terminadas y una etapa activa. La integración Farm usa dos fincas y ejecuta la preparación de phase02, phase04, phase05 y la finalización, con adquisición climática e inferencia simuladas; verifica que todos los procesos ejecutados de ese caso aparezcan en el historial persistido y terminen con porcentaje 100, y conserva dos predicciones por finca y la celda representativa esperada. La preparación climática tiene comprobaciones independientes de sus agrupaciones, caché, construcción y unión de filas. No se ejecutó una validación completa adicional con los aproximadamente 11.6 millones de filas de la corrida activa: esa corrida conserva el código que cargó al iniciarse. No se reconstruyen contadores históricos que no fueron registrados.

### Corrección de Excel grandes en el flujo Farm — 2026-10-06

La corrida `20261006-190709-80710d7b` falló al cerrar el workbook de clima y suelos con `File size too large, try using force_zip64`, después de procesar 208,980 filas. Su hoja XML supera el límite ZIP utilizado por Python; como el tamaño no se conoce al iniciar la escritura por streaming, ahora se abre `xl/worksheets/sheet1.xml` con `force_zip64=True`. Se mantiene la estructura, el contenido y los contadores del workbook.

Una regresión reduce temporalmente `zipfile.ZIP64_LIMIT` a 2,048 bytes, reproduce exactamente el error anterior y comprueba que el Excel corregido cierre, pase la comprobación de integridad ZIP, conserve los valores y reporte el 100% después del cierre. Además, el historial mantiene una etapa incompleta como `error` cuando falla; la UI conserva su porcentaje y evita mostrarla como `finished`. Pasaron 76 pruebas aplicables y la comprobación del renderizador de actividad. La validación del límite se hizo con un archivo pequeño; no se repitió automáticamente la corrida completa que falló.
