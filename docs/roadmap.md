# Roadmap

| Fase | Objetivo | Estado | Entregables | Dependencias | Riesgos | Criterios de cierre |
|---|---|---|---|---|---|---|
| Fase 1 | Plataforma BI, ETL, indicadores, inventario, dashboard, reglas y baseline inicial | Completada | Pipeline, datasets procesados, reportes, dashboard, reglas, Isolation Forest baseline, tests | Fuentes SAP y configuración local | Calidad de fuente, combinaciones SAP nuevas, publicación accidental de payload | Pipeline ejecuta, pruebas pasan, dashboard valida, artefactos protegidos |
| Fase 2 | Investigación no supervisada y selección de modelo | Pendiente | Notebook, comparación de modelos, top-N para revisión, criterios de selección | Fase 1 estable, features, expertos disponibles | Sin etiquetas, fuga temporal, baja explicabilidad, exceso de alertas | Modelo candidato seleccionado o descarte justificado con revisión experta |
| Fase 3 | MLOps y despliegue | Futura | Entrenamiento versionado, scoring, monitoreo, drift, retroalimentación, rollback | Fase 2 cerrada, gobierno de datos, ambiente productivo | Deriva, cambios operativos, deuda de monitoreo, controles de acceso | Scoring reproducible, modelo versionado, monitoreo activo y runbook productivo |

## Dependencias entre fases

- Fase 2 depende de la estabilidad de las salidas de Fase 1.
- Fase 3 depende de un candidato validado en Fase 2.
- La retroalimentación humana de Fase 3 puede crear etiquetas para una futura etapa supervisada.
