
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from granjas_anomalias.productivity import (
    ProductivitySettings,
    build_productivity_outputs,
    build_weekly_productivity,
    enrich_daily_productivity,
)
from granjas_anomalias.standards import prepare_standard


class DummyConfig:
    """
    Configuración mínima para probar productivity.py
    sin depender de archivos YAML ni rutas locales.
    """

    raw = {
        "productivity": {
            "minimum_production_ratio_for_ica": 0.30,
            "use_daily_ica_on_first_production_day": True,
            "epsilon_kg": 1e-9,
        }
    }

    project = {
        "minimum_production_ratio_for_ica": 0.30,
    }

    sap: dict[str, object] = {}


class ConfigWithoutRaw:
    """
    Simula una versión anterior de ProjectConfig,
    que todavía no contiene el atributo raw.
    """

    project = {
        "minimum_production_ratio_for_ica": 0.30,
    }

    sap: dict[str, object] = {}


def build_standard() -> pd.DataFrame:
    """
    Política sencilla para 1000 aves:

    - consumo esperado: 100 kg/día;
    - producción esperada: 50 kg/día;
    - ICA esperado: 2.0.
    """

    raw = pd.DataFrame(
        {
            "Semana Edad": [16],
            "Peso Corporal": [1500.0],
            "Mort": [0.5],
            "Producción Ave Día": [50.0],
            "ICA": [2.0],
            "Consumo de Alimento Ave Día": [100.0],
            "Peso Promedio Huevo Gramos": [100.0],
            "Viabilidad": [99.5],
        }
    )

    return prepare_standard(raw)


def build_daily_facts(
    production: list[float] | None = None,
    consumption: list[float] | None = None,
) -> pd.DataFrame:
    """
    Construye siete días de hechos SAP para un ciclo.

    Por defecto:
    - días 1 a 3: preproducción;
    - día 4: primera producción;
    - días 4 a 7: producción de 50 kg;
    - consumo diario: 100 kg.
    """

    dates = pd.date_range(
        "2026-01-01",
        periods=7,
        freq="D",
    )

    if production is None:
        production = [
            0.0,
            0.0,
            0.0,
            50.0,
            50.0,
            50.0,
            50.0,
        ]

    if consumption is None:
        consumption = [
            100.0,
            100.0,
            100.0,
            100.0,
            100.0,
            100.0,
            100.0,
        ]

    return pd.DataFrame(
        {
            "cycle_id": ["CICLO_001"] * 7,
            "fecha": dates,
            "centro": ["0000"] * 7,
            "caseta": ["1007"] * 7,
            "lote": ["LOTE_001"] * 7,
            "orden_operativa": ["12000000001"] * 7,
            "estado_ciclo": ["ACTIVO"] * 7,
            "aves_iniciales": [1000.0] * 7,
            "aves_disponibles": [1000.0] * 7,
            "mortalidad_dia": [0.0] * 7,
            "consumo_real_kg_dia": consumption,
            "produccion_real_kg_dia": production,
            "edad_semana": [16] * 7,
            "edad_dia_semana": list(range(7)),
        }
    )


def test_preproductive_consumption_is_excluded_from_ica() -> None:
    """
    El consumo anterior a la primera producción debe conservarse
    como contexto, pero no debe entrar al ICA productivo.
    """

    daily, weekly = build_productivity_outputs(
        daily_facts=build_daily_facts(),
        standard=build_standard(),
        config=DummyConfig(),
    )

    assert daily[
        "consumo_preproductivo_kg_dia"
    ].sum() == pytest.approx(
        300.0
    )

    assert daily[
        "consumo_productivo_kg_dia"
    ].sum() == pytest.approx(
        400.0
    )

    row = weekly.iloc[0]

    # Consumo SAP total, incluyendo preproducción.
    assert row["consumo_real_kg"] == pytest.approx(
        700.0
    )

    # Consumo utilizado para el ICA.
    assert row[
        "consumo_productivo_kg"
    ] == pytest.approx(
        400.0
    )

    assert row[
        "produccion_productiva_kg"
    ] == pytest.approx(
        200.0
    )

    assert row["ica_real"] == pytest.approx(
        2.0
    )


def test_first_production_day_uses_sensitive_startup_ica() -> None:
    """
    El primer día con producción utiliza el ICA diario sensible.
    Los días siguientes utilizan el ICA acumulado de la semana.
    """

    daily = enrich_daily_productivity(
        daily_facts=build_daily_facts(),
        standard=build_standard(),
        config=DummyConfig(),
    )

    first_day = daily.loc[
        daily["fecha"].eq(
            pd.Timestamp("2026-01-04")
        )
    ].iloc[0]

    next_day = daily.loc[
        daily["fecha"].eq(
            pd.Timestamp("2026-01-05")
        )
    ].iloc[0]

    assert bool(
        first_day["es_primer_dia_produccion"]
    )

    assert first_day[
        "primera_fecha_produccion"
    ] == pd.Timestamp("2026-01-04")

    assert first_day[
        "estado_ica"
    ] == "Arranque sensible"

    assert first_day[
        "ica_arranque_diario"
    ] == pytest.approx(
        2.0
    )

    assert first_day[
        "ica_principal"
    ] == pytest.approx(
        2.0
    )

    assert next_day[
        "estado_ica"
    ] == "Evaluable: ICA semanal"

    assert next_day[
        "ica_principal"
    ] == pytest.approx(
        2.0
    )


