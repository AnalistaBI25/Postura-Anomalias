
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from granjas_anomalias.stock import build_feed_stock


# ============================================================
# Configuración y datos auxiliares
# ============================================================

def make_config(
    *,
    initial_date: object = "2026-02-03",
    initial_stock: dict[str, object] | None = None,
    feed_materials: dict[str, str] | None = None,
    center: str = "0000",
    warehouse: str = "1100",
) -> SimpleNamespace:
    """
    Construye una configuración mínima para probar stock.py.
    """

    if feed_materials is None:
        feed_materials = {
            "10007": "Fase 1",
            "10008": "Fase 2",
        }

    if initial_stock is None:
        initial_stock = {
            "10007": 1000.0,
            "10008": 2000.0,
        }

    return SimpleNamespace(
        project={
            "center_id": center,
        },
        sap={
            "feed_warehouse": warehouse,
            "feed_materials": feed_materials,
        },
        stock={
            "initial_stock_date": initial_date,
            "initial_stock_kg": initial_stock,
        },
    )


def stock_row(
    *,
    fecha: str,
    centro: str = "0000",
    almacen: str = "1100",
    material: str = "10007",
    rol_movimiento: str = "",
    cantidad_abs: float = 0.0,
    movimiento_stock_alimento_kg: float = 0.0,
    consumo_alimento_neto_kg: float = 0.0,
    clase_movimiento: str = "",
    clase_transaccion_evento: str = "",
    orden: str = "",
    documento_material: str = "",
) -> dict[str, object]:
    """
    Construye una fila mínima del kardex clasificado.
    """

    return {
        "fecha": pd.Timestamp(fecha),
        "centro": centro,
        "almacen": almacen,
        "material": material,
        "rol_movimiento": rol_movimiento,
        "cantidad_abs": cantidad_abs,
        "movimiento_stock_alimento_kg": (
            movimiento_stock_alimento_kg
        ),
        "consumo_alimento_neto_kg": (
            consumo_alimento_neto_kg
        ),
        "clase_movimiento": clase_movimiento,
        "clase_transaccion_evento": (
            clase_transaccion_evento
        ),
        "orden": orden,
        "documento_material": documento_material,
    }


# ============================================================
# Saldo inicial y calendario
# ============================================================

def test_no_post_initial_movements_returns_initial_snapshot() -> None:
    """
    Si no hay movimientos posteriores a la fecha MB5B,
    debe generarse una fotografía del saldo inicial.
    """

    kardex = pd.DataFrame(
        [
            stock_row(
                fecha="2026-02-04",
                centro="9999",
                material="10007",
                rol_movimiento="ALIMENTO_ENTRADA",
                cantidad_abs=500.0,
                movimiento_stock_alimento_kg=500.0,
                clase_movimiento="101",
                clase_transaccion_evento="WE",
            )
        ]
    )

    stock_material, stock_global = build_feed_stock(
        kardex=kardex,
        config=make_config(),
    )

    assert len(stock_material) == 2
    assert len(stock_global) == 1

    assert stock_material["fecha"].eq(
        pd.Timestamp("2026-02-03")
    ).all()

    balances = (
        stock_material
        .set_index("material")["stock_cierre_kg"]
        .to_dict()
    )

    assert balances["10007"] == pytest.approx(
        1000.0
    )

    assert balances["10008"] == pytest.approx(
        2000.0
    )

    assert stock_material[
        "movimiento_stock_kg"
    ].eq(0.0).all()

    assert stock_global.iloc[0][
        "stock_global_kg"
    ] == pytest.approx(3000.0)


def test_movements_on_initial_date_are_excluded() -> None:
    """
    initial_stock_date representa el cierre validado por MB5B.

    Por ello:
    - un movimiento en la misma fecha no se vuelve a aplicar;
    - un movimiento del día siguiente sí se aplica.
    """

    config = make_config(
        feed_materials={
            "10007": "Fase 1",
        },
        initial_stock={
            "10007": 1000.0,
        },
    )

    kardex = pd.DataFrame(
        [
            stock_row(
                fecha="2026-02-03",
                material="10007",
                rol_movimiento="ALIMENTO_ENTRADA",
                cantidad_abs=500.0,
                movimiento_stock_alimento_kg=500.0,
                clase_movimiento="101",
                clase_transaccion_evento="WE",
            ),
            stock_row(
                fecha="2026-02-04",
                material="10007",
                rol_movimiento="ALIMENTO_ENTRADA",
                cantidad_abs=200.0,
                movimiento_stock_alimento_kg=200.0,
                clase_movimiento="101",
                clase_transaccion_evento="WE",
            ),
        ]
    )

    stock_material, _ = build_feed_stock(
        kardex=kardex,
        config=config,
    )

    initial_day = stock_material.loc[
        stock_material["fecha"].eq(
            pd.Timestamp("2026-02-03")
        )
    ].iloc[0]

    next_day = stock_material.loc[
        stock_material["fecha"].eq(
            pd.Timestamp("2026-02-04")
        )
    ].iloc[0]

    assert initial_day[
        "movimiento_stock_kg"
    ] == pytest.approx(0.0)

    assert initial_day[
        "stock_cierre_kg"
    ] == pytest.approx(1000.0)

    assert next_day[
        "entrada_101_we_kg"
    ] == pytest.approx(200.0)

    assert next_day[
        "stock_apertura_kg"
    ] == pytest.approx(1000.0)

    assert next_day[
        "stock_cierre_kg"
    ] == pytest.approx(1200.0)


