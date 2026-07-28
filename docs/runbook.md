# Runbook operativo

## Instalación

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e .
```

## Configuración

1. Copiar la estructura de `config/project.example.yml`.
2. Crear una configuración en `config/`.
3. Asignar un `project.farm_id` único y estable.
4. Actualizar fuentes, centro, casetas, materiales, almacenes y fechas.
5. Definir el modo y las rutas del modelo de esa granja.
6. Verificar que la configuración no exponga credenciales.

Todas las rutas operativas del YAML son relativas a `farms/<farm_id>/`. Ver
[GUIA_PROYECTO_MULTI_GRANJA.md](GUIA_PROYECTO_MULTI_GRANJA.md).

## Ejecución

```powershell
uv run python -m granjas_anomalias.cli run --config config/project.yml
```

Con `model_lifecycle.mode: score_existing`, la ejecución usa el modelo activo de
la granja y no reentrena automáticamente.

Alternativas:

```powershell
.\scripts\run_all.ps1 config/project.yml
scripts\run_all.bat config\project.yml
```

## Carga incremental

```powershell
uv run python scripts/validate_input.py --input "archivo.xlsx" --config config/project.yml
uv run python scripts/run_incremental.py --input "archivo.xlsx" --config config/project.yml
```

## Entrenamiento controlado

```powershell
uv run python scripts/train_model.py --config config/project.yml
```

Este comando fuerza `model_mode="train"`. Solo debe usarse con autorización,
datos suficientes y una política de promoción definida para esa granja.

## Streamlit

La aplicación usa `config/project.yml` como configuración activa. La selección
dinámica de granja no forma parte de esta fase.

```powershell
uv run streamlit run streamlit_app.py --server.address 127.0.0.1 --server.port 8508
```

## Validaciones

```powershell
uv run pytest -q
uv run python scripts/validar_dashboard_payload.py --config config/project.yml
uv run python scripts/validar_dashboard_html.py --config config/project.yml
uv run python scripts/check_reference_results.py --config config/project.yml
```

`check_reference_results.py` aplica controles exactos cuando la configuración
contiene `reference_validation`.

## Revisión de salidas

Sustituir `<farm_id>` por el identificador configurado:

- `farms/<farm_id>/reports/run_manifest.json`;
- `farms/<farm_id>/reports/CALIDAD_DATOS.md`;
- `farms/<farm_id>/reports/EDA_Y_ANOMALIAS.md`;
- `farms/<farm_id>/reports/tables/03_movimientos_no_clasificados.csv`;
- `farms/<farm_id>/data/processed/10_features_y_scores_diarios.csv`;
- `farms/<farm_id>/data/processed/11_anomalias_consumo.csv`;
- `farms/<farm_id>/outputs/latest/operational_metrics.json`;
- `farms/<farm_id>/outputs/latest/alert_review_audit.csv`;
- `farms/<farm_id>/logs/pipeline.log`.

## Solución de problemas

| Síntoma | Revisión sugerida |
|---|---|
| `farm_id` inválido | Usar minúsculas, números, guion o guion bajo; no usar rutas. |
| Falta una fuente | Confirmar su ruta bajo `farms/<farm_id>/`. |
| Fallan columnas de MB51 | Revisar exportación y alias en `normalize.py`. |
| No se detectan ciclos | Confirmar entradas de aves y ventana de análisis. |
| Muchas combinaciones sin clasificar | Revisar `reports/tables/03_movimientos_no_clasificados.csv` dentro de la granja. |
| Modelo faltante | Revisar `farms/<farm_id>/models/` y `model_lifecycle`. |
| Dashboard inválido | Ejecutar validadores de payload y HTML con el mismo `--config`. |
| Aparecen resultados en otra granja | Detener la operación y revisar `farm_id` y el archivo YAML seleccionado. |

## Recuperación

1. No modificar ni borrar las fuentes raw.
2. Revisar log, manifiesto y métricas de la granja afectada.
3. Corregir configuración o fuente.
4. Regenerar solo esa granja.
5. Ejecutar pruebas y validadores.
6. Si el problema es de modelo, restaurar artefacto y metadata de esa granja.

Las carpetas anteriores a la migración están respaldadas en
`legacy/chencopo_pre_multigranja/` y no deben borrarse sin autorización
separada.
