# Preguntas pendientes y supuestos provisionales

Registro vivo de decisiones confirmadas con el usuario, supuestos provisionales
parametrizados y pendientes con el área responsable. Actualizado: 2026-07-06.

## Decisiones confirmadas (2026-07-06)

| Tema | Decisión |
|---|---|
| Módulo de carga web | Streamlit (`streamlit_app.py`), extendiendo el wrapper existente; el dashboard HTML autocontenido se conserva intacto. |
| Persistencia incremental | SQLite (`data/warehouse.db`): registro de cargas, movimientos deduplicados, ejecuciones, alertas y revisiones manuales. |
| Estrategia ante traslapes | Insertar solo registros nuevos (llave de negocio + ocurrencia); nada se borra ni se sobreescribe; el traslape queda registrado. |
| Alcance multi-granja | El registro y el almacén lógico separan por centro desde el diseño; el procesamiento se hace por granja con su `config/<granja>.yml`. |
| Alcance de almacenes | **Solo granjas con un único almacén de alimento** (pueden tener varias casetas). Multialmacén queda fuera de esta iteración. |
| Formato de carga oficial | Exportación directa MB51 de SAP (estructura de `kardex_mb51_*.xlsx`, hoja `Data`). Los libros de trabajo mensuales por granja (hojas 1..31) **no** son formato de carga y se rechazan con motivo. |
| Mortalidad | Fuente única: kardex MB51 (261/262 WR sobre el material de aves). No hay captura operativa adicional. |
| Fórmula de ICA | Se confirma `consumo_neto / producción_neta` (producción = principal + subproductos), evaluación semanal; se añade ICA acumulado por ciclo como referencia. |
| Gestión de alertas | Estados automáticos entre corridas (nueva/persistente/recurrente/reabierta/resuelta) + revisión manual desde Streamlit (CONFIRMADA / FALSO_POSITIVO / PROBLEMA_DE_DATOS) persistida en SQLite. |

## Supuestos provisionales (parametrizados, PENDIENTE DE CONFIRMACIÓN)

| Supuesto | Valor provisional | Dónde se configura | Impacto si cambia |
|---|---|---|---|
| Días de cobertura mínimo | 3 días | `coverage.dias_cobertura_minimo` | Alertas de desabasto más/menos sensibles. |
| Días de cobertura objetivo | 7 días | `coverage.dias_cobertura_objetivo` | Cambia el "inventario requerido" informativo. |
| Días de cobertura máximo | 15 días | `coverage.dias_cobertura_maximo` | Alertas de sobrestock más/menos sensibles. |
| Ventana de consumo estimado | 7 días (media móvil) | `coverage.ventana_consumo_dias` | Estabilidad del estimado de consumo diario. |
| Días sin movimiento para alertar | 14 días | `coverage.dias_sin_movimiento_alerta` | Alertas de alimento inmovilizado. |
| Umbral ICA fuera de estándar | 15 % (reusa `policy_gap_warning_pct`) | `anomaly_detection.policy_gap_warning_pct` | Volumen de alertas de ICA. |
| Ventana de vigencia de alertas | 7 días desde la última fecha con datos | argumento `ventana_actividad_dias` en `alerts.construir_alertas` | Qué eventos se consideran "vigentes". |

## Pendientes con el área responsable / SAP

- **Capacidad máxima de silos/almacenes**: no existe en las fuentes actuales
  (la hoja "Capacidad" de los libros mensuales parece contener saldos de aves,
  no capacidad de silos). Sin este dato no se emite la alerta
  "inventario por encima del máximo físico". PENDIENTE DE CONFIRMACIÓN.
- **Inventario de seguridad y tiempo de reposición**: no documentados; la
  cobertura mínima provisional (3 días) hace de sustituto. PENDIENTE.
- **Alimento en tránsito y pedidos programados**: los movimientos 641/642/643
  se conservan como contexto logístico y NO entran al consumo ni al ICA; no hay
  fuente de pedidos futuros. PENDIENTE.
- **Movimientos anulados en exportaciones incrementales**: confirmar si una
  anulación posterior aparece en la siguiente exportación MB51 con el mismo
  documento (hoy se asume que sí, como par 102/262). PENDIENTE con SAP.
- **Umbrales oficiales de cobertura**: sustituir los provisionales cuando el
  negocio los defina (por granja, etapa o material).
- **Granjas multialmacén de alimento**: fuera de alcance en esta iteración;
  requiere decidir si el stock se modela por almacén o consolidado.
- **Impacto económico por alerta**: requiere costo del alimento por material;
  no disponible en las fuentes actuales. PENDIENTE.

## Cómo actualizar un supuesto

1. Edita el valor en `config/project.yml` (sección `coverage` o `anomaly_detection`).
2. Reejecuta `python scripts/run_incremental.py --solo-pipeline`.
3. El cambio queda trazado en `outputs/history/<año>/<mes>/run_*/execution_manifest.json`.