# ============================================================
# Entrada de alimento
# ============================================================

def test_entry_101_we_24290_updates_stock() -> None:
    """
    Valida el evento de referencia del proyecto:

    fecha de referencia:
    entrada 101 WE con cantidad controlada.
    """

    config = make_config(
        feed_materials={
            "10007": "Fase 1",
        },
        initial_stock={
            "10007": 0.0,
        },
    )

    kardex = pd.DataFrame(
        [
            stock_row(
                fecha="2026-02-04",
                material="10007",
                rol_movimiento="ALIMENTO_ENTRADA",
                cantidad_abs=24290.0,
                movimiento_stock_alimento_kg=24290.0,
                clase_movimiento="101",
                clase_transaccion_evento="WE",
                documento_material="DOC_24290",
            )
        ]
    )

    stock_material, stock_global = build_feed_stock(
        kardex=kardex,
        config=config,
    )

    material_day = stock_material.loc[
        stock_material["fecha"].eq(
            pd.Timestamp("2026-02-04")
        )
    ].iloc[0]

    global_day = stock_global.loc[
        stock_global["fecha"].eq(
            pd.Timestamp("2026-02-04")
        )
    ].iloc[0]

    assert material_day[
        "entrada_101_we_kg"
    ] == pytest.approx(24290.0)

    assert material_day[
        "movimiento_stock_kg"
    ] == pytest.approx(24290.0)

    assert material_day[
        "stock_cierre_kg"
    ] == pytest.approx(24290.0)

    assert global_day[
        "entradas_alimento_kg"
    ] == pytest.approx(24290.0)

    assert global_day[
        "stock_global_kg"
    ] == pytest.approx(24290.0)

    assert global_day[
        "diferencia_conciliacion_kg"
    ] == pytest.approx(0.0)


# ============================================================
# Consumo y reversas
# ============================================================

def test_consumption_and_reverse_are_split_without_double_counting() -> None:
    """
    El consumo 261 y su reversa 262 deben desglosarse,
    pero el saldo físico debe usar una sola vez el movimiento
    oficial movimiento_stock_alimento_kg.
    """

    config = make_config(
        feed_materials={
            "10007": "Fase 1",
        },
        initial_stock={
            "10007": 1000.0,
        },
    )

    kardex = pd.DataFrame(
        [
            stock_row(
                fecha="2026-02-04",
                material="10007",
                rol_movimiento="CONSUMO_ALIMENTO",
                cantidad_abs=100.0,
                movimiento_stock_alimento_kg=-100.0,
                consumo_alimento_neto_kg=100.0,
                clase_movimiento="261",
                clase_transaccion_evento="WA",
                orden="12000000001",
            ),
            stock_row(
                fecha="2026-02-04",
                material="10007",
                rol_movimiento="CONSUMO_ALIMENTO_REVERSA",
                cantidad_abs=20.0,
                movimiento_stock_alimento_kg=20.0,
                consumo_alimento_neto_kg=-20.0,
                clase_movimiento="262",
                clase_transaccion_evento="WA",
                orden="12000000001",
            ),
        ]
    )

    stock_material, stock_global = build_feed_stock(
        kardex=kardex,
        config=config,
    )

    row = stock_material.loc[
        stock_material["fecha"].eq(
            pd.Timestamp("2026-02-04")
        )
    ].iloc[0]

    assert row["consumo_261_kg"] == pytest.approx(
        100.0
    )

    assert row[
        "reversa_consumo_262_kg"
    ] == pytest.approx(20.0)

    assert row[
        "consumo_neto_calculado_kg"
    ] == pytest.approx(80.0)

    assert row[
        "consumo_neto_fuente_kg"
    ] == pytest.approx(80.0)

    assert row[
        "movimiento_stock_kg"
    ] == pytest.approx(-80.0)

    assert row[
        "stock_cierre_kg"
    ] == pytest.approx(920.0)

    assert row[
        "diferencia_consumo_neto_kg"
    ] == pytest.approx(0.0)

    assert row[
        "diferencia_desglose_movimientos_kg"
    ] == pytest.approx(0.0)

    global_row = stock_global.loc[
        stock_global["fecha"].eq(
            pd.Timestamp("2026-02-04")
        )
    ].iloc[0]

    assert global_row[
        "consumo_total_alimento_kg"
    ] == pytest.approx(80.0)

    assert global_row[
        "stock_global_kg"
    ] == pytest.approx(920.0)


