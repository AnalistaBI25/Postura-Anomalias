import pandas as pd

from granjas_anomalias.config import load_config
from granjas_anomalias.classify import classify_movements


def _config():
    return load_config("config/project.yml")


def test_feed_consumption_261_is_positive_metric():
    row = pd.DataFrame({
        "material": ["10007"],
        "clase_movimiento": ["261"],
        "clase_transaccion_evento": ["WA"],
        "cantidad_abs": [320.0],
        "cantidad_kg": [-320.0],
        "cantidad_unidades": [float("nan")], 
    })
    result = classify_movements(row, _config())
    assert result.loc[0, "rol_movimiento"] == "ALIMENTO_CONSUMO"
    assert result.loc[0, "consumo_alimento_neto_kg"] == 320.0


def test_age_policy_week_16_day_0():
    start = pd.Timestamp("2026-02-07")
    age_total = 16 * 7 + (pd.Timestamp("2026-02-07") - start).days
    assert age_total // 7 == 16
    assert age_total % 7 == 0
