
from __future__ import annotations

import pandas as pd
import pytest

from granjas_anomalias.daily import (
    build_daily_cycles,
    build_daily_facts,
)
from granjas_anomalias.standards import prepare_standard


# ============================================================
# Configuración mínima de pruebas
# ============================================================

class DummyConfig:
    """
    Configuración mínima para probar daily.py y productivity.py
    sin depender de archivos YAML ni rutas locales.
    """

    project = {
        "initial_age_week": 16,
        "initial_age_day": 0,
        "minimum_production_ratio_for_ica": 0.30,
    }

    raw = {
        "productivity": {
            "minimum_production_ratio_for_ica": 0.30,
            "use_daily_ica_on_first_production_day": True,
            "epsilon_kg": 1e-9,
        }
    }

    sap = {
        "bird_material": "20019",
        "feed_materials": {
            "10007": "Fase 1",
            "10008": "Fase 2",
            "10009": "Fase 3",
            "10010": "Fase 4",
            "10011": "Fase 5",
        },
        "production_materials": {
            "50012": "Huevo normal",
            "50008": "Huevo jumbo",
            "50009": "Huevo picado",
            "50010": "Huevo roto",
            "50011": "Huevo sucio",
            "50129": "Huevo clasificado",
            "50150": "Huevo libre de jaula",
        },
    }


# ============================================================
# Datos auxiliares
# ============================================================

def build_cycle() -> pd.DataFrame:
    """
    Ciclo base de tres días para la caseta 1007.
    """

    return pd.DataFrame(
        {
            "cycle_id": ["CICLO_001"],
            "centro": ["0000"],
            "caseta": ["1007"],
            "lote": ["LOTE_A"],
            "orden_operativa": ["12000000001"],
            "estado_ciclo": ["ACTIVO"],
            "aves_iniciales": [1000.0],
            "fecha_inicio_ciclo": [
                pd.Timestamp("2026-02-07")
            ],
            "fecha_corte_analisis": [
                pd.Timestamp("2026-02-09")
            ],
        }
    )


def sap_row(
    *,
    fecha: str,
    centro: str = "0000",
    almacen: str = "1007",
    material: str = "20019",
    lote: str = "LOTE_A",
    orden: str = "",
    rol_movimiento: str = "",
    cantidad_unidades: float = 0.0,
    movimiento_aves_neto: float = 0.0,
    consumo_alimento_neto_kg: float = 0.0,
    produccion_neta_kg: float = 0.0,
    clase_movimiento: str = "",
    clase_transaccion_evento: str = "",
) -> dict[str, object]:
    """
    Construye una fila compatible con el kardex clasificado.
    """

    return {
        "fecha": pd.Timestamp(fecha),
        "centro": centro,
        "almacen": almacen,
        "material": material,
        "lote": lote,
        "orden": orden,
        "rol_movimiento": rol_movimiento,
        "cantidad_unidades": cantidad_unidades,
        "movimiento_aves_neto": movimiento_aves_neto,
        "consumo_alimento_neto_kg": (
            consumo_alimento_neto_kg
        ),
        "produccion_neta_kg": produccion_neta_kg,
        "clase_movimiento": clase_movimiento,
        "clase_transaccion_evento": (
            clase_transaccion_evento
        ),
    }


