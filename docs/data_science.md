# Validación de Data Science

Validación independiente de los KPIs del dashboard contra el kardex MB51
crudo, ejecutada por `agents/agent_ds.py` (recalcula desde la fuente sin usar
los módulos del pipeline). Evidencia: `reports/agentes/<timestamp>/revisor_ds.json`.
Fecha de la validación: 2026-07-06, rama `deploy-dashboard-chencopo`.

## Resultados de la conciliación (kardex ↔ pipeline)

| Verificación | Recalculado independiente | Pipeline | Desvío | Veredicto |
|---|---:|---:|---:|---|
| Filas en ventana de análisis | 42,900 | 42,900 (01_kardex) | 0.0000% | ✅ |
| Consumo neto alimento (261−262 WA, desde ancla MB5B 2024-07-06) | 795,890 kg | 795,890 kg (09_stock) | 0.0000% | ✅ |
| Entradas netas alimento (101−102 WE, desde ancla) | 832,190 kg | 832,190 kg (09_stock) | 0.0000% | ✅ |
| Producción (101 WF huevo + 531 WA subproducto) | 449,093 kg | 442,522 kg (06_diaria) | 98.54% asignada | ⚠ ver nota 1 |
| Mortalidad aves (261−262 WR, en ventana de ciclos) | 1,539 aves | 1,530 aves | 0.6% | ⚠ ver nota 1 |
| Consumo diario ↔ semanal | 795,490 kg | 795,490 kg | 0.0000% | ✅ |
| Producción diaria ↔ semanal | 442,521.85 kg | 442,521.85 kg | 0.0000% | ✅ |
| ICA semanal (258 semanas evaluables) | consumo_productivo/produccion_productiva | ica_real | desvío máx 0.0000 | ✅ |

**Nota 1 — brechas de asignación, no de conteo:** la línea diaria asigna
movimientos a *ciclos detectados*. La producción/mortalidad del kardex previa
al inicio de los ciclos analizados (preventana de 30 días y órdenes históricas)
existe en SAP pero no pertenece a ningún ciclo del análisis. No hay doble
conteo (pipeline ≤ kardex en ambos casos). Confirmar con negocio que el 1.46%
de producción no asignada corresponde a ciclos previos.

## Diccionario de KPIs principales

| KPI | Objetivo | Fórmula | Fuente | Llaves | Granularidad | Unidad | Filtros | Validación |
|---|---|---|---|---|---|---|---|---|
| Consumo neto | Alimento realmente consumido | `261 WA − 262 WA` | MB51 | centro+almacén+material+fecha(+orden) | diaria | kg | materiales de alimento, almacén único configurado | exacta vs kardex |
| Entradas netas | Alimento recibido | `101 WE − 102 WE` | MB51 | ídem | diaria | kg | ídem | exacta vs kardex |
| Stock global | Inventario del almacén de alimento | `ancla MB5B + Σ movimientos` | MB5B+MB51 | almacén global | diaria | kg | desde fecha de ancla | conciliación diaria en 09 (`diferencia_conciliacion_kg`) |
| Producción neta | Huevo producido | `101/102 WF (principal) + 531/532 WA (subproducto)` | MB51 | orden→ciclo | diaria | kg | materiales configurados | 98.54% asignada a ciclos |
| Mortalidad | Bajas de aves | `261 WR − 262 WR` (unidades) | MB51 | orden→ciclo | diaria | aves | material de aves | 0.6% desvío en ventana |
| ICA semanal | Eficiencia alimenticia | `consumo_productivo / produccion_productiva` | 06/07 | ciclo+semana de edad | semanal | kg/kg | semanas evaluables (`es_ica_evaluable`), excluye consumo preproductivo del arranque | reproducible en 258/258 semanas |
| Días de cobertura | Autonomía de alimento | `stock / consumo_diario_estimado(7d)` | 09+12 | almacén global y material | diaria | días | consumo estimado > 0; NaN sin historia | pruebas unitarias con casos borde |
| Score de anomalía | Priorización de revisión | `0.65·reglas + 0.35·IsolationForest` | 10_features | ciclo+fecha | diaria | 0–100 | filas elegibles | contrato protegido por pruebas |

**Supuestos y limitaciones**: umbrales de cobertura provisionales
(`docs/PREGUNTAS_PENDIENTES.md`); el estándar corporativo depende de la
política cargada; los modelos sombra (IF/LOF por edad) son evidencia
comparativa y no promueven alertas.

## Riesgos evaluados

- **Doble conteo**: descartado en consumo/entradas/producción (conciliación exacta o pipeline ≤ kardex).
- **Pérdida de registros**: la ingesta descarta solo filas sin fecha válida y lo reporta; llave de negocio + ocurrencia conserva duplicados legítimos.
- **Mezcla de periodos**: agregaciones semanales conservan el total diario (0.0000%).
- **Mezcla de centros/almacenes**: alcance limitado a un centro con almacén único de alimento (validado en la ingesta).
- **Fuga de información (modelo)**: features móviles usan `shift(1)` (solo historia previa); el modo `score_existing` separa entrenamiento de scoring.

## Falsos positivos del propio validador (corregidos)

La primera corrida del agente reportó 3 desvíos que resultaron ser errores del
*validador*, no del pipeline (ver `docs/agentes_evaluacion.md`): ventana del
stock (ancla MB5B vs preventana), ventana de mortalidad e ICA con fórmula no
productiva. Quedaron corregidos en `agents/agent_ds.py` y documentados como
tasa de falsos positivos de la primera iteración.
