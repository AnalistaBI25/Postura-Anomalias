# Arquitectura del sistema de agentes

Prototipo funcional en `agents/` (Fase 1: **solo lectura**). Ejecutar:

```powershell
python -m agents.orquestador            # todos los agentes
python -m agents.orquestador --skip pruebas rendimiento   # subconjunto
```

Salida por corrida: `reports/agentes/<timestamp>/` con un JSON por agente,
`hallazgos_consolidados.json` y `resumen.md`.

## Agentes implementados

| Agente | Módulo | Objetivo limitado | Entradas | Salida |
|---|---|---|---|---|
| Orquestador | `orquestador.py` | orden, consolidación, contradicciones, reporte | reportes de agentes | JSON+MD consolidado |
| Revisor Git | `agent_git.py` | rama, estado, sincronía, archivos sensibles/artefactos versionados | `git` (lectura) | hallazgos |
| Revisor de datos | `agent_datos.py` | nulos, duplicados, fechas, no clasificados, estado del warehouse | kardex cache, SQLite, tablas de calidad | hallazgos |
| Revisor DS | `agent_ds.py` | recálculo independiente de KPIs vs pipeline y payload | kardex, processed/, payload debug | hallazgos + métricas de conciliación |
| Revisor rendimiento | `agent_rendimiento.py` | etapas del log, benchmarks 1x–10x, memoria, SQLite | log + datos sintéticos | hallazgos + mediciones |
| Revisor seguridad | `agent_seguridad.py` | visibilidad del repo, secretos, superficie de la app, CRUD/auditoría | git, código fuente | hallazgos |
| Ejecutor de pruebas | `agent_pruebas.py` | pytest + validadores del dashboard | suite existente | hallazgos + conteos |
| Revisor despliegue | `agent_despliegue.py` | dependencias, arranque, config Streamlit, rollback, persistencia | requirements, filesystem | hallazgos |
| Revisor documental | `agent_documental.py` | inventario de documentos requeridos y equivalencias | docs/ | hallazgos |

## Reglas de operación (aplicadas en código)

- Formato de hallazgo estándar (`agents/base.py::Finding`): agent, finding_id,
  severity, category, file, component, evidence, impact, recommendation,
  `requires_business_validation`, confidence, status — igual al contrato
  definido para el proyecto.
- Cada ejecución registra inicio, duración, resultado y errores sin ocultarlos
  (un agente que truena reporta su traceback en su JSON).
- Los agentes **no** modifican código ni datos, **no** hacen push/merge, **no**
  despliegan, **no** tocan secretos y **no** aprueban resultados: emiten
  recomendaciones con confianza declarada; las dudas de negocio se marcan con
  `requires_business_validation: true`.
- Reproducibles: mismas entradas → mismos hallazgos (los benchmarks usan
  semilla fija).

## Fases de autonomía

| Fase | Estado | Alcance |
|---|---|---|
| 1 · Solo lectura | ✅ implementada y evaluada (2 corridas) | inspección, pruebas, evidencia, recomendación |
| 2 · Propuesta de parches | ⏳ siguiente | generar diffs sin aplicarlos, esperando aprobación humana |
| 3 · Cambios controlados | ⛔ no habilitada | solo cambios pequeños/reversibles/cubiertos por pruebas y preaprobados |
| 4 · Evaluación continua | en curso | métricas de `docs/agentes_evaluacion.md` deciden si se avanza |

**Criterio para avanzar de fase**: ≥2 corridas consecutivas sin falsos
positivos high/critical y confirmación humana de utilidad (ver métricas).