def build_kardex() -> pd.DataFrame:
    """
    Kardex base con:

    - entrada de 1000 aves;
    - mortalidad de 5 aves;
    - reversa de mortalidad de 2 aves;
    - consumo de Fase 1 y Fase 2;
    - transición entre fases;
    - reversa de consumo;
    - producción normal y jumbo;
    - movimientos de otra orden que deben excluirse.
    """

    order = "12000000001"
    other_order = "12000000999"

    rows = [
        # ----------------------------------------------------
        # Aves
        # ----------------------------------------------------
        sap_row(
            fecha="2026-02-07",
            material="20019",
            almacen="1007",
            lote="LOTE_A",
            orden=order,
            rol_movimiento="ENTRADA_AVES",
            cantidad_unidades=1000.0,
            movimiento_aves_neto=1000.0,
            clase_movimiento="101",
            clase_transaccion_evento="WE",
        ),
        sap_row(
            fecha="2026-02-08",
            material="20019",
            almacen="1007",
            lote="LOTE_A",
            orden=order,
            rol_movimiento="MORTALIDAD",
            cantidad_unidades=-5.0,
            movimiento_aves_neto=-5.0,
            clase_movimiento="261",
            clase_transaccion_evento="WR",
        ),
        sap_row(
            fecha="2026-02-09",
            material="20019",
            almacen="1007",
            lote="LOTE_A",
            orden=order,
            rol_movimiento="MORTALIDAD_REVERSA",
            cantidad_unidades=2.0,
            movimiento_aves_neto=2.0,
            clase_movimiento="262",
            clase_transaccion_evento="WR",
        ),

        # ----------------------------------------------------
        # Alimento asignado a la orden correcta
        # ----------------------------------------------------
        sap_row(
            fecha="2026-02-07",
            almacen="1100",
            material="10007",
            lote="",
            orden=order,
            rol_movimiento="CONSUMO_ALIMENTO",
            cantidad_unidades=-80.0,
            consumo_alimento_neto_kg=80.0,
            clase_movimiento="261",
            clase_transaccion_evento="WA",
        ),
        sap_row(
            fecha="2026-02-08",
            almacen="1100",
            material="10007",
            lote="",
            orden=order,
            rol_movimiento="CONSUMO_ALIMENTO",
            cantidad_unidades=-20.0,
            consumo_alimento_neto_kg=20.0,
            clase_movimiento="261",
            clase_transaccion_evento="WA",
        ),
        sap_row(
            fecha="2026-02-08",
            almacen="1100",
            material="10008",
            lote="",
            orden=order,
            rol_movimiento="CONSUMO_ALIMENTO",
            cantidad_unidades=-50.0,
            consumo_alimento_neto_kg=50.0,
            clase_movimiento="261",
            clase_transaccion_evento="WA",
        ),
        sap_row(
            fecha="2026-02-09",
            almacen="1100",
            material="10008",
            lote="",
            orden=order,
            rol_movimiento="CONSUMO_ALIMENTO_REVERSA",
            cantidad_unidades=10.0,
            consumo_alimento_neto_kg=-10.0,
            clase_movimiento="262",
            clase_transaccion_evento="WA",
        ),

        # Este consumo pertenece a otra orden y debe excluirse.
        sap_row(
            fecha="2026-02-08",
            almacen="1100",
            material="10007",
            lote="",
            orden=other_order,
            rol_movimiento="CONSUMO_ALIMENTO",
            cantidad_unidades=-999.0,
            consumo_alimento_neto_kg=999.0,
            clase_movimiento="261",
            clase_transaccion_evento="WA",
        ),

        # ----------------------------------------------------
        # Producción asignada a la orden correcta
        # ----------------------------------------------------
        sap_row(
            fecha="2026-02-08",
            almacen="3401",
            material="50012",
            lote="",
            orden=order,
            rol_movimiento="PRODUCCION_HUEVO",
            cantidad_unidades=40.0,
            produccion_neta_kg=40.0,
            clase_movimiento="101",
            clase_transaccion_evento="WF",
        ),
        sap_row(
            fecha="2026-02-09",
            almacen="3401",
            material="50008",
            lote="",
            orden=order,
            rol_movimiento="PRODUCCION_SUBPRODUCTO",
            cantidad_unidades=5.0,
            produccion_neta_kg=5.0,
            clase_movimiento="531",
            clase_transaccion_evento="WA",
        ),

        # Esta producción pertenece a otra orden y debe excluirse.
        sap_row(
            fecha="2026-02-09",
            almacen="3401",
            material="50012",
            lote="",
            orden=other_order,
            rol_movimiento="PRODUCCION_HUEVO",
            cantidad_unidades=500.0,
            produccion_neta_kg=500.0,
            clase_movimiento="101",
            clase_transaccion_evento="WF",
        ),
    ]

    return pd.DataFrame(rows)


def build_standard() -> pd.DataFrame:
    """
    Política sencilla para las semanas 16 y 17.
    """

    raw = pd.DataFrame(
        {
            "Semana Edad": [16, 17],
            "Peso Corporal": [1500.0, 1550.0],
            "Mort": [0.5, 0.7],
            "Producción Ave Día": [50.0, 60.0],
            "ICA": [2.0, 2.0],
            "Consumo de Alimento Ave Día": [
                100.0,
                105.0,
            ],
            "Peso Promedio Huevo Gramos": [
                100.0,
                100.0,
            ],
            "Viabilidad": [99.5, 99.3],
        }
    )

    return prepare_standard(raw)


