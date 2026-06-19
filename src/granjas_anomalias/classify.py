from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ProjectConfig


def classify_movements(kardex: pd.DataFrame, config: ProjectConfig) -> pd.DataFrame:
    df = kardex.copy()
    sap = config.sap

    bird = str(sap["bird_material"])
    feed = set(map(str, sap["feed_materials"].keys()))
    production = set(map(str, sap["production_materials"].keys()))
    normal_eggs = set(map(str, sap["normal_egg_materials"]))
    subproducts = set(map(str, sap["subproduct_materials"]))

    df["bloque_material"] = np.select(
        [
            df["material"].eq(bird),
            df["material"].isin(feed),
            df["material"].isin(production),
        ],
        ["AVES", "ALIMENTO", "PRODUCCION"],
        default="OTROS",
    )

    movement = df["clase_movimiento"].fillna("")
    event = df["clase_transaccion_evento"].fillna("")
    material = df["material"].fillna("")

    role = pd.Series("NO_CLASIFICADO", index=df.index, dtype="string")

    def set_role(mask: pd.Series, value: str) -> None:
        role.loc[mask] = value

    # Aves
    set_role(material.eq(bird) & movement.eq("101") & event.eq("WE"), "AVES_ENTRADA")
    set_role(material.eq(bird) & movement.eq("102") & event.eq("WE"), "AVES_ENTRADA_REVERSA")
    set_role(material.eq(bird) & movement.eq("261") & event.eq("WR"), "MORTALIDAD")
    set_role(material.eq(bird) & movement.eq("262") & event.eq("WR"), "MORTALIDAD_REVERSA")
    set_role(material.eq(bird) & movement.eq("261") & event.eq("WA"), "AVES_SALIDA")
    set_role(material.eq(bird) & movement.eq("262") & event.eq("WA"), "AVES_SALIDA_REVERSA")
    set_role(material.eq(bird) & movement.isin(["641", "642", "643"]), "AVES_LOGISTICA_TRANSITO")
    set_role(material.eq(bird) & movement.isin(["511", "512", "701", "702"]), "AVES_AJUSTE_CONTEXTO")

    # Alimento
    is_feed = material.isin(feed)
    set_role(is_feed & movement.eq("101") & event.eq("WE"), "ALIMENTO_ENTRADA")
    set_role(is_feed & movement.eq("102") & event.eq("WE"), "ALIMENTO_ENTRADA_REVERSA")
    set_role(is_feed & movement.eq("261") & event.eq("WA"), "ALIMENTO_CONSUMO")
    set_role(is_feed & movement.eq("262") & event.eq("WA"), "ALIMENTO_CONSUMO_REVERSA")
    set_role(is_feed & movement.isin(["301", "311"]), "ALIMENTO_TRASPASO")
    set_role(is_feed & movement.isin(["511", "512"]), "ALIMENTO_AJUSTE")
    set_role(is_feed & movement.isin(["551", "552"]), "ALIMENTO_MERMA")
    set_role(is_feed & movement.isin(["641", "642", "643"]), "ALIMENTO_LOGISTICA")
    set_role(is_feed & movement.isin(["701", "702"]), "ALIMENTO_DIF_INVENTARIO")

    # Producción
    is_normal = material.isin(normal_eggs)
    is_subproduct = material.isin(subproducts)
    set_role(is_normal & movement.eq("101") & event.eq("WF"), "PRODUCCION_NORMAL")
    set_role(is_normal & movement.eq("102") & event.eq("WF"), "PRODUCCION_NORMAL_REVERSA")
    set_role(is_subproduct & movement.eq("531") & event.eq("WA"), "PRODUCCION_SUBPRODUCTO")
    set_role(is_subproduct & movement.eq("532") & event.eq("WA"), "PRODUCCION_SUBPRODUCTO_REVERSA")
    set_role(material.isin(production) & movement.isin(["641", "642", "643"]), "PRODUCCION_LOGISTICA")
    set_role(material.isin(production) & movement.isin(["701", "702"]), "PRODUCCION_AJUSTE_INVENTARIO")
    set_role(material.isin(production) & movement.isin(["551", "552"]), "PRODUCCION_MERMA")

    df["rol_movimiento"] = role
    df["regla_movimiento"] = (
        df["material"].fillna("")
        + "|"
        + movement
        + "|"
        + event
        + "|"
        + role
    )

    # Métricas netas específicas.
    abs_kg = df["cantidad_abs"].fillna(0.0)
    abs_units = pd.to_numeric(df["cantidad_unidades"], errors="coerce").abs().fillna(0.0)

    df["movimiento_aves_neto"] = np.select(
        [
            role.eq("AVES_ENTRADA"),
            role.eq("AVES_ENTRADA_REVERSA"),
            role.eq("MORTALIDAD"),
            role.eq("MORTALIDAD_REVERSA"),
            role.eq("AVES_SALIDA"),
            role.eq("AVES_SALIDA_REVERSA"),
        ],
        [abs_units, -abs_units, -abs_units, abs_units, -abs_units, abs_units],
        default=0.0,
    )

    df["consumo_alimento_neto_kg"] = np.select(
        [role.eq("ALIMENTO_CONSUMO"), role.eq("ALIMENTO_CONSUMO_REVERSA")],
        [abs_kg, -abs_kg],
        default=0.0,
    )

    df["produccion_neta_kg"] = np.select(
        [
            role.isin(["PRODUCCION_NORMAL", "PRODUCCION_SUBPRODUCTO"]),
            role.isin(["PRODUCCION_NORMAL_REVERSA", "PRODUCCION_SUBPRODUCTO_REVERSA"]),
        ],
        [abs_kg, -abs_kg],
        default=0.0,
    )

    raw_signed = pd.to_numeric(df["cantidad_kg"], errors="coerce").fillna(0.0)
    df["movimiento_stock_alimento_kg"] = np.select(
        [
            role.eq("ALIMENTO_ENTRADA"),
            role.eq("ALIMENTO_ENTRADA_REVERSA"),
            role.eq("ALIMENTO_CONSUMO"),
            role.eq("ALIMENTO_CONSUMO_REVERSA"),
            role.eq("ALIMENTO_AJUSTE") & movement.eq("511"),
            role.eq("ALIMENTO_AJUSTE") & movement.eq("512"),
            role.eq("ALIMENTO_MERMA") & movement.eq("551"),
            role.eq("ALIMENTO_MERMA") & movement.eq("552"),
            role.eq("ALIMENTO_DIF_INVENTARIO") & movement.eq("701"),
            role.eq("ALIMENTO_DIF_INVENTARIO") & movement.eq("702"),
            role.isin(["ALIMENTO_TRASPASO", "ALIMENTO_LOGISTICA"]),
        ],
        [abs_kg, -abs_kg, -abs_kg, abs_kg, abs_kg, -abs_kg, -abs_kg, abs_kg, abs_kg, -abs_kg, raw_signed],
        default=0.0,
    )

    phase_map = {str(k): str(v) for k, v in sap["feed_materials"].items()}
    product_map = {str(k): str(v) for k, v in sap["production_materials"].items()}
    df["fase_alimento"] = df["material"].map(phase_map).astype("string")
    df["tipo_producto"] = df["material"].map(product_map).astype("string")
    return df
