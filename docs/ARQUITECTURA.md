# Arquitectura del proyecto

La arquitectura vigente y la arquitectura objetivo están documentadas en `docs/architecture.md`.

## Resumen

- Fase 1 actual: fuentes -> ETL -> indicadores -> stock -> reglas -> baseline no supervisado -> dashboard.
- Fase 2 pendiente: experimentación no supervisada, comparación de modelos y validación experta.
- Fase 3 futura: MLOps, scoring, monitoreo, deriva, retroalimentación y reentrenamiento.

## Separación fundamental

- **Almacén:** stock físico global de alimento.
- **Caseta/ciclo:** consumo y producción atribuidos mediante la orden operativa.
- **Ciclo biológico:** centro + caseta + lote + fecha de entrada de aves.