# ============================================================
# Pruebas del calendario y edad
# ============================================================

def test_build_daily_facts_creates_complete_calendar_and_age() -> None:
    """
    Debe existir una fila por cada día del ciclo.

    La fecha inicial corresponde a:
    semana 16, día 0.
    """

    result = build_daily_facts(
        cycles=build_cycle(),
        kardex=build_kardex(),
        config=DummyConfig(),
    )

    assert len(result) == 3

    assert result["fecha"].tolist() == [
        pd.Timestamp("2026-02-07"),
        pd.Timestamp("2026-02-08"),
        pd.Timestamp("2026-02-09"),
    ]

    assert result["dias_desde_inicio"].tolist() == [
        0,
        1,
        2,
    ]

    assert result["edad_semana"].tolist() == [
        16,
        16,
        16,
    ]

    assert result["edad_dia_semana"].tolist() == [
        0,
        1,
        2,
    ]

    assert result["cycle_id"].eq(
        "CICLO_001"
    ).all()

    assert result["centro"].eq("0000").all()
    assert result["caseta"].eq("1007").all()


# ============================================================
# Pruebas de aves y mortalidad
# ============================================================

def test_bird_balance_includes_mortality_and_reverse() -> None:
    """
    El saldo de aves debe considerar:

    - entrada inicial: +1000;
    - mortalidad: -5;
    - reversa de mortalidad: +2.
    """

    result = build_daily_facts(
        cycles=build_cycle(),
        kardex=build_kardex(),
        config=DummyConfig(),
    )

    assert result[
        "movimiento_aves_neto_dia"
    ].tolist() == pytest.approx(
        [
            1000.0,
            -5.0,
            2.0,
        ]
    )

    assert result[
        "mortalidad_dia"
    ].tolist() == pytest.approx(
        [
            0.0,
            5.0,
            -2.0,
        ]
    )

    assert result[
        "aves_disponibles"
    ].tolist() == pytest.approx(
        [
            1000.0,
            995.0,
            997.0,
        ]
    )

    assert result[
        "fuente_saldo_aves"
    ].eq(
        "movimientos_sap"
    ).all()


def test_bird_balance_uses_initial_birds_when_entry_is_missing() -> None:
    """
    Si la extracción no contiene la entrada 101 de aves,
    se utiliza aves_iniciales como respaldo.
    """

    cycle = build_cycle()

    cycle.loc[
        0,
        "fecha_corte_analisis",
    ] = pd.Timestamp("2026-02-08")

    kardex = pd.DataFrame(
        [
            sap_row(
                fecha="2026-02-07",
                material="20019",
                almacen="1007",
                lote="LOTE_A",
                orden="12000000001",
                rol_movimiento="MORTALIDAD",
                cantidad_unidades=-5.0,
                movimiento_aves_neto=-5.0,
                clase_movimiento="261",
                clase_transaccion_evento="WR",
            )
        ]
    )

    result = build_daily_facts(
        cycles=cycle,
        kardex=kardex,
        config=DummyConfig(),
    )

    assert result[
        "aves_disponibles"
    ].tolist() == pytest.approx(
        [
            995.0,
            995.0,
        ]
    )

    assert result[
        "fuente_saldo_aves"
    ].eq(
        "aves_iniciales_mas_movimientos"
    ).all()


# ============================================================
# Pruebas de consumo y fases
# ============================================================

