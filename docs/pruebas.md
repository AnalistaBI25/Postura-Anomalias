# Pruebas

## Suite automatizada

```powershell
pytest            # 107 pruebas (exit 0 verificado 2026-07-06)
```

| Área | Archivo | Qué protege |
|---|---|---|
| Ingesta incremental | `tests/test_ingestion.py` | detección de fuente/granularidad, validación (extensión, vacío, columnas, reporte mensual no soportado), idempotencia por hash, traslapes (solo nuevos), duplicados legítimos (ocurrencia), rechazo registrado, cache compatible con `normalize_kardex` |
| Cobertura de alimento | `tests/test_coverage.py` | días de cobertura, exceso, consumo cero (sin división), historia insuficiente, eventos sobrestock/desabasto crítico/inventario cero con aves/stock negativo (calidad)/sin movimiento |
| Alertas y consenso | `tests/test_alerts.py` | capas 1–4, `CALIDAD_DE_DATOS` vs operativa, severidad que no degrada la oficial, construcción canónica, ciclo de vida (nueva→persistente→resuelta→reabierta), cambio de severidad, revisión manual persistida |
| Modelo | `tests/test_model_lifecycle.py`, `tests/test_shadow_models.py` | modo train/score_existing, metadata versionada, `MODEL_MISSING` sin entrenamiento silencioso; los modelos sombra no promueven alertas |
| Reglas de negocio | `tests/test_business_rules.py`, `test_standard.py`, `test_productivity.py`, `test_daily.py`, `test_stock.py`, `test_utils.py` | clasificación 261/262, política por edad, stock, fórmulas |
| Dashboard | `tests/test_dashboard_payload.py`, `test_dashboard_frontend_refactor.py`, `test_dashboard_groups.py`, `test_dashboard_group_ui.py` | contrato del payload, refactor del frontend, agrupación de ciclos |

## Validadores de artefactos

```powershell
python scripts/validar_dashboard_payload.py   # OK (exit 0)
python scripts/validar_dashboard_html.py      # OK (exit 0)
python scripts/validate_input.py --input archivo.xlsx
```

## Validación analítica independiente

`python -m agents.orquestador` (agente `revisor_ds`): conciliación completa
kardex ↔ pipeline ↔ payload con resultados en `docs/data_science.md`.

## Matriz de archivos de entrada (§ pruebas con diferentes archivos)

| Caso | Cobertura | Dónde |
|---|---|---|
| Válido actual / pequeño / grande | ✅ real + sintético 10x | e2e + benchmarks |
| Un día / semanal / mensual / varios meses | ✅ | `analizar_granularidad` tests |
| Traslape / duplicado / vacío / sin fechas / fechas futuras | ✅ | test_ingestion |
| Columnas faltantes / renombradas (alias cortos SAP) / extra | ✅ | detección de fuente + aliases |
| Cantidades nulas / negativas / no clasificados | ✅ | quality + coverage + alerts |
| Hoja incorrecta / archivo dañado / reporte mensual | ✅ | validación (rechazo con motivo) |
| Centros/almacenes/materiales nuevos, unidades distintas | ⚠ requiere archivos reales de otras granjas | documentado en limitaciones |

## Regresión

Tras las correcciones de esta revisión (`.streamlit/config.toml`, agentes),
la suite completa se reejecutó: **107 pruebas, 0 fallos** — sin regresiones.
El score oficial (65/35) y sus umbrales no fueron modificados.
