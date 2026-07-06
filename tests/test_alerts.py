from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from granjas_anomalias.alerts import (
    aplicar_consenso_capas,
    aplicar_ciclo_vida,
    construir_alertas,
    procesar_alertas,
)
from granjas_anomalias.db import Warehouse


def make_config() -> SimpleNamespace:
    return SimpleNamespace(
        project={"center_id": "1217", "farm_name": "GRANJA TEST"},
        sap={"feed_warehouse": "1100"},
        anomaly={
            "policy_gap_warning_pct": 0.15,
            "policy_gap_critical_pct": 0.30,
        },
    )


def make_scored(**overrides) -> pd.DataFrame:
    base = {
        "fecha": pd.Timestamp("2026-05-10"),
        "cycle_id": "C1",
        "caseta": "1001",
        "material_alimento_principal": "10007",
        "edad_semana": 30,
        "aves_disponibles": 5000.0,
        "consumo_real_kg_dia": 500.0,
        "consumo_estandar_kg_dia": 520.0,
        "consumo_rolling_median_28": 505.0,
        "consumo_promedio_7d": 498.0,
        "produccion_real_kg_dia": 300.0,
        "produccion_estandar_kg_dia": 310.0,
        "brecha_produccion_pct_dia": -0.03,
        "hay_produccion": True,
        "mortalidad_dia": 2.0,
        "mortalidad_estandar_acum_aves": 100.0,
        "diferencia_conciliacion_kg": 0.0,
        "fases_activas_dia": 1,
        "score_anomalia": 10.0,
        "severidad": "baja",
        "acuerdo_modelos": 0,
        # banderas
        "consumo_negativo": False,
        "consumo_sin_orden": False,
        "orden_fuera_maestro": False,
        "fase_multiple_dia": False,
        "flag_stock_inconsistente": False,
        "flag_z_robusto": False,
        "flag_cambio_abrupto": False,
        "flag_brecha_politica": False,
        "flag_brecha_politica_critica": False,
        "consumo_cero_con_aves": False,
        "flag_mortalidad_alta": False,
        "flag_ml": False,
    }
    base.update(overrides)
    return pd.DataFrame([base])


# ============================================================
# Consenso de capas
# ============================================================
def test_consenso_sin_banderas():
    resultado = aplicar_consenso_capas(make_scored(), make_config())
    fila = resultado.iloc[0]
    assert fila["n_capas"] == 0
    assert fila["severidad_consenso"] == "baja"  # nunca degrada la oficial
    assert fila["tipo_resultado"] == "OPERATIVA"


def test_consenso_solo_capa1_es_calidad_de_datos():
    resultado = aplicar_consenso_capas(
        make_scored(consumo_negativo=True), make_config()
    )
    fila = resultado.iloc[0]
    assert fila["capa1_calidad"]
    assert fila["n_capas"] == 1
    assert fila["tipo_resultado"] == "CALIDAD_DE_DATOS"


def test_consenso_tres_capas_critica():
    resultado = aplicar_consenso_capas(
        make_scored(flag_z_robusto=True, flag_brecha_politica=True, flag_ml=True),
        make_config(),
    )
    fila = resultado.iloc[0]
    assert fila["n_capas"] == 3
    assert fila["severidad_consenso"] == "critica"
    assert fila["tipo_resultado"] == "OPERATIVA"


def test_consenso_no_degrada_severidad_oficial():
    resultado = aplicar_consenso_capas(
        make_scored(severidad="critica"), make_config()
    )
    assert resultado.iloc[0]["severidad_consenso"] == "critica"


def test_consenso_produccion_baja_activa_capa3():
    resultado = aplicar_consenso_capas(
        make_scored(brecha_produccion_pct_dia=-0.5), make_config()
    )
    fila = resultado.iloc[0]
    assert fila["flag_produccion_baja"]
    assert fila["capa3_contextual"]


def test_consenso_produccion_cero_con_aves():
    resultado = aplicar_consenso_capas(
        make_scored(produccion_real_kg_dia=0.0), make_config()
    )
    assert resultado.iloc[0]["flag_produccion_cero"]


# ============================================================
# Construcción de alertas
# ============================================================
def test_construir_alertas_consumo():
    scored = aplicar_consenso_capas(
        make_scored(flag_z_robusto=True, severidad="alta"), make_config()
    )
    alertas = construir_alertas(scored, pd.DataFrame(), [], make_config(), "run1")
    assert len(alertas) == 1
    fila = alertas.iloc[0]
    assert fila["familia"] == "CONSUMO"
    assert fila["tipo"] == "CONSUMO_FUERA_DE_HISTORICO"
    assert fila["centro"] == "1217"
    assert fila["caseta"] == "1001"
    assert fila["estado"] == "nueva"
    assert fila["recomendacion"]


