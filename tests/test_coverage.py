from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from granjas_anomalias.coverage import build_coverage, eventos_cobertura


def make_config(**coverage) -> SimpleNamespace:
    base = {
        "dias_cobertura_minimo": 3,
        "dias_cobertura_objetivo": 7,
        "dias_cobertura_maximo": 15,
        "ventana_consumo_dias": 7,
        "min_dias_historia": 3,
        "dias_sin_movimiento_alerta": 5,
    }
    base.update(coverage)
    return SimpleNamespace(coverage=base)


def make_frames(
    dias: int = 15,
    stock: float = 1000.0,
    consumo: float = 100.0,
    aves: float = 5000.0,
    stock_negativo: bool = False,
):
    fechas = pd.date_range("2026-05-01", periods=dias, freq="D")
    stock_global = pd.DataFrame(
        {
            "fecha": fechas,
            "stock_global_kg": stock,
            "stock_apertura_global_kg": stock + consumo,
            "consumo_neto_calculado_kg": consumo,
            "entradas_netas_kg": 0.0,
            "stock_negativo": stock_negativo,
        }
    )
    stock_material = pd.DataFrame(
        {
            "fecha": fechas,
            "material": "10007",
            "stock_cierre_kg": stock,
            "stock_apertura_kg": stock + consumo,
            "consumo_neto_kg": consumo,
            "entradas_netas_kg": 0.0,
            "stock_negativo": stock_negativo,
        }
    )
    daily = pd.DataFrame({"fecha": fechas, "aves_disponibles": aves})
    return stock_material, stock_global, daily


def _global_ultimo(cobertura: pd.DataFrame) -> pd.Series:
    glob = cobertura.loc[cobertura["nivel"].eq("global")].sort_values("fecha")
    return glob.iloc[-1]


# ============================================================
# Cálculo base
# ============================================================
def test_dias_cobertura_calculo():
    cobertura = build_coverage(*make_frames(stock=1000.0, consumo=100.0), make_config())
    ultimo = _global_ultimo(cobertura)
    assert ultimo["consumo_diario_estimado_kg"] == pytest.approx(100.0)
    assert ultimo["dias_cobertura"] == pytest.approx(10.0)
    assert ultimo["inventario_requerido_kg"] == pytest.approx(700.0)
    assert ultimo["exceso_estimado_kg"] == pytest.approx(0.0)
    assert not ultimo["flag_sobrestock"]
    assert not ultimo["flag_desabasto"]


def test_exceso_estimado_sobre_maximo():
    cobertura = build_coverage(*make_frames(stock=5000.0, consumo=100.0), make_config())
    ultimo = _global_ultimo(cobertura)
    assert ultimo["dias_cobertura"] == pytest.approx(50.0)
    assert bool(ultimo["flag_sobrestock"])
    # exceso = stock - consumo * máximo = 5000 - 1500
    assert ultimo["exceso_estimado_kg"] == pytest.approx(3500.0)


def test_consumo_cero_no_divide(caplog):
    cobertura = build_coverage(*make_frames(stock=800.0, consumo=0.0), make_config())
    ultimo = _global_ultimo(cobertura)
    assert np.isnan(ultimo["dias_cobertura"])
    assert bool(ultimo["consumo_estimado_cero"])
    assert not bool(ultimo["flag_sobrestock"])
    assert not bool(ultimo["flag_desabasto"])


def test_historia_insuficiente():
    cobertura = build_coverage(*make_frames(dias=2), make_config())
    ultimo = _global_ultimo(cobertura)
    assert bool(ultimo["datos_insuficientes"])
    assert np.isnan(ultimo["dias_cobertura"])


# ============================================================
# Eventos de alerta
# ============================================================
def test_evento_sobrestock():
    config = make_config()
    cobertura = build_coverage(*make_frames(stock=5000.0, consumo=100.0), config)
    tipos = {e["tipo"] for e in eventos_cobertura(cobertura, config)}
    assert "SOBRESTOCK" in tipos


def test_evento_desabasto_critico():
    config = make_config()
    cobertura = build_coverage(*make_frames(stock=100.0, consumo=100.0), config)
    eventos = [e for e in eventos_cobertura(cobertura, config) if e["tipo"] == "RIESGO_DESABASTO"]
    assert eventos
    # 1 día de cobertura < mínimo/2 = 1.5 -> crítica
    assert eventos[0]["severidad"] == "critica"


def test_evento_inventario_cero_con_aves():
    config = make_config()
    cobertura = build_coverage(
        *make_frames(stock=0.0, consumo=0.0, aves=8000.0), config
    )
    tipos = {e["tipo"] for e in eventos_cobertura(cobertura, config)}
    assert "INVENTARIO_CERO_CON_AVES" in tipos


def test_evento_stock_negativo_es_calidad():
    config = make_config()
    cobertura = build_coverage(
        *make_frames(stock=-50.0, consumo=10.0, stock_negativo=True), config
    )
    eventos = [e for e in eventos_cobertura(cobertura, config) if e["tipo"] == "STOCK_NEGATIVO"]
    assert eventos
    assert all(e["tipo_resultado"] == "CALIDAD_DE_DATOS" for e in eventos)


def test_evento_sin_movimiento_material():
    config = make_config()
    stock_material, stock_global, daily = make_frames(stock=500.0, consumo=0.0, aves=0.0)
    cobertura = build_coverage(stock_material, stock_global, daily, config)
    eventos = [
        e
        for e in eventos_cobertura(cobertura, config)
        if e["tipo"] == "ALIMENTO_SIN_MOVIMIENTO"
    ]
    assert eventos
    assert eventos[0]["nivel"] == "material"
    assert eventos[0]["persistencia_dias"] >= 5
