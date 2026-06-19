# Arquitectura

## Arquitectura actual - Fase 1

```mermaid
flowchart LR
    A[Fuentes SAP y maestros] --> B[Carga io.py]
    B --> C[Normalización normalize.py]
    C --> D[Clasificación SAP classify.py]
    D --> E[Ciclos cycles.py]
    E --> F[Línea diaria y semanal daily.py + productivity.py]
    D --> G[Stock global stock.py]
    F --> H[Features features.py]
    G --> H
    H --> I[Reglas anomaly_rules.py]
    I --> J[Isolation Forest baseline models.py]
    J --> K[Reportes, tablas y dashboard]
```

La Fase 1 genera datasets intermedios, procesados, reportes, figuras, modelo baseline, payload y dashboard HTML.

## Arquitectura objetivo - Fases 2 y 3

```mermaid
flowchart LR
    A[Features validadas] --> B[Laboratorio Fase 2]
    B --> C[Comparación de modelos]
    C --> D[Revisión experta]
    D --> E[Modelo candidato]
    E --> F[Registro de modelo]
    F --> G[Scoring productivo]
    G --> H[Dashboard y alertas]
    H --> I[Retroalimentación humana]
    I --> J[Monitoreo de deriva]
    J --> K[Reentrenamiento controlado]
    K --> F
```

## Capas actuales

| Capa | Ruta | Descripción |
|---|---|---|
| Raw | `data/raw/` | Exportaciones y fuentes originales. |
| Cache | `data/cache/` | Cache local de lectura. |
| Interim | `data/interim/` | Datos normalizados y clasificados. |
| Processed | `data/processed/` | Ciclos, línea diaria, stock, features y anomalías. |
| Models | `models/` | Artefactos generados del baseline. |
| Reports | `reports/` | Figuras, tablas, dashboard y manifiesto. |
| Source | `src/granjas_anomalias/` | Código productivo del pipeline. |

## Principios

- Raw no se modifica.
- El stock físico se separa del consumo atribuido por ciclo.
- Las reglas son auditables y exportan combinaciones no clasificadas.
- El baseline no supervisado prioriza revisión, no reemplaza criterio experto.
- Los dashboards generados con payload real no son publicables.
