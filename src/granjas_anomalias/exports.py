"""Exportación de salidas para operación y dashboard.

Escribe ``outputs/latest`` (estado vigente), ``outputs/dashboard`` (datasets
para visualización) y ``outputs/history/AAAA/MM/run_*`` (trazabilidad por
ejecución).
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from .config import ProjectConfig
from .db import Warehouse


def _guardar(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def exportar_salidas(
    config: ProjectConfig,
    db: Warehouse,
    run_id: str,
    alertas: pd.DataFrame,
    cobertura: pd.DataFrame,
    weekly: pd.DataFrame,
    manifest: dict,
) -> dict[str, Path]:
    outputs_dir = config.root / "outputs"
    latest = outputs_dir / "latest"
    dashboard = outputs_dir / "dashboard"
    rutas: dict[str, Path] = {}

    # --- Registro de cargas y ejecuciones ---
    cargas = db.listar_cargas()
    rutas["file_load_registry"] = _guardar(cargas, latest / "file_load_registry.csv")
    rutas["dashboard_cargas"] = _guardar(cargas, dashboard / "dashboard_cargas.csv")

    # --- Cobertura ---
    rutas["inventory_coverage"] = _guardar(cobertura, latest / "inventory_coverage.csv")
    global_cov = cobertura.loc[cobertura["nivel"].eq("global")]
    rutas["dashboard_alimento"] = _guardar(global_cov, dashboard / "dashboard_alimento.csv")

    # --- Alertas por familia ---
    rutas["consolidated_alerts"] = _guardar(alertas, latest / "consolidated_alerts.csv")
    if not alertas.empty:
        criticas = alertas.loc[alertas["severidad"].eq("critica")]
        familias = {
            "overstock_alerts.csv": alertas["tipo"].isin(["SOBRESTOCK", "ALIMENTO_SIN_MOVIMIENTO"]),
            "shortage_alerts.csv": alertas["tipo"].isin(
                ["RIESGO_DESABASTO", "INVENTARIO_CERO_CON_AVES"]
            ),
            "consumption_alerts.csv": alertas["familia"].eq("CONSUMO"),
            "production_alerts.csv": alertas["familia"].eq("PRODUCCION"),
            "ica_alerts.csv": alertas["familia"].eq("ICA"),
            "quality_alerts.csv": alertas["tipo_resultado"].eq("CALIDAD_DE_DATOS"),
        }
    else:
        criticas = alertas
        familias = {
            nombre: pd.Series(dtype=bool)
            for nombre in [
                "overstock_alerts.csv",
                "shortage_alerts.csv",
                "consumption_alerts.csv",
                "production_alerts.csv",
                "ica_alerts.csv",
                "quality_alerts.csv",
            ]
        }
    rutas["critical_alerts"] = _guardar(criticas, latest / "critical_alerts.csv")
    for nombre, mascara in familias.items():
        subset = alertas.loc[mascara] if not alertas.empty else alertas
        rutas[nombre] = _guardar(subset, latest / nombre)

    historial = db.leer_alertas()
    rutas["alert_history"] = _guardar(historial, latest / "alert_history.csv")

    # --- Datasets del dashboard ---
    if not alertas.empty:
        resumen = (
            alertas.groupby(["familia", "tipo", "severidad", "estado"], dropna=False)
            .size()
            .rename("n_alertas")
            .reset_index()
        )
    else:
        resumen = pd.DataFrame(columns=["familia", "tipo", "severidad", "estado", "n_alertas"])
    rutas["dashboard_alertas_resumen"] = _guardar(
        resumen, dashboard / "dashboard_alertas_resumen.csv"
    )
    rutas["dashboard_alertas_detalle"] = _guardar(
        alertas, dashboard / "dashboard_alertas_detalle.csv"
    )
    if weekly is not None and not weekly.empty:
        rutas["dashboard_ica"] = _guardar(weekly, dashboard / "dashboard_ica.csv")

    # --- Manifiesto de la ejecución ---
    manifest = dict(manifest)
    manifest["run_id"] = run_id
    manifest["alertas"] = {
        "total": int(len(alertas)),
        "criticas": int(len(criticas)),
        "por_estado": alertas["estado"].value_counts().to_dict() if not alertas.empty else {},
    }
    manifest_path = latest / "execution_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    rutas["execution_manifest"] = manifest_path

    # --- Historial por ejecución ---
    ahora = datetime.now()
    hist_dir = outputs_dir / "history" / f"{ahora:%Y}" / f"{ahora:%m}" / f"run_{run_id}"
    hist_dir.mkdir(parents=True, exist_ok=True)
    for archivo in latest.glob("*"):
        if archivo.is_file():
            shutil.copy2(archivo, hist_dir / archivo.name)
    rutas["history_dir"] = hist_dir
    return rutas
