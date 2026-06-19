
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from granjas_anomalias.standards import (
    prepare_standard,
    validate_standard,
)


def build_valid_standard_raw() -> pd.DataFrame:
    """
    Crea una política mínima válida utilizando nombres similares
    a los del archivo STANDAR SAP.
    """

    return pd.DataFrame(
        {
            "Semana Edad": [18, 19, 20],
            "Peso Corporal": [1600.0, 1650.0, 1700.0],
            "Mort": [1.0, 1.2, 1.4],
            "Producción Ave Día": [3.0, 14.0, 35.0],
            "ICA": [64.837905, 14.799154, 6.026786],
            "Consumo de Alimento Ave Día": [78.0, 84.0, 90.0],
            "Peso Promedio Huevo Gramos": [40.1, 40.55, 42.67],
            "Viabilidad": [99.0, 98.8, 98.6],
        }
    )


def test_prepare_standard_creates_canonical_columns() -> None:
    """
    Verifica que la política se normalice a las columnas canónicas
    utilizadas por el proyecto.
    """

    raw = build_valid_standard_raw()

    result = prepare_standard(raw)

    expected_columns = {
        "semana_edad",
        "peso_corporal_g",
        "mortalidad_pct_acum",
        "produccion_pct_ave_dia",
        "ica_sap",
        "consumo_g_ave_dia",
        "peso_huevo_g",
        "viabilidad_pct",
        "produccion_fraccion",
        "mortalidad_fraccion_acum",
        "viabilidad_fraccion",
        "huevos_1000_aves_dia",
        "produccion_kg_1000_aves_dia",
        "produccion_kg_1000_aves_semana",
        "consumo_kg_1000_aves_dia",
        "consumo_kg_1000_aves_semana",
        "mortalidad_aves_1000_acum",
        "aves_viables_1000",
        "ica_calculado_politica",
        "ica_estandar_principal",
        "ica_diferencia_control",
        "ica_diferencia_control_pct",
        "registros_fuente_semana",
    }

    assert expected_columns.issubset(result.columns)
    assert len(result) == 3
    assert result["semana_edad"].tolist() == [18, 19, 20]


def test_prepare_standard_calculates_policy_metrics() -> None:
    """
    Comprueba las fórmulas de consumo, producción e ICA
    para una semana conocida.
    """

    raw = build_valid_standard_raw()

    result = prepare_standard(raw)

    week_18 = result.loc[
        result["semana_edad"].eq(18)
    ].iloc[0]

    expected_production_kg = (
        1000
        * 0.03
        * 40.1
        / 1000
    )

    expected_consumption_kg = 78.0

    expected_ica = (
        expected_consumption_kg
        / expected_production_kg
    )

    assert week_18["produccion_fraccion"] == pytest.approx(
        0.03
    )

    assert week_18[
        "produccion_kg_1000_aves_dia"
    ] == pytest.approx(
        expected_production_kg
    )

    assert week_18[
        "consumo_kg_1000_aves_dia"
    ] == pytest.approx(
        expected_consumption_kg
    )

    assert week_18[
        "ica_calculado_politica"
    ] == pytest.approx(
        expected_ica,
        rel=1e-5,
    )

    assert week_18[
        "ica_estandar_principal"
    ] == pytest.approx(
        64.837905
    )


def test_prepare_standard_converts_fraction_and_kg_units() -> None:
    """
    Verifica la conversión automática de:
    - fracciones a porcentajes;
    - kilogramos a gramos.
    """

    raw = pd.DataFrame(
        {
            "Semana Edad": [30],
            "Peso Corporal kg": [1.65],
            "Mortalidad": [0.01],
            "Producción Ave Día": [0.90],
            "ICA": [2.10],
            "Consumo kg ave dia": [0.110],
            "Peso huevo kg": [0.063],
            "Viabilidad": [0.99],
        }
    )

    result = prepare_standard(raw)

    row = result.iloc[0]

    assert row["produccion_pct_ave_dia"] == pytest.approx(
        90.0
    )

    assert row["mortalidad_pct_acum"] == pytest.approx(
        1.0
    )

    assert row["viabilidad_pct"] == pytest.approx(
        99.0
    )

    assert row["consumo_g_ave_dia"] == pytest.approx(
        110.0
    )

    assert row["peso_huevo_g"] == pytest.approx(
        63.0
    )

    assert row["peso_corporal_g"] == pytest.approx(
        1650.0
    )


