from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ProjectConfig
from .utils import safe_divide


def _rolling_robust_z(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    history = series.shift(1)
    median = history.rolling(window, min_periods=min_periods).median()
    mad = (history - median).abs().rolling(window, min_periods=min_periods).median()
    scale = 1.4826 * mad
    return (series - median) / scale.where(scale > 1e-9)


def build_anomaly_features(
    daily: pd.DataFrame,
    stock_global: pd.DataFrame,
    cycles: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    features = daily.copy().sort_values(["cycle_id", "fecha"])
    window = int(config.anomaly["rolling_window_days"])
    minimum = int(config.anomaly["minimum_history_days"])

    features["consumo_g_ave_dia_real"] = 1000 * safe_divide(
        features["consumo_real_kg_dia"], features["aves_disponibles"]
    )
    features["produccion_g_ave_dia_real"] = 1000 * safe_divide(
        features["produccion_real_kg_dia"], features["aves_disponibles"]
    )
    features["mortalidad_por_1000"] = 1000 * safe_divide(
        features["mortalidad_dia"], features["aves_disponibles"]
    )

    grouped = features.groupby("cycle_id", group_keys=False)
    features["consumo_rolling_median_28"] = grouped["consumo_g_ave_dia_real"].transform(
        lambda s: s.shift(1).rolling(window, min_periods=minimum).median()
    )
    features["consumo_robust_z_28"] = grouped["consumo_g_ave_dia_real"].transform(
        lambda s: _rolling_robust_z(s, window, minimum)
    )
    features["cambio_consumo_pct_dia"] = grouped["consumo_real_kg_dia"].pct_change()
    features["consumo_promedio_7d"] = grouped["consumo_real_kg_dia"].transform(
        lambda s: s.rolling(7, min_periods=3).mean()
    )
    features["consumo_std_7d"] = grouped["consumo_real_kg_dia"].transform(
        lambda s: s.rolling(7, min_periods=3).std()
    )

    stock_cols = [
        "fecha",
        "stock_global_kg",
        "entradas_alimento_kg",
        "consumo_total_alimento_kg",
        "diferencia_conciliacion_kg",
    ]
    features = features.merge(stock_global[stock_cols], on="fecha", how="left")
    features = features.merge(
        cycles[["cycle_id", "orden_en_maestro_organizacion"]],
        on="cycle_id",
        how="left",
    )

    features["ratio_consumo_vs_estandar"] = safe_divide(
        features["consumo_real_kg_dia"], features["consumo_estandar_kg_dia"]
    )
    features["ratio_produccion_vs_estandar"] = safe_divide(
        features["produccion_real_kg_dia"], features["produccion_estandar_kg_dia"]
    )
    features["consumo_cero_con_aves"] = (
        features["aves_disponibles"].gt(0)
        & features["consumo_real_kg_dia"].abs().lt(1e-9)
    )
    features["consumo_negativo"] = features["consumo_real_kg_dia"].lt(-1e-9)
    features["consumo_sin_orden"] = features["orden_operativa"].isna()
    features["orden_fuera_maestro"] = ~features["orden_en_maestro_organizacion"].fillna(False)
    features["fase_multiple_dia"] = features["fases_activas_dia"].gt(1)
    return features
