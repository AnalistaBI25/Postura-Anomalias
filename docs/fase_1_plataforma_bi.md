# Fase 1 - Plataforma BI, ETL y analítica descriptiva

## Estado

Terminada y funcional. La Fase 1 convierte fuentes operativas en datasets auditables, indicadores productivos, controles de calidad, señales iniciales de anomalía y un dashboard HTML.

## Objetivo

Reconstruir el flujo de alimento y el comportamiento productivo por ciclo para responder si el consumo observado es consistente con edad, aves disponibles, fase alimenticia, producción, mortalidad, estándar productivo y movimientos SAP.

## Alcance implementado

- Carga de kardex, estándar productivo, organización, materiales y ancla de stock.
- Normalización de llaves, fechas y cantidades.
- Clasificación de movimientos por bloque operativo.
- Detección de ciclos biológicos desde entradas de aves.
- Asociación de órdenes operativas como conector de consumo, producción y mortalidad.
- Cálculo de aves disponibles, mortalidad, consumo, producción, edad e ICA.
- Preparación de política productiva semanal.
- Reconstrucción de stock de alimento por material y global.
- Controles de calidad y catálogo de combinaciones SAP.
- Variables analíticas y reglas de anomalía.
- Entrenamiento de baseline no supervisado con Isolation Forest.
- Reportes, figuras, dashboard y plantilla de validación experta.
- Pruebas automatizadas y scripts de validación.

## Fuentes

Las rutas se definen en `config/project.yml` y se documentan de forma segura en `config/project.example.yml`:

- `kardex_excel`: exportación MB51.
- `kardex_cache_csv`: cache local del kardex.
- `standard_excel`: estándar productivo semanal.
- `organization_excel`: organización y materiales.
- `mb5b_excel`: stock inicial opcional.

## Flujo ETL

1. `io.py` carga fuentes desde Excel o cache.
2. `normalize.py` estandariza columnas, fechas, llaves y cantidades.
3. `classify.py` asigna roles de movimiento.
4. `quality.py` genera controles de calidad y catálogos.
5. `cycles.py` detecta ciclos y cierres.
6. `daily.py` construye línea diaria.
7. `productivity.py` enriquece con estándares, producción e ICA.
8. `stock.py` reconstruye inventario.
9. `features.py` crea variables para anomalías.
10. `anomaly_rules.py` genera score de reglas.
11. `models.py` entrena baseline y combina scores.
12. `eda.py` y `dashboard.py` generan reportes y dashboard.

## Reglas de integración

- El ciclo biológico se identifica por centro, caseta, lote y fecha de entrada.
- La orden se usa como conector operativo, no como llave biológica primaria.
- El stock pertenece al almacén global de alimento.
- El consumo productivo se atribuye por orden/ciclo.
- El ICA se evalúa principalmente en escala semanal.
- Las combinaciones SAP no reconocidas no se descartan; se exportan para revisión.

## Construcción diaria y semanal

`daily.py` genera una línea diaria por ciclo con calendario completo, edad, aves disponibles, mortalidad, consumo, producción, fases activas y contexto SAP. `productivity.py` agrega estándares, producción esperada, brechas, ICA diario de arranque cuando aplica e ICA semanal.

## Inventario y stock global

`stock.py` reconstruye movimientos de alimento con entradas, reversas, consumo, traspasos, ajustes, mermas, diferencias de inventario y logística. Produce vistas por material y global, con conciliación.

## Anomalías baseline

`features.py` calcula variables como consumo por ave, z-score robusto, cambio diario, promedios móviles, mortalidad por mil, ratios contra estándar, fases activas y conciliación de stock.

`anomaly_rules.py` asigna puntos por reglas auditables:

- desviación robusta;
- brecha contra política;
- cambio abrupto;
- consumo cero con aves;
- consumo negativo;
- consumo sin orden;
- múltiples fases;
- diferencia de conciliación;
- mortalidad alta.

`models.py` entrena un `IsolationForest` cuando hay suficientes filas elegibles. El modelo actual es un baseline no supervisado para priorización, no un modelo final validado.

## Dashboard

`dashboard.py` construye un payload validado con `dashboard_payload.py`, inserta JSON en `src/granjas_anomalias/templates/dashboard_productivo.html` y escribe `reports/dashboard.html`.

El dashboard generado contiene datos embebidos y no debe publicarse con información real.

## Archivos generados

Los artefactos principales son:

- `data/interim/01_kardex_normalizado_clasificado.csv`
- `data/interim/02_organizacion_normalizada.csv`
- `data/interim/03_materiales_normalizados.csv`
- `data/processed/04_politica_preparada.csv`
- `data/processed/05_ciclos_detectados.csv`
- `data/processed/06_linea_diaria_ciclos.csv`
- `data/processed/07_resumen_semanal_ciclos.csv`
- `data/processed/08_stock_alimento_diario_por_material.csv`
- `data/processed/09_stock_alimento_diario_global.csv`
- `data/processed/10_features_y_scores_diarios.csv`
- `data/processed/11_anomalias_consumo.csv`
- `reports/tables/01_calidad_fuentes.csv`
- `reports/tables/02_catalogo_movimientos_sap.csv`
- `reports/tables/03_movimientos_no_clasificados.csv`
- `reports/tables/04_nulos_llaves_sap.csv`
- `reports/tables/05_plantilla_validacion_anomalias.csv`
- `reports/CALIDAD_DATOS.md`
- `reports/EDA_Y_ANOMALIAS.md`
- `reports/dashboard.html`
- `reports/run_manifest.json`
- `models/isolation_forest_consumo.joblib`
- `models/isolation_forest_metadata.json`

## Validadores y pruebas

- `pytest` ejecuta pruebas unitarias.
- `scripts/validar_dashboard_payload.py` valida estructura del payload.
- `scripts/validar_dashboard_html.py` valida inserción del payload en HTML.
- `scripts/check_reference_results.py` ejecuta controles opcionales declarados en config local.

## Limitaciones

- El baseline no demuestra causalidad ni confirma anomalías reales.
- Sin etiquetas expertas no deben usarse métricas supervisadas como accuracy, recall, F1 o matriz de confusión.
- La calidad depende de la consistencia de exportaciones SAP y maestros.
- El dashboard generado no es apto para publicación si contiene datos reales.
- Las reglas SAP pueden requerir ajustes cuando aparezcan combinaciones nuevas.

## Mejoras posteriores de Fase 1

- Mejorar diseño y accesibilidad del dashboard.
- Aumentar cobertura de pruebas de integración.
- Robustecer mensajes de error para fuentes incompletas.
- Agregar validadores de privacidad antes de publicar reportes.
- Documentar ejemplos sintéticos mínimos.
- Reducir duplicidad entre documentos antiguos y nuevos.