def test_days_before_first_production_are_not_evaluable() -> None:
    """
    Los días anteriores a la primera producción deben quedar
    identificados como preproducción.
    """

    daily = enrich_daily_productivity(
        daily_facts=build_daily_facts(),
        standard=build_standard(),
        config=DummyConfig(),
    )

    preproduction = daily.loc[
        daily["fecha"].lt(
            pd.Timestamp("2026-01-04")
        )
    ]

    assert preproduction[
        "es_preproduccion"
    ].all()

    assert preproduction[
        "estado_ica"
    ].eq(
        "Preproducción: ICA no evaluable"
    ).all()

    assert preproduction[
        "ica_principal"
    ].isna().all()


def test_low_production_is_not_stable_for_ica() -> None:
    """
    Si la producción observada es menor al 30 % de la esperada,
    el ICA debe marcarse como no estable.
    """

    low_production = [
        0.0,
        0.0,
        0.0,
        10.0,
        10.0,
        10.0,
        10.0,
    ]

    daily, weekly = build_productivity_outputs(
        daily_facts=build_daily_facts(
            production=low_production,
        ),
        standard=build_standard(),
        config=DummyConfig(),
    )

    productive_days_after_start = daily.loc[
        daily["fecha"].gt(
            pd.Timestamp("2026-01-04")
        )
    ]

    assert productive_days_after_start[
        "estado_ica"
    ].eq(
        "No estable: producción baja vs estándar"
    ).all()

    row = weekly.iloc[0]

    assert row[
        "ratio_produccion_vs_estandar"
    ] == pytest.approx(
        0.20
    )

    assert row[
        "estado_ica"
    ] == "No estable: producción baja"

    assert not bool(
        row["es_ica_evaluable"]
    )


def test_cycle_without_production_has_no_ica() -> None:
    """
    Un ciclo sin producción conserva el consumo como preproductivo
    y no genera un ICA real.
    """

    no_production = [0.0] * 7

    daily, weekly = build_productivity_outputs(
        daily_facts=build_daily_facts(
            production=no_production,
        ),
        standard=build_standard(),
        config=DummyConfig(),
    )

    assert not daily[
        "hay_produccion"
    ].any()

    assert daily[
        "es_preproduccion"
    ].all()

    assert daily[
        "consumo_preproductivo_kg_dia"
    ].sum() == pytest.approx(
        700.0
    )

    row = weekly.iloc[0]

    assert pd.isna(
        row["ica_real"]
    )

    assert row[
        "estado_ica"
    ] == "Preproducción / ICA no evaluable"

    assert not bool(
        row["es_ica_evaluable"]
    )


def test_duplicate_cycle_date_is_rejected() -> None:
    """
    No puede existir más de una fila por ciclo y fecha.
    """

    daily = build_daily_facts()

    duplicated = pd.concat(
        [
            daily,
            daily.iloc[[0]],
        ],
        ignore_index=True,
    )

    with pytest.raises(
        ValueError,
        match="más de una fila",
    ):
        enrich_daily_productivity(
            daily_facts=duplicated,
            standard=build_standard(),
            config=DummyConfig(),
        )


def test_missing_standard_column_is_rejected() -> None:
    """
    El cálculo debe detenerse si la política no contiene
    las columnas mínimas requeridas.
    """

    invalid_standard = (
        build_standard()
        .drop(columns=["ica_sap"])
    )

    with pytest.raises(
        ValueError,
        match="ica_sap",
    ):
        enrich_daily_productivity(
            daily_facts=build_daily_facts(),
            standard=invalid_standard,
            config=DummyConfig(),
        )


def test_settings_support_config_without_raw_attribute() -> None:
    """
    ProductivitySettings debe funcionar con la versión anterior
    de ProjectConfig, que únicamente contiene project y sap.
    """

    settings = ProductivitySettings.from_config(
        ConfigWithoutRaw()
    )

    assert (
        settings.minimum_production_ratio_for_ica
        == pytest.approx(0.30)
    )

    assert (
        settings.use_daily_ica_on_first_production_day
        is True
    )

    assert settings.epsilon_kg == pytest.approx(
        1e-9
    )


def test_weekly_builder_rejects_unenriched_daily_facts() -> None:
    """
    build_weekly_productivity debe recibir la línea diaria
    ya enriquecida por productivity.py.
    """

    with pytest.raises(
        ValueError,
        match="Faltan columnas requeridas",
    ):
        build_weekly_productivity(
            daily_productivity=build_daily_facts(),
            config=DummyConfig(),
        )

