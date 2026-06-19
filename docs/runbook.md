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
2. Crear o mantener `config/project.yml` local.
3. Actualizar rutas de fuentes, materiales y parámetros.
4. Verificar que `config/project.yml` no se versiona.

## Ejecución del pipeline

```powershell
python -m granjas_anomalias.cli run --config config/project.yml
```

Alternativa:

```powershell
scripts\run_all.bat
```

## Validaciones posteriores

```powershell
pytest
python scripts/validar_dashboard_payload.py
python scripts/validar_dashboard_html.py
python scripts/check_reference_results.py
```

`check_reference_results.py` solo aplica controles exactos si existen en `reference_validation` dentro de la configuración local.

## Regeneración del dashboard

El dashboard se regenera dentro del pipeline. Para validar un HTML de prueba:

```powershell
python scripts/validar_dashboard_html.py
```

El HTML generado contiene payload real y no debe publicarse.

## Revisión de salidas

Verificar:

- `reports/run_manifest.json`;
- `reports/CALIDAD_DATOS.md`;
- `reports/EDA_Y_ANOMALIAS.md`;
- `reports/tables/03_movimientos_no_clasificados.csv`;
- `data/processed/10_features_y_scores_diarios.csv`;
- `data/processed/11_anomalias_consumo.csv`.

## Revisión de logs

El pipeline escribe en `logs/pipeline.log`. Revisar este archivo cuando falle una etapa o falten salidas.

## Solución de problemas

| Síntoma | Revisión sugerida |
|---|---|
| Falta una fuente | Confirmar ruta en `config/project.yml`. |
| Fallan columnas de MB51 | Revisar exportación y alias en `normalize.py`. |
| No se detectan ciclos | Confirmar movimientos de entrada de aves y fecha de análisis. |
| Muchas combinaciones no clasificadas | Revisar `reports/tables/03_movimientos_no_clasificados.csv`. |
| No se genera modelo | Revisar filas elegibles; el baseline no entrena con bajo volumen. |
| Dashboard inválido | Ejecutar validadores de payload y HTML. |

## Recuperación ante errores

1. No modificar `data/raw/`.
2. Revisar logs y manifiesto.
3. Corregir configuración o fuente.
4. Regenerar pipeline completo.
5. Validar pruebas y dashboard.

## Antes de producción

- Confirmar que no hay datos reales en Git.
- Ejecutar pruebas.
- Revisar calidad de fuentes.
- Confirmar salidas esperadas.
- Validar dashboard.
- Acordar responsables de revisión de alertas.