# ============================================================
# Otros movimientos físicos
# ============================================================

def test_other_physical_movement_preserves_its_sign() -> None:
    """
    Traspasos y ajustes no clasificados como 101/102/261/262
    deben conservar el signo físico de SAP.
    """

    config = make_config(
        feed_materials={
            "10007": "Fase 1",
        },
        initial_stock={
            "10007": 1000.0,
        },
    )

    kardex = pd.DataFrame(
        [
            stock_row(
                fecha="2026-02-04",
                material="10007",
                rol_movimiento="TRASPASO_ALIMENTO",
                cantidad_abs=50.0,
                movimiento_stock_alimento_kg=50.0,
                clase_movimiento="311",
                clase_transaccion_evento="WA",
            )
        ]
    )

    stock_material, _ = build_feed_stock(
        kardex=kardex,
        config=config,
    )

    row = stock_material.loc[
        stock_material["fecha"].eq(
            pd.Timestamp("2026-02-04")
        )
    ].iloc[0]

    assert row[
        "otros_movimientos_stock_kg"
    ] == pytest.approx(50.0)

    assert row[
        "movimiento_stock_reconstruido_kg"
    ] == pytest.approx(50.0)

    assert row[
        "stock_cierre_kg"
    ] == pytest.approx(1050.0)

    assert row[
        "diferencia_desglose_movimientos_kg"
    ] == pytest.approx(0.0)


# ============================================================
# Alcance del almacén
# ============================================================

def test_scope_filters_center_warehouse_and_material() -> None:
    """
    Solo deben entrar movimientos del:

    - centro configurado;
    - almacén de alimento configurado;
    - material de alimento configurado.
    """

    config = make_config(
        feed_materials={
            "10007": "Fase 1",
        },
        initial_stock={
            "10007": 0.0,
        },
    )

    kardex = pd.DataFrame(
        [
            stock_row(
                fecha="2026-02-04",
                centro="0000",
                almacen="1100",
                material="10007",
                rol_movimiento="ALIMENTO_ENTRADA",
                cantidad_abs=100.0,
                movimiento_stock_alimento_kg=100.0,
                clase_movimiento="101",
                clase_transaccion_evento="WE",
            ),
            stock_row(
                fecha="2026-02-04",
                centro="9999",
                almacen="1100",
                material="10007",
                rol_movimiento="ALIMENTO_ENTRADA",
                cantidad_abs=900.0,
                movimiento_stock_alimento_kg=900.0,
                clase_movimiento="101",
                clase_transaccion_evento="WE",
            ),
            stock_row(
                fecha="2026-02-04",
                centro="0000",
                almacen="9999",
                material="10007",
                rol_movimiento="ALIMENTO_ENTRADA",
                cantidad_abs=800.0,
                movimiento_stock_alimento_kg=800.0,
                clase_movimiento="101",
                clase_transaccion_evento="WE",
            ),
            stock_row(
                fecha="2026-02-04",
                centro="0000",
                almacen="1100",
                material="99999",
                rol_movimiento="ALIMENTO_ENTRADA",
                cantidad_abs=700.0,
                movimiento_stock_alimento_kg=700.0,
                clase_movimiento="101",
                clase_transaccion_evento="WE",
            ),
        ]
    )

    stock_material, stock_global = build_feed_stock(
        kardex=kardex,
        config=config,
    )

    day = stock_material.loc[
        stock_material["fecha"].eq(
            pd.Timestamp("2026-02-04")
        )
    ].iloc[0]

    assert day[
        "entrada_101_we_kg"
    ] == pytest.approx(100.0)

    assert day[
        "stock_cierre_kg"
    ] == pytest.approx(100.0)

    assert stock_global.iloc[-1][
        "stock_global_kg"
    ] == pytest.approx(100.0)


