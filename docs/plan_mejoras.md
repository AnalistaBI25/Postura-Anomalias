# Plan de mejora priorizado

Derivado de los hallazgos de la revisión predeploy (agentes + revisión humana,
2026-07-06). Ningún hallazgo de cálculo quedó abierto: la conciliación de KPIs
cerró exacta (ver `data_science.md`).

## Críticos (resolver antes del merge a main)

| ID | Problema | Evidencia | Solución | Riesgo si se pospone | Estado |
|---|---|---|---|---|---|
| SEC-001 | Repo público con `config/project.yml` real + dashboard con payload real | agente seguridad, HTTP 200 | Hacer el repo privado (opción recomendada) o limpiar índice+historial | Exposición de datos internos | **decisión de negocio pendiente** |

## Altos

| ID | Problema | Solución | Complejidad | Estado |
|---|---|---|---|---|
| SEC-002 | App sin autenticación (carga+revisión abiertas a quien tenga la URL) | Token simple vía `st.secrets` que condicione los eventos del shell | baja | pendiente (requiere decidir mecanismo) |

## Medios

| ID | Problema | Solución | Estado |
|---|---|---|---|
| OPS-001 | Persistencia efímera en Streamlit Cloud | Documentado; para operación real: servidor propio/volumen | documentado en `despliegue.md` |
| GIT-001 | `outputs/*.json` versionados (rutas locales, ruido de diff) | `.gitignore` + `git rm --cached outputs/` | propuesta (tocar el índice es decisión del dueño de la rama) |
| DAT-001 | 9 movimientos con almacén nulo | Confirmar con SAP si es esperable en la variante | pendiente negocio |
| DS-001 | 1.46% producción / mortalidad fuera de ciclos detectados | Confirmar que corresponde a ciclos previos al análisis | pendiente negocio |

## Bajos

| ID | Problema | Solución | Big O actual → propuesto | Estado |
|---|---|---|---|---|
| PERF-001 | Recalculo completo por corrida | Recomputo de ciclos activos cuando la corrida supere ~2 min | O(historial) → O(activos) | aceptado por ahora (12 s) |
| PERF-002 | `_ops_status` lee todas las alertas por rerun | Filtro SQL por última corrida | O(total) → O(última corrida) | aceptado (volumen mínimo) |
| SEC-003 | Traceback expuesto al frontend en error de carga | Log interno + mensaje genérico | — | propuesta de parche lista |
| SEC-004 | Usuario de revisión como texto libre | Ligar a autenticación (depende de SEC-002) | — | pendiente |
| QA-001 | DeprecationWarnings de pandas/numpy (timedelta) | Seguimiento al actualizar pandas/numpy; no afecta resultados | — | monitorear |

## Reglas de priorización aplicadas

Corrección y seguridad por encima de optimización: no hay optimizaciones
pendientes por delante de SEC-001/SEC-002. Las optimizaciones PERF-* están
respaldadas por mediciones y explícitamente pospuestas por no ser cuello real
(pipeline completo: 12 s).
