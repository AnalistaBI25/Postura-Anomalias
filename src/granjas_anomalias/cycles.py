from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ProjectConfig
from .utils import compact_unique


def detect_cycles(kardex: pd.DataFrame, config: ProjectConfig) -> pd.DataFrame:
    bird = str(config.sap["bird_material"])
    center = str(config.project["center_id"])
    start = pd.Timestamp(config.project["analysis_start"])

    entries = kardex.loc[
        kardex["centro"].eq(center)
        & kardex["material"].eq(bird)
        & kardex["rol_movimiento"].isin(["AVES_ENTRADA", "AVES_ENTRADA_REVERSA"])
        & kardex["fecha"].ge(start)
    ].copy()

    if entries.empty:
        raise ValueError("No se detectaron entradas de aves 101/102 WE dentro del scope.")

    entries["entrada_neta_aves"] = entries["movimiento_aves_neto"]
    grouped = (
        entries.groupby(["centro", "almacen", "lote", "fecha"], dropna=False)
        .agg(
            entrada_neta_aves=("entrada_neta_aves", "sum"),
            entrada_bruta_aves=("cantidad_unidades", lambda s: s.abs().sum()),
            registros_entrada=("material", "size"),
            documentos=("documento_material", compact_unique),
            referencias=("referencia", compact_unique),
        )
        .reset_index()
    )
    grouped = grouped.loc[grouped["entrada_neta_aves"] > 0].copy()
    grouped = grouped.rename(columns={"fecha": "fecha_inicio_ciclo", "almacen": "caseta"})
    grouped["aves_iniciales"] = grouped["entrada_neta_aves"]
    grouped["cycle_id"] = (
        grouped["centro"].astype(str)
        + "_"
        + grouped["caseta"].astype(str)
        + "_"
        + grouped["lote"].astype(str)
        + "_"
        + grouped["fecha_inicio_ciclo"].dt.strftime("%Y%m%d")
    )
    return grouped.sort_values(["caseta", "fecha_inicio_ciclo"]).reset_index(drop=True)


def associate_orders_and_end_dates(
    cycles: pd.DataFrame,
    kardex: pd.DataFrame,
    organization: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    result = cycles.copy()
    bird = str(config.sap["bird_material"])
    max_date = kardex["fecha"].max()

    order_rows = []
    for cycle in result.itertuples(index=False):
        candidates = kardex.loc[
            kardex["centro"].eq(cycle.centro)
            & kardex["almacen"].eq(cycle.caseta)
            & kardex["lote"].eq(cycle.lote)
            & kardex["material"].eq(bird)
            & kardex["fecha"].ge(cycle.fecha_inicio_ciclo)
            & kardex["orden"].notna()
        ].copy()

        preferred = candidates.loc[
            candidates["clase_movimiento"].isin(["261", "262"])
            & candidates["clase_transaccion_evento"].eq("WR")
        ]
        source = preferred if not preferred.empty else candidates

        if source.empty:
            order = pd.NA
            first_order_date = pd.NaT
            evidence = "sin_orden_detectada"
        else:
            first = source.sort_values("fecha").iloc[0]
            order = first["orden"]
            first_order_date = first["fecha"]
            evidence = (
                f"{first['clase_movimiento']} {first['clase_transaccion_evento']}"
            )

        order_rows.append(
            {
                "cycle_id": cycle.cycle_id,
                "orden_operativa": order,
                "fecha_primer_movimiento_orden": first_order_date,
                "evidencia_orden": evidence,
            }
        )

    result = result.merge(pd.DataFrame(order_rows), on="cycle_id", how="left")

    end_rows = []
    for cycle in result.itertuples(index=False):
        exits = kardex.loc[
            kardex["centro"].eq(cycle.centro)
            & kardex["almacen"].eq(cycle.caseta)
            & kardex["lote"].eq(cycle.lote)
            & kardex["material"].eq(bird)
            & kardex["rol_movimiento"].eq("AVES_SALIDA")
            & kardex["fecha"].ge(cycle.fecha_inicio_ciclo)
        ].copy()
        if pd.notna(cycle.orden_operativa):
            order_exits = exits.loc[exits["orden"].eq(cycle.orden_operativa)]
            if not order_exits.empty:
                exits = order_exits

        exit_daily = exits.groupby("fecha")["cantidad_unidades"].apply(
            lambda s: s.abs().sum()
        ) if not exits.empty else pd.Series(dtype=float)
        major_exits = exit_daily.loc[exit_daily >= 0.50 * float(cycle.aves_iniciales)]

        later_cycles = result.loc[
            result["caseta"].eq(cycle.caseta)
            & result["fecha_inicio_ciclo"].gt(cycle.fecha_inicio_ciclo),
            "fecha_inicio_ciclo",
        ]

        if not major_exits.empty:
            end_date = major_exits.index.min()
            status = "cerrado_confirmado"
            reason = "salida_mayor_aves_261_WA"
        elif not later_cycles.empty:
            end_date = later_cycles.min() - pd.Timedelta(days=1)
            status = "cerrado_inferido"
            reason = "dia_anterior_siguiente_parvada"
        else:
            end_date = max_date
            status = "abierto_en_proceso"
            reason = "ultima_fecha_disponible"

        end_rows.append(
            {
                "cycle_id": cycle.cycle_id,
                "fecha_fin_ciclo": pd.Timestamp(end_date),
                "fecha_corte_analisis": pd.Timestamp(end_date),
                "estado_ciclo": status,
                "motivo_fin_ciclo": reason,
            }
        )

    result = result.merge(pd.DataFrame(end_rows), on="cycle_id", how="left")

    org_center = organization.loc[
        organization["centro"].eq(str(config.project["center_id"]))
    ].copy()
    org_orders = set(org_center["orden"].dropna().astype(str))
    result["orden_en_maestro_organizacion"] = result["orden_operativa"].astype("string").isin(org_orders)
    result["duracion_dias"] = (
        result["fecha_fin_ciclo"] - result["fecha_inicio_ciclo"]
    ).dt.days + 1
    return result.sort_values(["fecha_inicio_ciclo", "caseta"]).reset_index(drop=True)