# ============================================================
# Saldo inicial faltante
# ============================================================

def test_missing_initial_balance_is_flagged() -> None:
    """
    Un material configurado sin saldo inicial no debe desaparecer.

    Debe mantenerse con saldo cero y marcarse para revisión.
    """

    config = make_config(
        feed_materials={
            "10007": "Fase 1",
            "10008": "Fase 2",
        },
        initial_stock={
            "10007": 1000.0,
        },
    )

    kardex = pd.DataFrame(
        [
            stock_row(
                fecha="2026-02-04",
                centro="9999",
                material="10007",
            )
        ]
    )

    stock_material, stock_global = build_feed_stock(
        kardex=kardex,
        config=config,
    )

    material_10008 = stock_material.loc[
        stock_material["material"].eq(
            "10008"
        )
    ].iloc[0]

    assert material_10008[
        "stock_inicial_kg"
    ] == pytest.approx(0.0)

    assert bool(
        material_10008[
            "stock_inicial_faltante"
        ]
    )

    assert not bool(
        material_10008[
            "saldo_inicial_configurado"
        ]
    )

    global_row = stock_global.iloc[0]

    assert global_row[
        "materiales_sin_saldo_inicial"
    ] == 1

    assert not bool(
        global_row[
            "saldo_inicial_completo"
        ]
    )


# ============================================================
# Stock negativo
# ============================================================

def test_negative_stock_is_flagged() -> None:
    """
    Un consumo mayor al saldo disponible debe producir
    una señal explícita de stock negativo.
    """

    config = make_config(
        feed_materials={
            "10007": "Fase 1",
        },
        initial_stock={
            "10007": 50.0,
        },
    )

    kardex = pd.DataFrame(
        [
            stock_row(
                fecha="2026-02-04",
                material="10007",
                rol_movimiento="CONSUMO_ALIMENTO",
                cantidad_abs=100.0,
                movimiento_stock_alimento_kg=-100.0,
                consumo_alimento_neto_kg=100.0,
                clase_movimiento="261",
                clase_transaccion_evento="WA",
            )
        ]
    )

    stock_material, stock_global = build_feed_stock(
        kardex=kardex,
        config=config,
    )

    material_day = stock_material.loc[
        stock_material["fecha"].eq(
            pd.Timestamp("2026-02-04")
        )
    ].iloc[0]

    global_day = stock_global.loc[
        stock_global["fecha"].eq(
            pd.Timestamp("2026-02-04")
        )
    ].iloc[0]

    assert material_day[
        "stock_cierre_kg"
    ] == pytest.approx(-50.0)

    assert bool(
        material_day["stock_negativo"]
    )

    assert bool(
        global_day["stock_negativo"]
    )

    assert global_day[
        "materiales_stock_negativo"
    ] == 1


# ============================================================
# Conciliación global
# ============================================================

def test_global_stock_matches_sum_of_materials_and_reconciles() -> None:
    """
    El stock global debe ser exactamente la suma del stock
    de todos los materiales en cada fecha.
    """

    config = make_config(
        initial_stock={
            "10007": 1000.0,
            "10008": 2000.0,
        }
    )

    kardex = pd.DataFrame(
        [
            stock_row(
                fecha="2026-02-04",
                material="10007",
                rol_movimiento="ALIMENTO_ENTRADA",
                cantidad_abs=100.0,
                movimiento_stock_alimento_kg=100.0,
                clase_movimiento="101",
                clase_transaccion_evento="WE",
            ),
            stock_row(
                fecha="2026-02-04",
                material="10008",
                rol_movimiento="ALIMENTO_ENTRADA",
                cantidad_abs=200.0,
                movimiento_stock_alimento_kg=200.0,
                clase_movimiento="101",
                clase_transaccion_evento="WE",
            ),
            stock_row(
                fecha="2026-02-05",
                material="10007",
                rol_movimiento="CONSUMO_ALIMENTO",
                cantidad_abs=50.0,
                movimiento_stock_alimento_kg=-50.0,
                consumo_alimento_neto_kg=50.0,
                clase_movimiento="261",
                clase_transaccion_evento="WA",
            ),
            stock_row(
                fecha="2026-02-05",
                material="10008",
                rol_movimiento="CONSUMO_ALIMENTO",
                cantidad_abs=80.0,
                movimiento_stock_alimento_kg=-80.0,
                consumo_alimento_neto_kg=80.0,
                clase_movimiento="261",
                clase_transaccion_evento="WA",
            ),
        ]
    )

    stock_material, stock_global = build_feed_stock(
        kardex=kardex,
        config=config,
    )

    material_sum = (
        stock_material
        .groupby("fecha", as_index=False)[
            "stock_cierre_kg"
        ]
        .sum()
        .rename(
            columns={
                "stock_cierre_kg":
                    "suma_materiales_kg",
            }
        )
    )

    validation = stock_global.merge(
        material_sum,
        on="fecha",
        how="left",
        validate="one_to_one",
    )

    assert np.allclose(
        validation["stock_global_kg"],
        validation["suma_materiales_kg"],
    )

    assert np.allclose(
        stock_global[
            "stock_apertura_global_kg"
        ]
        + stock_global[
            "movimiento_stock_total_kg"
        ],
        stock_global["stock_global_kg"],
    )

    assert stock_material[
        "diferencia_conciliacion_kg"
    ].abs().max() == pytest.approx(0.0)

    assert stock_global[
        "diferencia_conciliacion_kg"
    ].abs().max() == pytest.approx(0.0)

    assert stock_global[
        "diferencia_movimiento_variacion_kg"
    ].abs().max() == pytest.approx(0.0)


