# Entregable final — Revisión predeploy del dashboard Chencopo

| | |
|---|---|
| **Proyecto** | BI de anomalías de consumo avícola (Postura) |
| **Rama evaluada** | `deploy-dashboard-chencopo` |
| **Fecha** | 2026-07-06 |
| **Método** | Revisión humana + sistema de agentes de solo lectura (`agents/`) |
| **Recomendación** | **LISTO PARA PR CON OBSERVACIONES** (ver §28) |

## 1–4. Objetivo, alcance y contexto

Determinar si el dashboard de Chencopo es apto para producción y reproducible
desde ambiente limpio, cubriendo Data Science, ingeniería de datos, UI/UX,
CRUD, seguridad, rendimiento/Big O, escalabilidad, despliegue, monitoreo,
documentación y un sistema controlado de agentes. La rama contiene los
cambios manuales del usuario para el despliegue en Streamlit Cloud más la
plataforma de ingesta incremental/alertas desarrollada previamente. Alcance de
datos: kardex MB51 real (46,755 movimientos, 2024-01→2026-06); las demás
fuentes quedan preparadas como punto de integración sin inventar reglas.

## 5. Estado inicial

Rama limpia y sincronizada con origin, 13 commits sobre `main`, 47 archivos
cambiados (+18,090/−3,790). Pipeline funcional de 11+2 etapas, 107 pruebas en
verde, dashboard HTML autocontenido, app Streamlit como host invisible de un
shell HTML/JS.

## 6. Cambios manuales identificados y veredicto

| Cambio | Propósito | Prueba | Veredicto |
|---|---|---|---|
| `streamlit_app.py` reescrito como host invisible + componente `dashboard_shell` | Toda la UI en HTML/CSS/JS propio; Streamlit solo procesa eventos | app arranca; flujo de carga validado por pruebas de ingesta | **Conservar** — diseño limpio, eventos deduplicados por `eventId` |
| `streamlit_components/dashboard_shell/index.html` (791 líneas) | Dock de carga compacto, estado, revisión experta, iframe del dashboard | validadores HTML/payload OK; `escapeHtml` en render dinámico | **Conservar** |
| `config.py`: parser YAML de respaldo | Evitar bloqueo del arranque en la nube si PyYAML falta | pruebas de config pasan; PyYAML sigue fijado | **Conservar** (fallback solo de contingencia) |
| `models.py`: ciclo de vida del modelo (train/`score_existing`, metadata, `MODEL_MISSING`) + `scripts/train_model.py` | Separar scoring productivo de reentrenamiento explícito | `tests/test_model_lifecycle.py` | **Conservar** — buena práctica MLOps |
| `db.py`: auditoría de eventos de revisión; `exports.py`: métricas operativas | Trazabilidad quién/qué/cuándo/antes/después | pruebas de alerts/revisión | **Conservar** |
| Carga web limitada a 1 MB51 (`max_files_per_upload`) | Simplificar la operación del usuario final | validación en `_process_upload_event` | **Conservar** |
| `.gitignore`: deja de ignorar `config/project.yml`; requirements fijados (openpyxl/xlrd/pyyaml) | Necesario para que el deploy en la nube tenga configuración | — | **Conservar con observación crítica de seguridad (§18)** |
| `reports/dashboard.html` + `outputs/*.json` versionados | La nube abre en modo consulta sin correr pipeline | — | dashboard: conservar mientras el repo sea privado; outputs: retirar del índice (propuesta GIT-001) |

Ninguna modificación manual introdujo regresiones (suite completa en verde) y
ninguna fue reemplazada "porque existía otra forma de hacerla".

## 7. Metodología

1) Inspección git y de cambios manuales; 2) suite de pruebas + validadores;
3) validación analítica independiente (recálculo desde el kardex sin usar los
módulos del pipeline); 4) profiling por log + benchmarks sintéticos 1x–10x;
5) revisión de seguridad, CRUD, UI/UX y despliegue; 6) dos corridas del
sistema de agentes (Fase 1, solo lectura) con confirmación humana de cada
hallazgo cuantitativo antes de aceptarlo.

## 8–9. Arquitectura y fuentes

Ver `docs/arquitectura.md` y `docs/fuentes_datos.md` (canónicos:
`ARQUITECTURA.md`, `EXTRACCION_DATOS_SAP.md`). Patrón: batch + artefacto
autocontenido + host Streamlit; SQLite como almacén operacional (cargas,
movimientos deduplicados, ejecuciones, alertas, revisiones, auditoría).

## 10. Validación de Data Science (resumen; detalle en `docs/data_science.md`)

Conciliación independiente kardex ↔ pipeline ↔ payload:

- Filas en ventana: **42,900 = 42,900** (0.0000%).
- Consumo neto alimento desde ancla MB5B: **795,890 = 795,890 kg** (0.0000%).
- Entradas netas: **832,190 = 832,190 kg** (0.0000%).
- Diario ↔ semanal (consumo y producción): **0.0000%**.
- ICA semanal: reproducible en **258/258** semanas evaluables
  (`consumo_productivo/produccion_productiva`, desvío máx 0.0000).
- Producción asignada a ciclos: **98.54%** (resto = fuera de ciclos, pendiente
  confirmación de negocio); mortalidad en ventana: desvío 0.6%.
- Sin doble conteo, sin pérdida silenciosa de registros, sin mezcla de
  periodos/centros; features sin fuga (rolling con `shift(1)`).

## 11–12. UI/UX y CRUD

`docs/ui_ux.md`: flujo de carga claro con confirmación explícita, estados
vacíos y errores comprensibles, render bajo demanda; pendientes menores de
accesibilidad. `docs/operaciones_crud.md`: datos crudos inmutables, borrado
solo lógico, auditoría completa de revisiones; pendientes identidad/permisos.