def test_prepare_standard_aggregates_duplicate_weeks() -> None:
    """
    Si hay varias filas para una misma semana, deben promediarse
    y conservarse como una sola semana auditable.
    """

    raw = pd.DataFrame(
        {
            "Semana Edad": [25, 25],
            "Peso Corporal": [1700.0, 1720.0],
            "Mort": [1.0, 1.2],
            "Producción Ave Día": [80.0, 82.0],
            "ICA": [2.0, 2.2],
            "Consumo de Alimento Ave Día": [105.0, 107.0],
            "Peso Promedio Huevo Gramos": [60.0, 62.0],
            "Viabilidad": [99.0, 98.8],
        }
    )

    result = prepare_standard(raw)

    assert len(result) == 1

    row = result.iloc[0]

    assert row["semana_edad"] == 25

    assert row[
        "registros_fuente_semana"
    ] == 2

    assert row[
        "consumo_g_ave_dia"
    ] == pytest.approx(
        106.0
    )

    assert row[
        "produccion_pct_ave_dia"
    ] == pytest.approx(
        81.0
    )

    assert row[
        "peso_huevo_g"
    ] == pytest.approx(
        61.0
    )


def test_prepare_standard_uses_calculated_ica_when_sap_is_missing() -> None:
    """
    Cuando el ICA SAP no está disponible, el proyecto debe utilizar
    el ICA calculado desde consumo y producción de política.
    """

    raw = build_valid_standard_raw()

    raw.loc[
        raw["Semana Edad"].eq(18),
        "ICA",
    ] = np.nan

    result = prepare_standard(raw)

    row = result.loc[
        result["semana_edad"].eq(18)
    ].iloc[0]

    assert pd.isna(row["ica_sap"])

    assert pd.notna(
        row["ica_calculado_politica"]
    )

    assert row[
        "ica_estandar_principal"
    ] == pytest.approx(
        row["ica_calculado_politica"]
    )


def test_validate_standard_returns_ok_for_valid_policy() -> None:
    """
    Una política correctamente preparada debe pasar
    las validaciones de calidad.
    """

    raw = build_valid_standard_raw()

    prepared = prepare_standard(raw)

    report = validate_standard(prepared)

    assert isinstance(report, pd.DataFrame)
    assert not report.empty

    assert (
        report["nivel"]
        .eq("OK")
        .any()
    )

    assert (
        report["codigo"]
        .eq("POLITICA_VALIDA")
        .any()
    )


def test_validate_standard_detects_invalid_values() -> None:
    """
    Comprueba que la validación detecte porcentajes fuera de rango
    y valores negativos.
    """

    raw = build_valid_standard_raw()

    prepared = prepare_standard(raw)

    prepared.loc[
        prepared.index[0],
        "produccion_pct_ave_dia",
    ] = 120.0

    prepared.loc[
        prepared.index[0],
        "consumo_g_ave_dia",
    ] = -15.0

    report = validate_standard(prepared)

    assert (
        report["nivel"]
        .eq("ERROR")
        .any()
    )

    assert (
        report["codigo"]
        .eq("RANGO_PRODUCCION_PCT_AVE_DIA")
        .any()
    )

    assert (
        report["codigo"]
        .eq("NEGATIVO_CONSUMO_G_AVE_DIA")
        .any()
    )


def test_validate_standard_detects_missing_columns() -> None:
    """
    La validación debe informar cuando recibe una tabla
    que todavía no está normalizada.
    """

    invalid = pd.DataFrame(
        {
            "semana_edad": [18, 19],
            "ica_sap": [2.0, 2.1],
        }
    )

    report = validate_standard(invalid)

    assert len(report) == 1

    row = report.iloc[0]

    assert row["nivel"] == "ERROR"
    assert row["codigo"] == "COLUMNAS_FALTANTES"
    assert row["filas_afectadas"] > 0


def test_prepare_standard_rejects_empty_dataframe() -> None:
    """
    No debe permitirse preparar una política vacía.
    """

    with pytest.raises(
        ValueError,
        match="política está vacía",
    ):
        prepare_standard(
            pd.DataFrame()
        )


def test_prepare_standard_rejects_missing_required_columns() -> None:
    """
    Debe generarse un error claro cuando la fuente no contiene
    las columnas mínimas de política.
    """

    raw = pd.DataFrame(
        {
            "Semana Edad": [18, 19],
            "ICA": [2.0, 2.1],
        }
    )

    with pytest.raises(
        ValueError,
        match="Faltan columnas de política",
    ):
        prepare_standard(raw)


def test_prepare_standard_stores_audit_metadata() -> None:
    """
    Verifica que la normalización conserve la trazabilidad
    de unidades, calidad y columnas fuente.
    """

    raw = build_valid_standard_raw()

    result = prepare_standard(raw)

    assert "unit_audit" in result.attrs
    assert "quality_report" in result.attrs
    assert "source_columns" in result.attrs

    assert isinstance(
        result.attrs["unit_audit"],
        pd.DataFrame,
    )

    assert isinstance(
        result.attrs["quality_report"],
        pd.DataFrame,
    )

    assert isinstance(
        result.attrs["source_columns"],
        dict,
    )

    source_columns = result.attrs[
        "source_columns"
    ]

    assert (
        source_columns["semana_edad"]
        == "Semana Edad"
    )

    assert (
        source_columns["ica_sap"]
        == "ICA"
    )

