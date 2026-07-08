## Agro Predict Map

Repositorio saneado para compartir en GitHub.

Incluye:

- código de la app en la raíz del repo
- frontend, backend y pipelines
- recursos de código vendorizados necesarios como `resources/featurehero` y `resources/phen_transform_dataset`
- datos estáticos ligeros para el mapa

Se excluyeron de esta copia:

- archivos `.env`
- archivos `.xlsx`
- artefactos entrenados `.pkl`
- salidas generadas de `pipeline/runs/`
- modelos registrados en `pipeline/model/20*/` y `ce_pipeline/model/`
- plantillas y archivos fuente de trabajo
- entornos virtuales vendorizados
- documentos auxiliares no necesarios para ejecutar el código
- `data/phase1_points.geojson`

Notas:

- algunas pruebas del proyecto original esperaban workbooks de prueba que no se copiaron
- el flujo de predicción que depende de artefactos de modelo entrenado requerirá volver a generar o volver a agregar esos artefactos de forma explícita
- esta copia deja los archivos directamente en la raíz del repo destino
