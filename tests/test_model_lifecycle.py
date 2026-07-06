from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from granjas_anomalias.config import ProjectConfig
from granjas_anomalias.models import MODEL_FEATURES, apply_isolation_forest


def _config(tmp_path: Path, mode: str) -> ProjectConfig:
    return ProjectConfig(
        root=tmp_path,
        raw={
            "project": {},
            "paths": {},
            "sap": {},
            "stock": {},
            "outputs": {},
            "anomaly_detection": {
                "isolation_forest": {
                    "enabled": True,
                    "contamination": 0.05,
                    "random_state": 11,
                    "n_estimators": 40,
                },
                "scoring": {
                    "rule_weight": 0.65,
                    "ml_weight": 0.35,
                    "medium_threshold": 40,
                    "high_threshold": 60,
                    "critical_threshold": 80,
                },
            },
            "model_lifecycle": {
                "mode": mode,
                "active_model_path": "models/test_iforest.joblib",
                "metadata_path": "models/test_iforest_metadata.json",
                "active_model_version": "test_model",
                "approval_status": "validacion_pendiente",
                "promotion_policy": "manual",
            },
        },
    )


def _model_data(rows: int = 130) -> pd.DataFrame:
    rng = np.random.default_rng(5)
    data = pd.DataFrame(
        {
            "aves_disponibles": 5000.0,
            "consumo_real_kg_dia": 400.0 + rng.normal(0, 10, rows),
            "dias_desde_inicio": np.arange(rows) + 7,
            "edad_semana": np.linspace(20, 70, rows),
        }
    )
    for column in MODEL_FEATURES:
        if column not in data.columns:
            data[column] = rng.normal(0, 1, rows)
    return data


def test_score_existing_missing_model_does_not_train(tmp_path: Path) -> None:
    config = _config(tmp_path, "score_existing")
    scored, model_path = apply_isolation_forest(_model_data(), config)

    assert model_path is None
    assert scored["score_ml"].eq(0).all()
    assert scored["flag_ml"].eq(False).all()
    assert scored["modelo_estado"].eq("MODEL_MISSING").all()
    assert not (tmp_path / "models" / "test_iforest.joblib").exists()


def test_train_mode_writes_versioned_metadata(tmp_path: Path) -> None:
    config = _config(tmp_path, "train")
    scored, model_path = apply_isolation_forest(_model_data(), config)

    metadata_path = tmp_path / "models" / "test_iforest_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert model_path is not None and model_path.exists()
    assert metadata["model_version"] == "test_model"
    assert metadata["execution_mode"] == "train"
    assert metadata["promotion_policy"] == "manual"
    assert metadata["training_rows"] >= 100
    assert scored["score_ml"].max() > 0
    assert scored["modelo_estado"].eq("TRAINED").all()
