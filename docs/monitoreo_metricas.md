# Monitoreo y métricas de seguimiento

Fuente automática por corrida: `outputs/latest/operational_metrics.json` y
`outputs/latest/execution_manifest.json` (copiados a
`outputs/history/AAAA/MM/run_<id>/`). Registro vivo en `data/warehouse.db`.

## Métricas técnicas

| Métrica | Fuente | Frecuencia | Umbral inicial | Acción correctiva |
|---|---|---|---|---|
| Duración del pipeline | manifest / log | por corrida | > 120 s | revisar etapa dominante (`rendimiento_big_o.md`) |
| Resultado de la ejecución | tabla `ejecuciones` | por corrida | resultado ≠ OK | revisar `logs/pipeline.log` |
| Errores/rechazos de carga | tabla `cargas` | por carga | > 20% rechazadas/semana | revisar variante de exportación SAP |
| Pruebas | pytest en local/agentes | por cambio | cualquier fallo | bloquear el cambio |

## Métricas de datos

| Métrica | Fuente | Umbral inicial | Acción |
|---|---|---|---|
| Registros nuevos por carga | `cargas.n_insertados` | 0 en carga esperada | confirmar exportación/traslape |
| Duplicados omitidos | `cargas.n_omitidos_duplicados` | 100% del archivo | archivo repetido: informar al usuario |
| Frescura (última fecha de datos) | `movimientos.max(fecha)` | > 3 días de rezago | solicitar exportación |
| Movimientos no clasificados | `reports/tables/03_*.csv` | > 0 | validar con negocio antes de reglas |
| Nulos en llaves | agente de datos | > 1% | revisar exportación |
| Diferencia de conciliación de stock | `09_*.csv` | > 1 kg sostenido | revisar ancla MB5B/movimientos |

## Métricas funcionales y de alertas

| Métrica | Fuente | Umbral inicial | Acción |
|---|---|---|---|
| Alertas por severidad/familia | `operational_metrics.json` | crítica > 0 | revisión el mismo día |
| Alertas persistentes | estado `persistente` | ≥ 3 corridas | escalar a responsable |
| Revisiones registradas | `alertas_revision` | 0 revisiones/semana con alertas activas | recordar al revisor |
| Falsos positivos confirmados | revisiones `FALSO_POSITIVO` | > 30% | recalibrar umbrales/pesos |

## Métricas del sistema de agentes

Definidas y medidas en `docs/agentes_evaluacion.md` (hallazgos confirmados,
falsos positivos, consistencia, recomendaciones aplicadas/rechazadas,
regresiones=0, costo).

## Responsable y cadencia

- Cadencia de revisión sugerida: semanal (o con cada carga).
- Responsable: analista de BI (usuario del dashboard); los umbrales viven en
  este documento y en `config/project.yml` — ajustarlos requiere commit
  (queda trazado en git).
