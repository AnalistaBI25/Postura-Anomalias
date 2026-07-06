# Operación: carga incremental desde el dashboard y por CLI

## Flujo general

```text
Usuario consulta MB51 en SAP y exporta (misma variante que el kardex del proyecto)
        ↓
Abre la app:  streamlit run streamlit_app.py  →  pestaña "📤 Carga SAP"
        ↓
Arrastra uno o varios archivos (.xlsx/.xls/.csv)
        ↓
El sistema valida: extensión, hoja, columnas, fechas, granularidad,
duplicado exacto (hash) y traslape con lo ya cargado
        ↓
Revisa el resumen y la vista previa → Confirmar carga
        ↓
Ingesta idempotente a SQLite (solo registros nuevos)
        ↓
(Opcional, activado por defecto) pipeline completo: indicadores, ICA,
cobertura, 4 capas, alertas y dashboard actualizado
        ↓
Trazabilidad en outputs/latest, outputs/history y data/warehouse.db
```

## Reglas del módulo de carga

- **Formato soportado**: exportación directa de MB51 (hoja `Data`, columnas
  como en `docs/EXTRACCION_DATOS_SAP.md`). También se registran como
  *maestros* el estándar, la organización y MB5B, pero no generan movimientos:
  para usarlos hay que sustituir el archivo configurado en `config/project.yml`.
- **Los libros de trabajo mensuales por granja** (hojas 1..31, Mortalidad,
  Prod. huevo) **se rechazan**: no son exportaciones directas de SAP.
- **Los archivos crudos nunca se modifican**: cada carga válida deja copia
  inmutable en `data/raw/cargas/<id>_<nombre>`; los rechazados van a
  `data/rejected/` con su motivo en el registro.
- **Idempotencia**: recargar el mismo archivo (hash idéntico) o un periodo
  traslapado no duplica movimientos; la llave de negocio es
  `centro + almacén + material + fecha + clase movimiento + evento +
  indicador D/H + documento + posición + ejercicio + orden + lote + cantidad`
  más un contador de ocurrencia para movimientos legítimamente idénticos.
- **Granularidad**: se detecta del contenido (diaria/semanal/mensual/irregular),
  junto con rango real, días faltantes, semanas/meses incluidos y fechas
  futuras. El detalle diario se conserva; las agregaciones se derivan.
- **Alcance**: granjas con un único almacén de alimento (multi-caseta sí,
  multialmacén no, por ahora).

## CLI equivalente (automatización)

```powershell
# Validar un archivo sin cargarlo
python scripts/validate_input.py --input "nuevo_mb51.xlsx"

# Primera vez: cargar el histórico configurado
python scripts/run_incremental.py --bootstrap

# Carga incremental (uno o varios archivos) + pipeline completo
python scripts/run_incremental.py --input "nuevo_mb51.xlsx"

# Solo ingesta, sin recalcular
python scripts/run_incremental.py --input "nuevo_mb51.xlsx" --sin-pipeline

# Reprocesar con lo ya cargado
python scripts/run_incremental.py --solo-pipeline

# Pipeline clásico (lee el cache/kardex configurado, sin ingesta)
python -m granjas_anomalias.cli run --config config/project.yml
```

## Dónde queda cada cosa

| Artefacto | Ubicación |
|---|---|
| Registro de cargas (metadatos, hash, estado, motivo de rechazo) | `data/warehouse.db` → tabla `cargas`; export en `outputs/latest/file_load_registry.csv` |
| Movimientos históricos deduplicados | `data/warehouse.db` → tabla `movimientos` |
| Copias inmutables de archivos válidos | `data/raw/cargas/` |
| Archivos rechazados | `data/rejected/` |
| Cobertura de alimento diaria | `data/processed/12_cobertura_alimento_diaria.csv` y `outputs/latest/inventory_coverage.csv` |
| Alertas consolidadas de la corrida | `data/processed/13_alertas_consolidadas.csv` y `outputs/latest/consolidated_alerts.csv` |
| Alertas por familia | `outputs/latest/{overstock,shortage,consumption,production,ica,quality}_alerts.csv` |
| Historial completo de alertas | `data/warehouse.db` → tabla `alertas`; `outputs/latest/alert_history.csv` |
| Revisiones manuales | `data/warehouse.db` → tabla `alertas_revision` |
| Datasets del dashboard | `outputs/dashboard/` |
| Trazabilidad por ejecución | `outputs/history/AAAA/MM/run_<id>/` |

## Metodología de 4 capas (adaptación avícola)

| Capa | Pregunta | Implementación |
|---|---|---|
| 1 · Calidad | ¿El dato es válido y conciliable? | Consumo negativo, sin orden, orden fuera de maestro, diferencia de conciliación de stock, stock negativo, consumo mayor al disponible. Se etiqueta `CALIDAD_DE_DATOS`, no como problema productivo. |
| 2 · Estadística robusta | ¿Es extremo vs su propio historial? | Z robusto (mediana/MAD, ventana 28d) y cambio diario abrupto por ciclo. |
| 3 · Contextual | ¿Es raro para esta caseta/edad/etapa? | Brecha contra el estándar por edad, consumo cero con aves, mortalidad alta, fases simultáneas, producción baja/cero, ICA semanal fuera de estándar, cobertura fuera de umbrales. |
| 4 · Multivariada | ¿La combinación es inusual? | Isolation Forest oficial (score 65/35 intacto). Los modelos sombra (IF/LOF por edad) solo aportan evidencia, no promueven alertas. |

**Consenso y severidad**: cada día-ciclo registra qué capas se activaron
(`capas_activas`, `n_capas`). La severidad de consenso sube con el número de
capas (≥3 → crítica, 2 → alta) y **nunca degrada** la severidad oficial del
score. Un hallazgo solo de Capa 1 se reporta como `CALIDAD_DE_DATOS`.

**Ciclo de vida** (comparación entre corridas por `clave_seguimiento`):
`nueva` → `persistente` (sigue activa) → `resuelta` (dejó de aparecer) →
`reabierta`/`recurrente` (reaparece), con `cambio_severidad` = subió/bajó.
La revisión manual (CONFIRMADA / FALSO_POSITIVO / PROBLEMA_DE_DATOS) vive en
la pestaña "🚨 Alertas" y persiste entre corridas.
