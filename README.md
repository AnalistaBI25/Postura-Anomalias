# Proyecto BI/Data Science de anomalías en consumo avícola

Proyecto reproducible en Python para convertir exportaciones operativas de SAP y maestros productivos en una plataforma BI de seguimiento de alimento, ciclos, inventario, productividad y señales iniciales de anomalía.

El repositorio está organizado como un proyecto evolutivo de tres fases:

| Fase | Estado | Objetivo |
|---|---|---|
| Fase 1 | Terminada y funcional | Plataforma BI, ETL, indicadores, inventario, dashboard, reglas y baseline inicial de anomalías. |
| Fase 2 | Pendiente | Investigación no supervisada de anomalías, comparación de modelos y validación experta. |
| Fase 3 | Futura | MLOps, despliegue, scoring productivo, monitoreo, deriva, retroalimentación y reentrenamiento. |

## Problema de negocio

El negocio necesita saber si el consumo de alimento observado es consistente con el ciclo productivo, la edad de las aves, la fase alimenticia, la producción, la mortalidad, los estándares y los movimientos SAP. El proyecto no busca afirmar fraude, merma o error de forma automática; prioriza eventos para revisión operativa con trazabilidad.

## Qué existe hoy

La Fase 1 ya implementa:

- carga de fuentes SAP y maestros desde `config/project.yml`;
- normalización de llaves, fechas y cantidades;
- clasificación auditable de movimientos SAP;
- detección de ciclos productivos;
- reconstrucción diaria de aves, mortalidad, consumo y producción;
- agregación semanal e indicadores de ICA;
- integración de estándares productivos;
- reconstrucción de stock global de alimento;
- generación de features para anomalías;
- reglas explicables de desviación;
- baseline no supervisado con Isolation Forest;
- dashboard HTML con Chart.js y payload embebido;
- reportes, tablas de control, logs, manifiesto y pruebas automatizadas.

## Arquitectura general

```text
Fuentes SAP y maestros
  -> carga y normalización
  -> clasificación de movimientos
  -> ciclos productivos
  -> línea diaria y semanal
  -> stock global
  -> features
  -> reglas + baseline no supervisado
  -> reportes y dashboard
```

La arquitectura detallada está en `docs/architecture.md`.

## Estructura del repositorio

```text
config/                     Configuración local y ejemplo seguro
data/                       Datos raw, cache, intermedios y procesados
docs/                       Documentación funcional y técnica
legacy/                     Código preservado del prototipo
models/                     Modelos generados
notebooks/                  Laboratorios de análisis
reports/                    Reportes, figuras, tablas y dashboards generados
scripts/                    Validadores y comandos auxiliares
src/granjas_anomalias/      Paquete productivo
tests/                      Pruebas automatizadas
```

Los datos reales, reportes generados, dashboards con payload, modelos, logs y configuración local están protegidos por `.gitignore`.

## Fuentes de datos

El pipeline espera, según `config/project.yml`:

- kardex SAP MB51;
- estándar productivo semanal;
- maestro de organización;
- maestro de materiales;
- ancla de stock inicial MB5B, cuando aplique.

`config/project.example.yml` contiene valores ficticios y seguros para documentar la estructura sin exponer datos.

## Instalación

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

También puede usarse:

```powershell
pip install -r requirements.txt
```

## Ejecución

Con el entorno activo:

```powershell
python -m granjas_anomalias.cli run --config config/project.yml
```

O mediante scripts:

```powershell
scripts\run_all.bat
```

## Validaciones

Pruebas automatizadas:

```powershell
pytest
```

Validación del payload:

```powershell
python scripts/validar_dashboard_payload.py
```

Validación del dashboard HTML:

```powershell
python scripts/validar_dashboard_html.py
```

Validación opcional de resultados de referencia:

```powershell
python scripts/check_reference_results.py
```

Los controles exactos de referencia deben declararse en el `config/project.yml` local, dentro de `reference_validation`.

## Salidas principales

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
- `reports/tables/05_plantilla_validacion_anomalias.csv`
- `reports/EDA_Y_ANOMALIAS.md`
- `reports/dashboard.html`
- `reports/run_manifest.json`
- `models/isolation_forest_consumo.joblib`

Estas salidas se consideran artefactos generados y no deben publicarse con datos reales.

## Baseline actual de anomalías

El baseline actual es no supervisado. `src/granjas_anomalias/models.py` entrena un `IsolationForest` dentro de un `Pipeline` con imputación mediana y escalamiento robusto. Consume variables de consumo por ave, brecha contra estándar, z-score robusto, cambio diario, estadísticas móviles, mortalidad, producción, edad y fases activas.

El score final combina:

- `score_reglas`, generado por reglas auditables en `anomaly_rules.py`;
- `score_ml`, generado por Isolation Forest;
- pesos y umbrales definidos en configuración.

Este baseline sirve para priorización y revisión experta. No es un modelo final validado.

## Roadmap

- Fase 1: completada. Mantener y mejorar diseño, documentación, pruebas, seguridad y mantenibilidad sin cambiar reglas de negocio.
- Fase 2: pendiente. Ejecutar experimentación no supervisada en `notebooks/02_modelado_anomalias_no_supervisado.ipynb`, comparar modelos y seleccionar candidato con expertos.
- Fase 3: futura. Industrializar entrenamiento, scoring, monitoreo, drift, retroalimentación y reentrenamiento.

El roadmap operativo está en `docs/roadmap.md`.

## Seguridad

No publicar:

- `config/project.yml`;
- `data/`;
- `reports/`;
- `models/`;
- `logs/`;
- dashboards HTML generados;
- notebooks ejecutados con datos reales;
- credenciales, rutas personales, órdenes, lotes, documentos SAP o payloads reales.

GitHub Pages solo debe usarse con datos sintéticos o anonimizados.
