# Operacion: carga incremental desde el dashboard y por CLI

## Flujo general

```text
Usuario exporta MB51 desde SAP
  -> abre la app Streamlit
  -> sube un solo archivo MB51
  -> Python valida estructura, fuente, fechas, duplicados y traslapes
  -> SQLite registra carga y movimientos nuevos
  -> el pipeline recalcula indicadores, 4 capas, alertas y dashboard
  -> el modelo oficial se usa en modo scoring productivo si existe artefacto activo
  -> el panel operativo permite revisar alertas sin borrar datos
```

## Reglas del modulo de carga

- **Formato soportado:** exportacion directa de MB51 (`.xlsx`, `.xls` o `.csv`) con columnas SAP esperadas.
- **Un archivo por carga web:** la app publicada procesa solo el primer MB51 seleccionado.
- **Maestros fuera del upload web:** estandar, organizacion y MB5B se gestionan por rutas de `config/project.yml`.
- **Rechazo explicito:** reportes mensuales por granja, columnas faltantes, archivos vacios o fuentes no reconocidas se rechazan con motivo.
- **Idempotencia:** recargar el mismo archivo o un periodo traslapado no duplica movimientos.
- **Raw inmutable:** los archivos validos quedan archivados y los rechazados quedan en carpeta de rechazo con registro.

## Modelo y scoring

La carga productiva no reentrena el modelo. La configuracion recomendada es:

```yaml
model_lifecycle:
  mode: score_existing
  active_model_path: models/isolation_forest_consumo.joblib
  metadata_path: models/isolation_forest_metadata.json
```

Si el modelo activo no existe, el sistema registra `MODEL_MISSING` y no entrena en silencio. El entrenamiento manual se ejecuta con:

```powershell
python scripts/train_model.py
```

## CRUD operativo

| Operacion | Entidad | Comportamiento |
|---|---|---|
| Crear | carga MB51 | registra metadata, hash y movimientos nuevos |
| Crear | revision experta | guarda estado, usuario y comentario |
| Leer | cargas, alertas, modelo | se muestra en panel operativo y exports |
| Actualizar | revision experta | reemplaza estado vigente y crea evento de auditoria |
| Eliminar | alerta revisada | se representa como `DESCARTADA`; no hay borrado fisico |

## CLI equivalente

```powershell
# Validar un archivo sin cargarlo
python scripts/validate_input.py --input "nuevo_mb51.xlsx"

# Primera vez: cargar historico configurado
python scripts/run_incremental.py --bootstrap

# Carga incremental + pipeline completo
python scripts/run_incremental.py --input "nuevo_mb51.xlsx"

# Solo ingesta, sin recalcular
python scripts/run_incremental.py --input "nuevo_mb51.xlsx" --sin-pipeline

# Reprocesar con lo ya cargado
python scripts/run_incremental.py --solo-pipeline

# Entrenar modelo de forma controlada
python scripts/train_model.py
```

## Artefactos operativos

| Artefacto | Ubicacion |
|---|---|
| Registro de cargas | `data/warehouse.db` tabla `cargas`; `outputs/latest/file_load_registry.csv` |
| Movimientos deduplicados | `data/warehouse.db` tabla `movimientos` |
| Alertas consolidadas | `data/processed/13_alertas_consolidadas.csv`; `outputs/latest/consolidated_alerts.csv` |
| Historial de alertas | `data/warehouse.db` tabla `alertas`; `outputs/latest/alert_history.csv` |
| Revision vigente | `data/warehouse.db` tabla `alertas_revision`; `outputs/latest/alert_reviews.csv` |
| Auditoria de revision | `data/warehouse.db` tabla `alertas_revision_eventos`; `outputs/latest/alert_review_audit.csv` |
| Metricas operativas | `outputs/latest/operational_metrics.json` |
| Dashboard | `reports/dashboard.html` |

## Metodologia de 4 capas

| Capa | Pregunta | Implementacion |
|---|---|---|
| 1. Calidad | El dato es valido y conciliable? | consumo negativo, sin orden, orden fuera de maestro, diferencia de stock |
| 2. Estadistica robusta | Es extremo contra su historial? | z robusto y cambio abrupto |
| 3. Contextual | Es raro para edad, fase o operacion? | brecha contra politica, consumo cero con aves, mortalidad alta, fase multiple |
| 4. Multivariada | La combinacion es inusual? | Isolation Forest oficial |

Los modelos sombra por edad aportan evidencia, pero no sustituyen el score oficial.
