from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import RobustScaler

from .config import ProjectConfig


MODEL_FEATURES = [
    "consumo_g_ave_dia_real",
    "brecha_consumo_pct_dia",
    "consumo_robust_z_28",
    "cambio_consumo_pct_dia",
    "consumo_promedio_7d",
    "consumo_std_7d",
    "mortalidad_por_1000",
    "ratio_produccion_vs_estandar",
    "edad_semana",
    "fases_activas_dia",
]


def train_isolation_forest(
    data: pd.DataFrame,
    config: ProjectConfig,
) -> tuple[pd.DataFrame, Path | None]:
    result = data.copy()
    settings = config.anomaly["isolation_forest"]
    if not settings.get("enabled", True):
        result["score_ml"] = 0.0
        result["flag_ml"] = False
        return result, None

    eligible = (
        result["aves_disponibles"].gt(0)
        & result["consumo_real_kg_dia"].ge(0)
        & result["dias_desde_inicio"].ge(7)
    )
    train = result.loc[eligible, MODEL_FEATURES].replace([np.inf, -np.inf], np.nan).copy()
    if len(train) < 100:
        result["score_ml"] = 0.0
        result["flag_ml"] = False
        return result, None

    model = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", RobustScaler()),
            (
                "model",
                IsolationForest(
                    n_estimators=int(settings["n_estimators"]),
                    contamination=float(settings["contamination"]),
                    random_state=int(settings["random_state"]),
                    n_jobs=-1,
                ),
            ),
        ]
    )
    model.fit(train)

    scores = pd.Series(np.nan, index=result.index, dtype=float)
    predictions = pd.Series(False, index=result.index, dtype=bool)
    matrix = result.loc[eligible, MODEL_FEATURES].replace([np.inf, -np.inf], np.nan)
    decision = -model.decision_function(matrix)
    minimum, maximum = float(decision.min()), float(decision.max())
    normalized = 100 * (decision - minimum) / max(maximum - minimum, 1e-12)
    scores.loc[eligible] = normalized
    predictions.loc[eligible] = model.predict(matrix) == -1

    result["score_ml"] = scores.fillna(0.0)
    result["flag_ml"] = predictions

    model_path = config.resolve("models_dir") / "isolation_forest_consumo.joblib"
    joblib.dump(model, model_path)
    metadata = {
        "features": MODEL_FEATURES,
        "eligible_rows": int(eligible.sum()),
        "contamination": float(settings["contamination"]),
    }
    (config.resolve("models_dir") / "isolation_forest_metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result, model_path


def combine_scores(data: pd.DataFrame, config: ProjectConfig) -> pd.DataFrame:
    result = data.copy()
    scoring = config.anomaly["scoring"]
    rule_weight = float(scoring["rule_weight"])
    ml_weight = float(scoring["ml_weight"])
    result["score_anomalia"] = (
        rule_weight * result["score_reglas"] + ml_weight * result["score_ml"]
    ).clip(0, 100)

    result["severidad"] = pd.cut(
        result["score_anomalia"],
        bins=[-0.01, scoring["medium_threshold"], scoring["high_threshold"], scoring["critical_threshold"], 100.01],
        labels=["baja", "media", "alta", "critica"],
        right=False,
    ).astype("string")
    result["es_anomalia"] = result["score_anomalia"].ge(float(scoring["medium_threshold"]))
    result["motivo_anomalia"] = np.where(
        result["flag_ml"] & result["motivos_reglas"].ne(""),
        result["motivos_reglas"] + "; patrón multivariable atípico",
        np.where(result["flag_ml"], "patrón multivariable atípico", result["motivos_reglas"]),
    )
    return result
