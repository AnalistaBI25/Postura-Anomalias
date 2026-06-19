# Objetivo general y alcance

## Objetivo general

Construir un producto reproducible de BI/Data Science que reconstruya ciclos productivos desde SAP, explique el flujo de alimento desde un almacén compartido hacia ciclos/casetas mediante órdenes operativas y priorice inconsistencias de consumo para revisión experta.

## Pregunta central

¿Qué consumos de alimento son inconsistentes para la edad, número de aves, fase, historial reciente, producción, mortalidad, estándar productivo y movimientos SAP del ciclo?

## Alcance de la Fase 1

1. Ingesta y validación de MB51, MB5B, política y organización.
2. Normalización de llaves SAP.
3. Clasificación auditable de materiales y movimientos.
4. Detección de ciclos biológicos.
5. Asociación de órdenes operativas.
6. Reconstrucción diaria de aves, mortalidad, consumo y producción.
7. Reconstrucción global de stock del almacén de alimento.
8. Comparación contra política por edad.
9. EDA y reglas de anomalía.
10. Baseline no supervisado con Isolation Forest.

La Fase 1 está documentada en `docs/fase_1_plataforma_bi.md`.

## Alcance de la Fase 2

Investigación no supervisada, comparación de modelos, validación experta y selección de un candidato. Ver `docs/fase_2_modelado_anomalias.md`.

## Alcance de la Fase 3

Industrialización, scoring, monitoreo, deriva, retroalimentación y reentrenamiento. Ver `docs/fase_3_mlops_produccion.md`.

## Fuera de alcance actual

- Diagnóstico sanitario automático.
- Afirmar fraude o error sin validación humana.
- Pronóstico de consumo como verdad operativa.
- Clasificador supervisado definitivo sin etiquetas de negocio.