## 13–15. Rendimiento, Big O y escalabilidad

`docs/rendimiento_big_o.md` y `docs/pruebas_rendimiento.md`: pipeline completo
**12 s** (dominado por la generación del dashboard, 6 s); ingesta y llaves
**O(n)** medido (10x datos → 9.3–9.8x tiempo; 500k filas ≈ 43 s, 376 MB pico);
SQLite 100k inserts en 3.4 s y reingesta idempotente 1.7 s. Límites operativos
iniciales definidos. **No se aplicaron optimizaciones sin medición previa**;
las dos deudas de diseño detectadas están cuantificadas y pospuestas con
umbral de reevaluación.

## 16–17. Sistema de agentes y resultados

`docs/agentes_arquitectura.md`: 9 agentes (orquestador + 8 revisores) en
Fase 1 solo lectura, formato de hallazgo estándar, sin permisos de escritura/
push/merge/deploy. `docs/agentes_evaluacion.md`: 2 corridas; corrida 1 detectó
19 hallazgos no informativos de los cuales 3 fueron falsos positivos del
propio validador (corregidos y documentados); corrida 2 sin falsos positivos
conocidos; 0 regresiones (no escriben código).

## 18. Seguridad (detalle en `docs/seguridad.md`)

- ✅ Sin secretos versionados; carga saneada (path traversal, extensión,
  100 MB en ingesta y servidor); SQL parametrizado; crudos inmutables;
  auditoría de revisiones.
- ❌ **Crítico (decisión de negocio)**: el repositorio es **público** y la rama
  versiona `config/project.yml` y `reports/dashboard.html` con datos
  operativos reales. Recomendación: **hacer el repo privado** antes del PR.
- ❌ Alto: la app no tiene autenticación (carga y revisión abiertas a quien
  tenga la URL).

## 19–20. Despliegue y pruebas

`docs/despliegue.md`: comandos reproducibles desde ambiente limpio, rollback
definido, limitación de persistencia efímera de Streamlit Cloud documentada;
se agregó `.streamlit/config.toml` (límite de carga alineado, sin telemetría).
`docs/pruebas.md`: 107 pruebas + validadores de payload/HTML + matriz de
26 tipos de archivos de entrada.

## 21–24. Evidencias, métricas, limitaciones y riesgos

- Evidencias: `reports/agentes/<timestamp>/` (JSON por agente + consolidado),
  manifiestos por corrida en `outputs/history/`.
- Métricas de seguimiento: `docs/monitoreo_metricas.md` +
  `outputs/latest/operational_metrics.json` generado en cada corrida.
- Limitaciones: `docs/limitaciones.md` (13 numeradas).
- Riesgos principales: exposición de datos (SEC-001), app sin auth (SEC-002),
  persistencia efímera (OPS-001).

## 25–27. Correcciones, plan de mejora y checklist

Correcciones aplicadas en esta revisión: `.streamlit/config.toml` (límite de
carga servidor = ingesta) y corrección de los 3 falsos positivos del agente
DS; regresión completa en verde tras aplicarlas. Plan priorizado:
`docs/plan_mejoras.md`. Checklist: `docs/checklist_produccion.md`
(22/22 criterios técnicos ✅; 2 bloqueos no técnicos).

## 28. Recomendación sobre el PR

### **LISTO PARA PR CON OBSERVACIONES**

Fundamento objetivo: código, cálculos, KPIs, pruebas, rendimiento,
reproducibilidad, CRUD y documentación cumplen los criterios con evidencia.
Las observaciones NO son de código y condicionan el *momento* del merge:

1. **SEC-001 (crítica, de negocio)**: mientras el repositorio sea público,
   fusionar a `main` consolida la exposición de `config/project.yml` y del
   dashboard con datos reales. **Hacer el repo privado (o limpiar índice e
   historial) antes del merge.**
2. **SEC-002 (alta)**: definir el mecanismo mínimo de acceso a la app antes de
   difundir la URL más allá del equipo de validación.
3. **GIT-001 (menor)**: retirar `outputs/*.json` del índice.

Con la observación 1 resuelta, no hay impedimento técnico para el PR.

### Propuesta de PR

- **Título**: `Deploy validado del dashboard Chencopo: carga MB51 web, ciclo de vida de modelo, agentes de revisión y documentación predeploy`
- **Descripción sugerida**: resumen de §6 (cambios manuales conservados),
  resultados de validación (§10, §13–15), correcciones aplicadas (§25),
  observaciones pendientes (§28.1–3) y enlace a `docs/checklist_produccion.md`.
- **Flujo**: crear el PR desde `deploy-dashboard-chencopo` → `main`, revisión
  humana, **sin merge automático** (regla del proyecto).

## 29. Conclusiones

La rama queda inspeccionada, validada analíticamente contra la fuente,
probada (107 pruebas + validadores), medida (profiling y escalabilidad 10x),
documentada (suite completa en `docs/`) y acompañada de un sistema de agentes
evaluado en modo controlado. Los tres pendientes son decisiones de negocio
(visibilidad del repo, autenticación, índice de outputs), no defectos de
implementación.

## 30. Anexos

- `docs/data_science.md` · `docs/ui_ux.md` · `docs/operaciones_crud.md`
- `docs/rendimiento_big_o.md` · `docs/pruebas_rendimiento.md`
- `docs/agentes_arquitectura.md` · `docs/agentes_evaluacion.md`
- `docs/pruebas.md` · `docs/seguridad.md` · `docs/despliegue.md`
- `docs/monitoreo_metricas.md` · `docs/limitaciones.md` · `docs/plan_mejoras.md`
- `docs/checklist_produccion.md` · `reports/agentes/<timestamp>/`
