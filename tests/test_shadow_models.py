from pathlib import Path

import numpy as np
import pandas as pd

from granjas_anomalias.config import ProjectConfig
from granjas_anomalias.models import MODEL_FEATURES, train_shadow_models_by_age


def _config() -> ProjectConfig:
    return ProjectConfig(
        root=Path("."),
        raw={
            "project": {},
            "paths": {},
            "sap": {},
            "stock": {},
            "outputs": {},
            "anomaly_detection": {
                "isolation_forest": {"contamination": 0.05},
                "shadow_models": {
                    "enabled": True,
                    "contamination": 0.05,
                    "random_state": 7,
                    "iforest_n_estimators": 80,
                    "lof_neighbors": 15,
                    "minimum_segment_rows": 30,
                },
            },
        },
    )


def _model_data() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    ages = np.concatenate(
        [
            np.linspace(16, 30, 70),
            np.linspace(31, 55, 70),
            np.linspace(56, 90, 70),
        ]
    )
    rows = len(ages)
    data = pd.DataFrame(
        {
            "aves_disponibles": 5000.0,
            "consumo_real_kg_dia": 400.0 + rng.normal(0, 12, rows),
            "dias_desde_inicio": np.arange(rows) + 7,
            "edad_semana": ages,
            "flag_ml": False,
            "score_anomalia": np.linspace(0, 50, rows),
        }
    )
    for column in MODEL_FEATURES:
        if column not in data.columns:
            data[column] = rng.normal(0, 1, rows)

    # Un caso extremo por banda para comprobar que los detectores reaccionan.
    for index in (69, 139, 209):
        data.loc[index, "consumo_g_ave_dia_real"] = 500.0
        data.loc[index, "consumo_robust_z_28"] = 12.0
        data.loc[index, "mortalidad_por_1000"] = 80.0
    data.loc[[10, 80, 150], "flag_ml"] = True
    return data


def test_shadow_models_are_segmented_and_do_not_replace_official_score() -> None:
    source = _model_data()
    result = train_shadow_models_by_age(source, _config())

    assert result["score_anomalia"].equals(source["score_anomalia"])
    assert set(result["segmento_modelo_sombra"].unique()) == {
        "16-30 semanas",
        "31-55 semanas",
        "56+ semanas",
    }
    assert result["flag_iforest_segmentado"].sum() > 0
    assert result["flag_lof"].sum() > 0
    assert result["acuerdo_modelos"].between(0, 3).all()


def test_shadow_models_flag_injected_extremes() -> None:
    result = train_shadow_models_by_age(_model_data(), _config())

    for index in (69, 139, 209):
        assert bool(
            result.loc[index, "flag_iforest_segmentado"]
            or result.loc[index, "flag_lof"]
        )

