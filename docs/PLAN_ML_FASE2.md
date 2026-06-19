# Estrategia de Machine Learning - Fase 2

La estrategia completa está en `docs/fase_2_modelado_anomalias.md`.

## Principio

La Fase 2 es una investigación no supervisada. Sin etiquetas expertas confiables, el objetivo no es entrenar un clasificador final sino comparar enfoques para priorizar revisión operativa.

## Línea base

El modelo actual es un baseline no supervisado con Isolation Forest combinado con reglas de negocio. Debe reproducirse y compararse contra:

- reglas robustas;
- Isolation Forest con sensibilidad de parámetros;
- Local Outlier Factor;
- One-Class SVM como opción exploratoria;
- acuerdo entre modelos.

## Validación

La validación debe ser temporal, explicable y revisada por expertos. Accuracy, precision, recall, F1 y matriz de confusión no son métricas principales hasta contar con etiquetas reales.