def test_construir_alertas_cobertura():
    eventos = [
        {
            "fecha": pd.Timestamp("2026-05-10"),
            "nivel": "global",
            "material": "(global)",
            "tipo": "RIESGO_DESABASTO",
            "tipo_resultado": "OPERATIVA",
            "severidad": "critica",
            "stock_kg": 100.0,
            "consumo_diario_estimado_kg": 100.0,
            "dias_cobertura": 1.0,
            "aves_activas": 5000.0,
            "persistencia_dias": 2,
        }
    ]
    alertas = construir_alertas(pd.DataFrame(), pd.DataFrame(), eventos, make_config(), "run1")
    assert len(alertas) == 1
    fila = alertas.iloc[0]
    assert fila["familia"] == "INVENTARIO"
    assert fila["severidad"] == "critica"
    assert fila["fecha_inicial"] == "2026-05-09"  # persistencia de 2 días


def test_construir_alertas_ica_semanal():
    weekly = pd.DataFrame(
        [
            {
                "cycle_id": "C1",
                "caseta": "1001",
                "edad_semana": 30,
                "fecha_inicio_semana": "2026-05-04",
                "fecha_fin_semana": "2026-05-10",
                "es_ica_evaluable": True,
                "ica_real": 2.4,
                "ica_estandar_principal": 2.0,
                "brecha_ica": 0.4,
                "brecha_ica_pct": 0.20,
                "aves_promedio": 5000.0,
                "semana_completa": True,
            }
        ]
    )
    alertas = construir_alertas(make_scored(), weekly, [], make_config(), "run1")
    ica = alertas.loc[alertas["familia"].eq("ICA")]
    assert len(ica) == 1
    assert ica.iloc[0]["tipo"] == "ICA_SUPERIOR_AL_ESTANDAR"
    assert ica.iloc[0]["granularidad"] == "semanal"


# ============================================================
# Ciclo de vida
# ============================================================
@pytest.fixture()
def db(tmp_path: Path) -> Warehouse:
    return Warehouse(tmp_path / "warehouse.db")


def _alertas_de(flags: dict, run_id: str, db: Warehouse) -> pd.DataFrame:
    scored = aplicar_consenso_capas(make_scored(**flags), make_config())
    return procesar_alertas(scored, pd.DataFrame(), [], make_config(), db, run_id)


def test_ciclo_vida_nueva_persistente_resuelta(db: Warehouse):
    # Corrida 1: una alerta de consumo -> nueva
    alertas1 = _alertas_de({"flag_z_robusto": True}, "run1", db)
    assert alertas1.iloc[0]["estado"] == "nueva"

    # Corrida 2: misma alerta -> persistente
    alertas2 = _alertas_de({"flag_z_robusto": True}, "run2", db)
    activa = alertas2.loc[alertas2["estado"] != "resuelta"]
    assert activa.iloc[0]["estado"] == "persistente"

    # Corrida 3: desaparece -> se registra como resuelta
    alertas3 = _alertas_de({}, "run3", db)
    assert (alertas3["estado"] == "resuelta").any()

    # Corrida 4: reaparece -> recurrente o reabierta
    alertas4 = _alertas_de({"flag_z_robusto": True}, "run4", db)
    activa4 = alertas4.loc[alertas4["estado"] != "resuelta"]
    assert activa4.iloc[0]["estado"] in {"reabierta", "recurrente"}


def test_ciclo_vida_cambio_severidad(db: Warehouse):
    _alertas_de({"flag_z_robusto": True}, "run1", db)
    alertas2 = _alertas_de(
        {"flag_z_robusto": True, "flag_brecha_politica": True, "flag_ml": True},
        "run2",
        db,
    )
    activa = alertas2.loc[alertas2["estado"] == "persistente"]
    assert not activa.empty
    assert (activa["cambio_severidad"] == "subio").any()


def test_revision_manual_persiste(db: Warehouse):
    alertas = _alertas_de({"flag_z_robusto": True}, "run1", db)
    clave = alertas.iloc[0]["clave_seguimiento"]
    db.guardar_revision(clave, "FALSO_POSITIVO", "validado en campo", "tester")
    revisiones = db.leer_revisiones()
    assert revisiones.iloc[0]["estado_manual"] == "FALSO_POSITIVO"
