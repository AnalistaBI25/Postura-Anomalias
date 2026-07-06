from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

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


def _model_lifecycle(config: ProjectConfig) -> dict[str, Any]:
    return config.raw.get("model_lifecycle", {}) or {}


def _active_model_path(config: ProjectConfig) -> Path:
    lifecycle = _model_lifecycle(config)
    return (config.root / lifecycle.get("active_model_path", "models/isolation_forest_consumo.joblib")).resolve()


def _active_metadata_path(config: ProjectConfig) -> Path:
    lifecycle = _model_lifecycle(config)
    return (config.root / lifecycle.get("metadata_path", "models/isolation_forest_metadata.json")).resolve()


def _hash_training_frame(frame: pd.DataFrame) -> str:
    normalized = frame.copy()
    normalized = normalized.reindex(sorted(normalized.columns), axis=1)
    digest = hashlib.sha256()
    digest.update(pd.util.hash_pandas_object(normalized, index=True).values.tobytes())
    return digest.hexdigest()


def _empty_ml_result(data: pd.DataFrame, status: str, reason: str = "") -> pd.DataFrame:
    result = data.copy()
    result["score_ml"] = 0.0
    result["flag_ml"] = False
    result["modelo_estado"] = status
    result["modelo_version"] = ""
    result["modelo_motivo"] = reason
    return result


def _read_model_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _score_with_loaded_model(
    data: pd.DataFrame,
    model: Pipeline,
    metadata: dict[str, Any],
    status: str,
) -> pd.DataFrame:
    result = data.copy()
    eligible = _eligible_model_rows(result)
    scores = pd.Series(np.nan, index=result.index, dtype=float)
    predictions = pd.Series(False, index=result.index, dtype=bool)

    if eligible.any():
        matrix = result.loc[eligible, MODEL_FEATURES].replace([np.inf, -np.inf], np.nan)
        decision = -model.decision_function(matrix)
        minimum = float(metadata.get("decision_min", float(decision.min())))
        maximum = float(metadata.get("decision_max", float(decision.max())))
        normalized = 100 * (decision - minimum) / max(maximum - minimum, 1e-12)
        scores.loc[eligible] = np.clip(normalized, 0, 100)
        predictions.loc[eligible] = model.predict(matrix) == -1

    result["score_ml"] = scores.fillna(0.0)
    result["flag_ml"] = predictions
    result["modelo_estado"] = status
    result["modelo_version"] = str(metadata.get("model_version", ""))
    result["modelo_motivo"] = str(metadata.get("approval_status", ""))
    return result


def train_isolation_forest(
    data: pd.DataFrame,
    config: ProjectConfig,
) -> tuple[pd.DataFrame, Path | None]:
    result = data.copy()
    settings = config.anomaly["isolation_forest"]
    if not settings.get("enabled", True):
        return _empty_ml_result(result, "DISABLED", "isolation_forest.enabled=false"), None

    eligible = _eligible_model_rows(result)
    train = result.loc[eligible, MODEL_FEATURES].replace([np.inf, -np.inf], np.nan).copy()
    if len(train) < 100:
        return _empty_ml_result(result, "INSUFFICIENT_ROWS", "Menos de 100 filas elegibles"), None

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
    generated_at = datetime.now().isoformat(timespec="seconds")
    lifecycle = _model_lifecycle(config)
    model_version = str(
        lifecycle.get("active_model_version")
        or f"iforest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    result["modelo_estado"] = "TRAINED"
    result["modelo_version"] = model_version
    result["modelo_motivo"] = str(lifecycle.get("approval_status", "validacion_pendiente"))

    model_path = _active_model_path(config)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_path)
    metadata = {
        "model_name": "isolation_forest_consumo",
        "model_version": model_version,
        "generated_at": generated_at,
        "execution_mode": "train",
        "features": MODEL_FEATURES,
        "eligible_rows": int(eligible.sum()),
        "training_rows": int(len(train)),
        "contamination": float(settings["contamination"]),
        "random_state": int(settings["random_state"]),
        "n_estimators": int(settings["n_estimators"]),
        "decision_min": minimum,
        "decision_max": maximum,
        "training_data_hash": _hash_training_frame(train),
        "score_p95": float(pd.Series(normalized).quantile(0.95)),
        "flagged_rows": int(predictions.sum()),
        "approval_status": str(lifecycle.get("approval_status", "validacion_pendiente")),
        "promotion_policy": str(lifecycle.get("promotion_policy", "manual")),
    }
    metadata_path = _active_metadata_path(config)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return result, model_path


def score_isolation_forest(
    data: pd.DataFrame,
    config: ProjectConfig,
) -> tuple[pd.DataFrame, Path | None]:
    settings = config.anomaly["isolation_forest"]
    if not settings.get("enabled", True):
        return _empty_ml_result(data, "DISABLED", "isolation_forest.enabled=false"), None

    model_path = _active_model_path(config)
    metadata_path = _active_metadata_path(config)
    if not model_path.exists():
        return (
            _empty_ml_result(
                data,
                "MODEL_MISSING",
                "Modelo activo no disponible; no se reentrena automaticamente.",
            ),
            None,
        )

    metadata = _read_model_metadata(metadata_path)
    model = joblib.load(model_path)
    scored = _score_with_loaded_model(data, model, metadata, "SCORED")
    return scored, model_path


def apply_isolation_forest(
    data: pd.DataFrame,
    config: ProjectConfig,
    mode: str | None = None,
) -> tuple[pd.DataFrame, Path | None]:
    lifecycle = _model_lifecycle(config)
    selected_mode = str(mode or lifecycle.get("mode", "train")).lower()
    if selected_mode in {"train", "training", "retrain"}:
        return train_isolation_forest(data, config)
    if selected_mode in {"score_existing", "score", "production"}:
        return score_isolation_forest(data, config)
    raise ValueError(
        "model_lifecycle.mode debe ser 'score_existing' o 'train'. "
        f"Valor recibido: {selected_mode!r}"
    )


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
