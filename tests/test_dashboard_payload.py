from pathlib import Path

import pandas as pd

from granjas_anomalias.config import ProjectConfig
from granjas_anomalias.dashboard_payload import _build_shared_store


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
