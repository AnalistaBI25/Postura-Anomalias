from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ProjectConfig


def apply_rule_anomalies(features: pd.DataFrame, config: ProjectConfig) -> pd.DataFrame:
    result = features.copy()
    settings = config.anomaly
    robust_threshold = float(settings["robust_z_threshold"])
    warning_gap = float(settings["policy_gap_warning_pct"])
    critical_gap = float(settings["policy_gap_critical_pct"])
    change_threshold = float(settings["daily_change_warning_pct"])

    result["flag_z_robusto"] = result["consumo_robust_z_28"].abs().ge(robust_threshold)
    result["flag_brecha_politica"] = result["brecha_consumo_pct_dia"].abs().ge(warning_gap)
    result["flag_brecha_politica_critica"] = result["brecha_consumo_pct_dia"].abs().ge(critical_gap)
    result["flag_cambio_abrupto"] = result["cambio_consumo_pct_dia"].abs().ge(change_threshold)
    result["flag_stock_inconsistente"] = result["diferencia_conciliacion_kg"].abs().gt(1e-6)
    result["flag_mortalidad_alta"] = result["mortalidad_por_1000"].ge(2.0)

    score = pd.Series(0.0, index=result.index)
    score += result["flag_z_robusto"].astype(float) * 30
    score += result["flag_brecha_politica"].astype(float) * 15
    score += result["flag_brecha_politica_critica"].astype(float) * 20
    score += result["flag_cambio_abrupto"].astype(float) * 12
    score += result["consumo_cero_con_aves"].astype(float) * 20
    score += result["consumo_negativo"].astype(float) * 35
    score += result["consumo_sin_orden"].astype(float) * 30
    score += result["fase_multiple_dia"].astype(float) * 8
    score += result["flag_stock_inconsistente"].astype(float) * 12
    score += result["flag_mortalidad_alta"].astype(float) * 8
    result["score_reglas"] = score.clip(0, 100)

    flags = [
        "flag_z_robusto",
        "flag_brecha_politica",
        "flag_brecha_politica_critica",
        "flag_cambio_abrupto",
        "consumo_cero_con_aves",
        "consumo_negativo",
        "consumo_sin_orden",
        "fase_multiple_dia",
        "flag_stock_inconsistente",
        "flag_mortalidad_alta",
    ]
    names = {
        "flag_z_robusto": "desviación robusta",
        "flag_brecha_politica": "brecha contra política",
        "flag_brecha_politica_critica": "brecha crítica contra política",
        "flag_cambio_abrupto": "cambio abrupto",
        "consumo_cero_con_aves": "consumo cero con aves",
        "consumo_negativo": "consumo neto negativo",
        "consumo_sin_orden": "sin orden operativa",
        "fase_multiple_dia": "más de una fase el mismo día",
        "flag_stock_inconsistente": "diferencia de conciliación",
        "flag_mortalidad_alta": "mortalidad alta",
    }

    result["motivos_reglas"] = result.apply(
        lambda row: "; ".join(names[flag] for flag in flags if bool(row.get(flag, False))),
        axis=1,
    )
    return result