def test_feed_is_assigned_by_order_and_detects_phase_transition() -> None:
    """
    El consumo debe filtrarse por la orden operativa.

    El día con Fase 1 y Fase 2 debe identificarse como transición.
    """

    result = build_daily_facts(
        cycles=build_cycle(),
        kardex=build_kardex(),
        config=DummyConfig(),
    )

    day_1 = result.loc[
        result["fecha"].eq(
            pd.Timestamp("2026-02-07")
        )
    ].iloc[0]

    day_2 = result.loc[
        result["fecha"].eq(
            pd.Timestamp("2026-02-08")
        )
    ].iloc[0]

    day_3 = result.loc[
        result["fecha"].eq(
            pd.Timestamp("2026-02-09")
        )
    ].iloc[0]

    assert day_1[
        "consumo_real_kg_dia"
    ] == pytest.approx(80.0)

    assert day_1[
        "consumo_10007_kg_dia"
    ] == pytest.approx(80.0)

    assert day_1[
        "fase_alimento_principal"
    ] == "Fase 1"

    assert day_1[
        "material_alimento_principal"
    ] == "10007"

    assert day_1["fases_activas_dia"] == 1
    assert not bool(day_1["es_transicion_fase"])

    # El movimiento de 999 kg de la otra orden no debe entrar.
    assert day_2[
        "consumo_real_kg_dia"
    ] == pytest.approx(70.0)

    assert day_2[
        "consumo_10007_kg_dia"
    ] == pytest.approx(20.0)

    assert day_2[
        "consumo_10008_kg_dia"
    ] == pytest.approx(50.0)

    assert day_2["fases_activas_dia"] == 2
    assert bool(day_2["es_transicion_fase"])

    assert day_2[
        "fase_alimento_principal"
    ] == "Fase 2"

    # La reversa conserva signo negativo, pero la fase sigue
    # siendo detectada mediante magnitud absoluta.
    assert day_3[
        "consumo_real_kg_dia"
    ] == pytest.approx(-10.0)

    assert day_3[
        "consumo_10008_kg_dia"
    ] == pytest.approx(-10.0)

    assert day_3[
        "fase_alimento_principal"
    ] == "Fase 2"

    assert day_3[
        "material_alimento_principal"
    ] == "10008"


# ============================================================
# Pruebas de producción
# ============================================================

def test_production_is_assigned_by_order_and_material() -> None:
    """
    La producción debe incluir solamente materiales
    y movimientos de la orden operativa del ciclo.
    """

    result = build_daily_facts(
        cycles=build_cycle(),
        kardex=build_kardex(),
        config=DummyConfig(),
    )

    day_1 = result.loc[
        result["fecha"].eq(
            pd.Timestamp("2026-02-07")
        )
    ].iloc[0]

    day_2 = result.loc[
        result["fecha"].eq(
            pd.Timestamp("2026-02-08")
        )
    ].iloc[0]

    day_3 = result.loc[
        result["fecha"].eq(
            pd.Timestamp("2026-02-09")
        )
    ].iloc[0]

    assert day_1[
        "produccion_real_kg_dia"
    ] == pytest.approx(0.0)

    assert day_2[
        "produccion_real_kg_dia"
    ] == pytest.approx(40.0)

    assert day_2[
        "produccion_50012_kg_dia"
    ] == pytest.approx(40.0)

    assert day_2[
        "tipos_huevo_activos_dia"
    ] == 1

    # La producción de 500 kg de la otra orden no debe entrar.
    assert day_3[
        "produccion_real_kg_dia"
    ] == pytest.approx(5.0)

    assert day_3[
        "produccion_50008_kg_dia"
    ] == pytest.approx(5.0)

    assert day_3[
        "produccion_50012_kg_dia"
    ] == pytest.approx(0.0)


# ============================================================
# Ciclos sin orden
# ============================================================

def test_cycle_without_order_keeps_biology_but_not_feed_or_production() -> None:
    """
    Un ciclo sin orden debe conservar aves, mortalidad y edad,
    pero no debe asignar consumo ni producción.
    """

    cycle = build_cycle()

    cycle.loc[
        0,
        "orden_operativa",
    ] = pd.NA

    result = build_daily_facts(
        cycles=cycle,
        kardex=build_kardex(),
        config=DummyConfig(),
    )

    assert not result[
        "tiene_orden_operativa"
    ].any()

    assert result[
        "ciclo_sin_orden_operativa"
    ].all()

    assert result[
        "consumo_real_kg_dia"
    ].eq(0.0).all()

    assert result[
        "produccion_real_kg_dia"
    ].eq(0.0).all()

    assert not result[
        "consumo_asignado_por_orden"
    ].any()

    assert not result[
        "produccion_asignada_por_orden"
    ].any()

    # La biología sigue disponible.
    assert result[
        "aves_disponibles"
    ].tolist() == pytest.approx(
        [
            1000.0,
            995.0,
            997.0,
        ]
    )


# ============================================================
# Contexto SAP
# ============================================================

