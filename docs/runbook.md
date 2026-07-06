# Runbook operativo

## Instalacion

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

## Configuracion

1. Copiar la estructura de `config/project.example.yml`.
2. Crear o mantener `config/project.yml` local.
3. Actualizar rutas de fuentes, materiales, modelo y parametros.
4. Verificar que `config/project.yml` no exponga credenciales ni rutas sensibles antes de publicar.

## Ejecucion productiva del pipeline

```powershell
python -m granjas_anomalias.cli run --config config/project.yml
```

Con `model_lifecycle.mode: score_existing`, esta ejecucion usa el modelo activo versionado y no reentrena automaticamente durante cargas productivas.

Alternativa:

```powershell
scripts\run_all.bat
```

## Entrenamiento controlado del modelo

El entrenamiento se ejecuta de forma explicita, fuera de la carga diaria:

```powershell
python scripts/train_model.py
```

Este comando fuerza `model_mode="train"`, guarda el artefacto configurado en `model_lifecycle.active_model_path` y actualiza la metadata definida en `model_lifecycle.metadata_path`.

## Carga web

La app recibe un solo archivo MB51 crudo por carga. La experiencia visible vive en HTML/CSS/JS; Streamlit solo funciona como host/backend.

```powershell
python -m streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8508
```

## Validaciones posteriores

```powershell
uv run --with pytest --with pandas --with openpyxl pytest -q
python scripts/validar_dashboard_payload.py
python scripts/validar_dashboard_html.py
python scripts/check_reference_results.py
```

`check_reference_results.py` solo aplica controles exactos si existen en `reference_validation` dentro de la configuracion local.

## Revision de salidas

Verificar:

- `reports/run_manifest.json`;
- `reports/CALIDAD_DATOS.md`;
- `reports/EDA_Y_ANOMALIAS.md`;
- `reports/tables/03_movimientos_no_clasificados.csv`;
- `data/processed/10_features_y_scores_diarios.csv`;
- `data/processed/11_anomalias_consumo.csv`;
- `outputs/latest/operational_metrics.json`;
- `outputs/latest/alert_review_audit.csv`.

## Revision de logs

El pipeline escribe en `logs/pipeline.log`. Revisar este archivo cuando falle una etapa o falten salidas.

## Solucion de problemas

| Sintoma | Revision sugerida |
|---|---|
| Falta una fuente | Confirmar ruta en `config/project.yml`. |
| Fallan columnas de MB51 | Revisar exportacion y alias en `normalize.py`. |
| No se detectan ciclos | Confirmar movimientos de entrada de aves y fecha de analisis. |
| Muchas combinaciones no clasificadas | Revisar `reports/tables/03_movimientos_no_clasificados.csv`. |
| No se genera modelo en entrenamiento | Revisar filas elegibles; el baseline no entrena con bajo volumen. |
| Modelo faltante en produccion | Revisar `model_lifecycle.active_model_path`; el pipeline no reentrena en silencio. |
| Dashboard invalido | Ejecutar validadores de payload y HTML. |
| Streamlit Cloud instala mal dependencias | Confirmar ausencia de `uv.lock` y uso de `requirements.txt`. |

## Recuperacion ante errores

1. No modificar `data/raw/`.
2. Revisar logs, manifiesto y metricas operativas.
3. Corregir configuracion o fuente.
4. Regenerar pipeline completo.
5. Validar pruebas, payload y dashboard.
6. Si el problema es de modelo, restaurar artefacto y metadata anteriores.

## Antes de produccion

- Confirmar que no hay datos reales no autorizados en Git.
- Ejecutar pruebas.
- Revisar calidad de fuentes.
- Confirmar modo `score_existing` y artefacto activo aprobado.
- Revisar `outputs/latest/operational_metrics.json`.
- Validar dashboard.
- Acordar responsables de revision de alertas.
- Confirmar ausencia de `uv.lock` si Streamlit Cloud debe usar `requirements.txt`.
