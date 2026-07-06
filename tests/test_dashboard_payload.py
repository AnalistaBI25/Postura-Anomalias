from pathlib import Path

import pandas as pd

from granjas_anomalias.config import ProjectConfig
from granjas_anomalias.dashboard_payload import _build_shared_store, _prepare_scores


def _config() -> ProjectConfig:
    return ProjectConfig(
        root=Path("."),
        raw={
            "project": {
                "center_id": "1217",
                "farm_name": "GRANJA PRUEBA",
                "timezone": "America/Merida",
            },
            "paths": {"standard_excel": "standard.xlsx"},
            "sap": {
                "feed_materials": {
                    "10007": "Fase 1",
                    "10008": "Fase 2",
                }
            },
            "stock": {},
            "anomaly_detection": {},
            "outputs": {},
        },
    )


def _daily() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fecha": ["2024-07-07"] * 3,
            "cycle_id": ["c1", "c2", "c3"],
            "caseta": ["1007", "1008", "1009"],
            "lote": ["l1", "l2", "l3"],
            "orden_operativa": ["o1", "o2", "o3"],
            "aves_disponibles": [1000.0, 990.0, 980.0],
            "mortalidad_dia": [0.0, 1.0, 2.0],
            "mortalidad_acum": [0.0, 1.0, 2.0],
            "consumo_real_kg_dia": [100.0, 200.0, 300.0],
            "consumo_real_kg_acum": [100.0, 200.0, 300.0],
            "consumo_10007_kg_dia": [100.0, 200.0, 300.0],
            "consumo_10008_kg_dia": [0.0, 0.0, 0.0],
            "produccion_real_kg_dia": [10.0, 20.0, 30.0],
            "produccion_real_kg_acum": [10.0, 20.0, 30.0],
            "fase_alimento_principal": ["Fase 1"] * 3,
            "material_alimento_principal": ["10007"] * 3,
            "ica_principal": [1.1, 1.2, 1.3],
            "ica_estandar_calculado": [1.0, 1.0, 1.0],
            "estado_ica": ["Evaluable"] * 3,
        }
    )


def _stock(consumption: float = 600.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fecha": pd.to_datetime(["2024-07-07"]),
            "stock_apertura": [1000.0],
            "stock": [400.0],
            "stock_esperado": [400.0],
            "entrada_alimento": [0.0],
            "consumo_global": [consumption],
            "otros_movimientos_stock": [0.0],
            "movimiento_stock_total": [-600.0],
            "variacion_stock": [-600.0],
            "diferencia_conciliacion_stock": [0.0],
        }
    )


def test_shared_store_daily_exposes_house_sums_and_global_stock() -> None:
    result = _build_shared_store(
        daily=_daily(),
        stock=_stock(),
        movement_daily=pd.DataFrame(),
        config=_config(),
    )

    day = result["daily"][0]

    assert day["consumo_por_caseta"] == {
        "1007": 100.0,
        "1008": 200.0,
        "1009": 300.0,
    }
    assert day["consumo_global_casetas"] == 600.0
    assert day["consumo_global"] == 600.0
    assert day["produccion_total"] == 60.0
    assert day["aves_total"] == 2970.0
    assert day["mortalidad_dia_total"] == 3.0
    assert day["stock_apertura"] == 1000.0
    assert day["stock"] == 400.0
    assert day["consumo_conciliado"] is True
    assert day["stock_conciliado"] is True


def test_shared_store_daily_flags_consumption_difference() -> None:
    result = _build_shared_store(
        daily=_daily(),
        stock=_stock(consumption=700.0),
        movement_daily=pd.DataFrame(),
        config=_config(),
    )

    day = result["daily"][0]

    assert day["consumo_global_casetas"] == 600.0
    assert day["consumo_global"] == 700.0
    assert day["diferencia_consumo_casetas_almacen"] == -100.0
    assert day["consumo_conciliado"] is False


def test_prepare_scores_keeps_shadow_model_fields() -> None:
    source = pd.DataFrame(
        {
            "cycle_id": ["c1"],
            "fecha": ["2024-07-07"],
            "score_anomalia": [42.0],
            "score_ml": [81.0],
            "flag_ml": [True],
            "segmento_modelo_sombra": ["16-30 semanas"],
            "score_iforest_segmentado": [92.0],
            "flag_iforest_segmentado": [True],
            "score_lof": [97.0],
            "flag_lof": [True],
            "acuerdo_modelos": [3],
        }
    )

    result = _prepare_scores(source)

    assert result.loc[0, "score_lof"] == 97.0
    assert bool(result.loc[0, "flag_lof"])
    assert result.loc[0, "segmento_modelo_sombra"] == "16-30 semanas"
    assert result.loc[0, "acuerdo_modelos"] == 3


def test_shared_store_exposes_official_and_shadow_scores_by_house() -> None:
    daily = _daily()
    daily["score_reglas"] = [20.0, 30.0, 40.0]
    daily["score_anomalia"] = [10.0, 45.0, 70.0]
    daily["severidad"] = ["baja", "media", "alta"]
    daily["es_anomalia"] = [False, True, True]
    daily["motivo_anomalia"] = ["", "regla", "regla + modelo"]
    daily["score_ml"] = [11.0, 71.0, 92.0]
    daily["flag_ml"] = [False, True, True]
    daily["segmento_modelo_sombra"] = ["16-30 semanas"] * 3
    daily["score_iforest_segmentado"] = [12.0, 75.0, 95.0]
    daily["flag_iforest_segmentado"] = [False, True, True]
    daily["score_lof"] = [15.0, 80.0, 98.0]
    daily["flag_lof"] = [False, True, True]
    daily["acuerdo_modelos"] = [0, 3, 3]

    result = _build_shared_store(
        daily=daily,
        stock=_stock(),
        movement_daily=pd.DataFrame(),
        config=_config(),
    )
    detail = result["daily"][0]["casetas_detalle"]["1009"]

    assert detail["score_anomalia"] == 70.0
    assert detail["es_anomalia"] is True
    assert detail["score_iforest"] == 92.0
    assert detail["score_iforest_segmentado"] == 95.0
    assert detail["score_lof"] == 98.0
    assert detail["acuerdo_modelos"] == 3