def test_daily_facts_include_auditable_sap_context() -> None:
    """
    Deben preservarse movimientos, eventos, materiales y órdenes
    observados en cada fecha.
    """

    result = build_daily_facts(
        cycles=build_cycle(),
        kardex=build_kardex(),
        config=DummyConfig(),
    )

    day_2 = result.loc[
        result["fecha"].eq(
            pd.Timestamp("2026-02-08")
        )
    ].iloc[0]

    movements = str(
        day_2["movimientos_sap_dia"]
    )

    events = str(
        day_2["eventos_sap_dia"]
    )

    materials = str(
        day_2["materiales_sap_dia"]
    )

    orders = str(
        day_2["ordenes_sap_dia"]
    )

    assert "261" in movements

    assert (
        "WA" in events
        or "WR" in events
        or "WF" in events
    )

    assert "20019" in materials
    assert "10007" in materials
    assert "10008" in materials
    assert "50012" in materials

    assert "12000000001" in orders

    assert "documentos_sap_dia" in result.columns


# ============================================================
# Validaciones de entrada
# ============================================================

def test_duplicate_cycle_id_is_rejected() -> None:
    """
    No puede existir más de un registro para el mismo cycle_id.
    """

    cycle = build_cycle()

    duplicated = pd.concat(
        [
            cycle,
            cycle,
        ],
        ignore_index=True,
    )

    with pytest.raises(
        ValueError,
        match="cycle_id duplicados",
    ):
        build_daily_facts(
            cycles=duplicated,
            kardex=build_kardex(),
            config=DummyConfig(),
        )


def test_invalid_cycle_date_range_is_rejected() -> None:
    """
    La fecha de corte no puede ser anterior al inicio del ciclo.
    """

    cycle = build_cycle()

    cycle.loc[
        0,
        "fecha_corte_analisis",
    ] = pd.Timestamp("2026-02-01")

    with pytest.raises(
        ValueError,
        match="fecha de corte no puede ser anterior",
    ):
        build_daily_facts(
            cycles=cycle,
            kardex=build_kardex(),
            config=DummyConfig(),
        )


def test_missing_kardex_column_is_rejected() -> None:
    """
    El kardex debe contener todas las columnas mínimas
    requeridas por daily.py.
    """

    invalid_kardex = (
        build_kardex()
        .drop(
            columns=[
                "consumo_alimento_neto_kg"
            ]
        )
    )

    with pytest.raises(
        ValueError,
        match="consumo_alimento_neto_kg",
    ):
        build_daily_facts(
            cycles=build_cycle(),
            kardex=invalid_kardex,
            config=DummyConfig(),
        )


# ============================================================
# Integración con productivity.py
# ============================================================

def test_public_build_daily_cycles_returns_daily_and_weekly_outputs() -> None:
    """
    La API pública anterior debe continuar funcionando:

    daily, weekly = build_daily_cycles(...)
    """

    daily, weekly = build_daily_cycles(
        cycles=build_cycle(),
        kardex=build_kardex(),
        standard=build_standard(),
        config=DummyConfig(),
    )

    assert len(daily) == 3
    assert len(weekly) == 1

    expected_daily_columns = {
        "consumo_estandar_kg_dia",
        "produccion_estandar_kg_dia",
        "primera_fecha_produccion",
        "es_preproduccion",
        "consumo_preproductivo_kg_dia",
        "consumo_productivo_kg_dia",
        "ica_principal",
        "estado_ica",
    }

    assert expected_daily_columns.issubset(
        daily.columns
    )

    expected_weekly_columns = {
        "consumo_real_kg",
        "consumo_productivo_kg",
        "produccion_real_kg",
        "produccion_productiva_kg",
        "ica_real",
        "ica_estandar_principal",
        "brecha_ica",
        "estado_ica",
    }

    assert expected_weekly_columns.issubset(
        weekly.columns
    )

    row = weekly.iloc[0]

    # El 07 de febrero todavía es preproducción.
    # El ICA productivo usa:
    # consumo = 70 - 10 = 60 kg
    # producción = 40 + 5 = 45 kg
    assert row[
        "consumo_preproductivo_kg"
    ] == pytest.approx(80.0)

    assert row[
        "consumo_productivo_kg"
    ] == pytest.approx(60.0)

    assert row[
        "produccion_productiva_kg"
    ] == pytest.approx(45.0)

    assert row["ica_real"] == pytest.approx(
        60.0 / 45.0
    )

