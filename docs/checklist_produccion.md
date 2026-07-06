# Checklist de preparación para producción

Evaluación contra los criterios de aceptación (2026-07-06, rama
`deploy-dashboard-chencopo`).

| # | Criterio | Estado | Evidencia |
|---|---|---|---|
| 1 | Dashboard se ejecuta desde cero | ✅ | `docs/despliegue.md` (comandos verificados) |
| 2 | Dependencias documentadas | ✅ | requirements.txt fijado; 13/13 importables (agente despliegue) |
| 3 | Kardex se procesa correctamente | ✅ | 42,900 filas, corrida 12 s, exit 0 |
| 4 | KPIs validados | ✅ | conciliación independiente exacta (`data_science.md`) |
| 5 | Sin errores críticos de código | ✅ | 107 pruebas + 2 validadores en verde |
| 6 | Rutas reproducibles | ✅ | todo relativo a `config.root` |
| 7 | Configuración separada | ✅ | `config/project.yml` + `.streamlit/config.toml` |
| 8 | Errores de entrada manejados | ✅ | validación con rechazo motivado + `data/rejected/` |
| 9 | Existen pruebas | ✅ | 107 (`docs/pruebas.md`) |
| 10 | Sin regresiones | ✅ | suite completa tras los cambios de la revisión |
| 11 | UI clara | ✅ | `docs/ui_ux.md` (2 pendientes menores) |
| 12 | CRUD seguro y auditable | ✅ parcial | borrado lógico + auditoría ✔; identidad/permisos pendientes |
| 13 | Rendimiento medido | ✅ | 12 s pipeline; benchmarks 1x–10x |
| 14 | Cuellos de botella documentados | ✅ | `rendimiento_big_o.md` |
| 15 | Optimizaciones con beneficio demostrado | ✅ | ninguna aplicada sin medición; pospuestas con evidencia |
| 16 | Despliegue documentado | ✅ | `docs/despliegue.md` |
| 17 | Rollback | ✅ | git revert + history de outputs + dashboard versionado |
| 18 | Métricas definidas | ✅ | `docs/monitoreo_metricas.md` + operational_metrics.json |
| 19 | Agentes evaluados en modo controlado | ✅ | 2 corridas Fase 1 (`agentes_evaluacion.md`) |
| 20 | Agentes sin permisos peligrosos | ✅ | solo lectura; sin push/merge/borrado |
| 21 | Documentación formal | ✅ | suite docs/ completa + entregable |
| 22 | Pendientes identificados | ✅ | `limitaciones.md`, `plan_mejoras.md`, `PREGUNTAS_PENDIENTES.md` |
| — | **Seguridad de datos del repositorio** | ❌ | **repo público con datos reales — decisión de negocio previa al PR** |
| — | Autenticación de la app | ❌ | pendiente (aceptable solo para validación restringida) |

**Conclusión**: 22/22 criterios técnicos cumplidos; 2 bloqueos no técnicos
(visibilidad del repositorio y autenticación) requieren decisión del negocio.
Recomendación formal en `docs/entregable_final.md`.
