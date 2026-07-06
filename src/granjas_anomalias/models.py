from __future__ import annotations

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.impute import SimpleImputer
from sklearn.neighbors import LocalOutlierFactor
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

SHADOW_AGE_SEGMENTS = (
    ("16-30 semanas", float("-inf"), 30.0),
    ("31-55 semanas", 30.0, 55.0),
    ("56+ semanas", 55.0, float("inf")),
)


def _eligible_model_rows(data: pd.DataFrame) -> pd.Series:
    """Filas comparables para los detectores no supervisados."""

    return (
        data["aves_disponibles"].gt(0)
        & data["consumo_real_kg_dia"].ge(0)
        & data["dias_desde_inicio"].ge(7)
    )


def _age_segment(age: pd.Series) -> pd.Series:
    numeric_age = pd.to_numeric(age, errors="coerce")
    segment = pd.Series("sin segmento", index=age.index, dtype="object")
    for label, lower, upper in SHADOW_AGE_SEGMENTS:
        segment.loc[numeric_age.gt(lower) & numeric_age.le(upper)] = label
    return segment


def _percentile_score(raw_score: np.ndarray, index: pd.Index) -> pd.Series:
    """Convierte rareza a percentil comparable dentro del segmento."""

    return pd.Series(raw_score, index=index, dtype=float).rank(
        method="average",
        pct=True,
    ) * 100.0


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

    eligible = _eligible_model_rows(result)
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


def train_shadow_models_by_age(
    data: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    """
    Calcula detectores sombra por banda de edad.

    Estas columnas son exclusivamente comparativas: no participan en
    ``score_anomalia`` ni cambian la alerta oficial. Isolation Forest segmentado
    permite medir el efecto de no mezclar edades; LOF aporta una segunda mirada
    local para la validacion experta.
    """

    result = data.copy()
    settings = config.anomaly.get("shadow_models", {})
    enabled = bool(settings.get("enabled", True))
    contamination = float(
        settings.get(
            "contamination",
            config.anomaly.get("isolation_forest", {}).get("contamination", 0.035),
        )
    )
    n_estimators = int(settings.get("iforest_n_estimators", 300))
    random_state = int(settings.get("random_state", 42))
    requested_neighbors = int(settings.get("lof_neighbors", 35))
    minimum_rows = int(settings.get("minimum_segment_rows", 50))

    result["segmento_modelo_sombra"] = "no elegible"
    result["score_iforest_segmentado"] = 0.0
    result["flag_iforest_segmentado"] = False
    result["score_lof"] = 0.0
    result["flag_lof"] = False

    if not enabled:
        result["acuerdo_modelos"] = result["flag_ml"].astype(int)
        return result

    eligible = _eligible_model_rows(result)
    segments = _age_segment(result["edad_semana"])
    result.loc[eligible, "segmento_modelo_sombra"] = segments.loc[eligible]

    for segment_name in segments.loc[eligible].drop_duplicates():
        segment_index = result.index[
            eligible & segments.eq(segment_name)
        ]
        if len(segment_index) < minimum_rows:
            result.loc[segment_index, "segmento_modelo_sombra"] = (
                f"{segment_name} (muestra insuficiente)"
            )
            continue

        matrix = result.loc[segment_index, MODEL_FEATURES].replace(
            [np.inf, -np.inf],
            np.nan,
        )
        preprocessor = Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", RobustScaler()),
            ]
        )
        transformed = preprocessor.fit_transform(matrix)

        segmented_iforest = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=random_state,
            n_jobs=-1,
        )
        iforest_flags = segmented_iforest.fit_predict(transformed) == -1
        iforest_raw = -segmented_iforest.decision_function(transformed)
        result.loc[segment_index, "score_iforest_segmentado"] = (
            _percentile_score(iforest_raw, segment_index)
        )
        result.loc[segment_index, "flag_iforest_segmentado"] = iforest_flags

        neighbors = min(requested_neighbors, len(segment_index) - 1)
        lof = LocalOutlierFactor(
            n_neighbors=max(2, neighbors),
            contamination=contamination,
        )
        lof_flags = lof.fit_predict(transformed) == -1
        lof_raw = -lof.negative_outlier_factor_
        result.loc[segment_index, "score_lof"] = _percentile_score(
            lof_raw,
            segment_index,
        )
        result.loc[segment_index, "flag_lof"] = lof_flags

    result["flag_iforest_segmentado"] = result[
        "flag_iforest_segmentado"
    ].astype(bool)
    result["flag_lof"] = result["flag_lof"].astype(bool)
    result["acuerdo_modelos"] = (
        result["flag_ml"].astype(int)
        + result["flag_iforest_segmentado"].astype(int)
        + result["flag_lof"].astype(int)
    )
    return result


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