# ============================================================
# Trazabilidad SAP
# ============================================================

def test_sap_metadata_is_preserved() -> None:
    """
    La salida debe conservar movimientos, eventos,
    roles, órdenes y documentos SAP.
    """

    config = make_config(
        feed_materials={
            "10007": "Fase 1",
        },
        initial_stock={
            "10007": 0.0,
        },
    )

    kardex = pd.DataFrame(
        [
            stock_row(
                fecha="2026-02-04",
                material="10007",
                rol_movimiento="ALIMENTO_ENTRADA",
                cantidad_abs=500.0,
                movimiento_stock_alimento_kg=500.0,
                clase_movimiento="101",
                clase_transaccion_evento="WE",
                orden="ORDEN_001",
                documento_material="DOC_001",
            )
        ]
    )

    stock_material, stock_global = build_feed_stock(
        kardex=kardex,
        config=config,
    )

    material_day = stock_material.loc[
        stock_material["fecha"].eq(
            pd.Timestamp("2026-02-04")
        )
    ].iloc[0]

    assert "101" in str(
        material_day["movimientos_sap"]
    )

    assert "WE" in str(
        material_day["eventos_sap"]
    )

    assert "ALIMENTO_ENTRADA" in str(
        material_day["roles_sap"]
    )

    assert "ORDEN_001" in str(
        material_day["ordenes_sap"]
    )

    assert "DOC_001" in str(
        material_day["documentos_sap"]
    )

    global_day = stock_global.loc[
        stock_global["fecha"].eq(
            pd.Timestamp("2026-02-04")
        )
    ].iloc[0]

    assert "101" in str(
        global_day["movimientos_sap"]
    )

    assert "DOC_001" in str(
        global_day["documentos_sap"]
    )


# ============================================================
# Validaciones de kardex y configuración
# ============================================================

def test_missing_kardex_column_is_rejected() -> None:
    """
    Debe fallar claramente cuando falta una columna obligatoria.
    """

    kardex = pd.DataFrame(
        [
            stock_row(
                fecha="2026-02-04",
            )
        ]
    ).drop(
        columns=[
            "movimiento_stock_alimento_kg",
        ]
    )

    with pytest.raises(
        ValueError,
        match="movimiento_stock_alimento_kg",
    ):
        build_feed_stock(
            kardex=kardex,
            config=make_config(),
        )


def test_invalid_initial_stock_date_is_rejected() -> None:
    """
    La fecha inicial MB5B debe ser válida.
    """

    kardex = pd.DataFrame(
        [
            stock_row(
                fecha="2026-02-04",
            )
        ]
    )

    config = make_config(
        initial_date="FECHA_INVALIDA",
    )

    with pytest.raises(
        ValueError,
        match="initial_stock_date",
    ):
        build_feed_stock(
            kardex=kardex,
            config=config,
        )


def test_non_numeric_initial_stock_is_rejected() -> None:
    """
    Todos los saldos iniciales deben ser numéricos.
    """

    kardex = pd.DataFrame(
        [
            stock_row(
                fecha="2026-02-04",
            )
        ]
    )

    config = make_config(
        initial_stock={
            "10007": "NO_NUMERICO",
        },
        feed_materials={
            "10007": "Fase 1",
        },
    )

    with pytest.raises(
        ValueError,
        match="no es numérico",
    ):
        build_feed_stock(
            kardex=kardex,
            config=config,
        )

