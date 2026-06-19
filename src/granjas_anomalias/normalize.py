from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ProjectConfig
from .utils import clean_key, normalize_text, parse_dates, parse_sap_number


SOURCE_COLUMN_ALIASES = {
    "material": "material",
    "descripcion_material": "descripcion_material",
    "centro": "centro",
    "almacen": "almacen",
    "lote": "lote",
    "documento_material": "documento_material",
    "ctd_en_um_entrada": "cantidad_um_entrada",
    "un_medida_de_entrada": "unidad_medida_entrada",
    "ctd_en_ump": "cantidad_ump",
    "unidad_medida_paral": "unidad_medida_paralela",
    "clase_de_movimiento": "clase_movimiento",
    "texto_clase_de_mov": "texto_clase_movimiento",
    "fecha_contabiliz": "fecha",
    "referencia": "referencia",
    "nombre_del_usuario": "usuario",
    "orden": "orden",
    "centro_receptor": "centro_receptor",
    "clase_de_trans_eve": "clase_transaccion_evento",
    "indicador_debe_haber": "indicador_debe_haber",
    "cantidad": "cantidad",
    "texto_cab_documento": "texto_cabecera",
    "texto": "texto_posicion",
    "motivo_movimiento": "motivo_movimiento",
}


def _rename_source_columns(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {}
    for column in df.columns:
        normalized = normalize_text(column)
        rename_map[column] = SOURCE_COLUMN_ALIASES.get(normalized, normalized)
    return df.rename(columns=rename_map)


def _choose_quantity_kg(df: pd.DataFrame) -> pd.Series:
    entry = pd.to_numeric(df.get("cantidad_um_entrada"), errors="coerce")
    parallel = pd.to_numeric(df.get("cantidad_ump"), errors="coerce")
    fallback = pd.to_numeric(df.get("cantidad"), errors="coerce")

    entry_unit = df.get("unidad_medida_entrada", pd.Series("", index=df.index))
    parallel_unit = df.get("unidad_medida_paralela", pd.Series("", index=df.index))
    entry_unit = entry_unit.astype("string").str.upper().fillna("")
    parallel_unit = parallel_unit.astype("string").str.upper().fillna("")

    result = pd.Series(np.nan, index=df.index, dtype="float64")
    result = result.mask(parallel_unit.eq("KG") & parallel.notna(), parallel)
    result = result.mask(result.isna() & entry_unit.eq("KG") & entry.notna(), entry)
    result = result.fillna(fallback)
    return result


def normalize_kardex(raw: pd.DataFrame, config: ProjectConfig) -> pd.DataFrame:
    df = _rename_source_columns(raw.copy())

    required = [
        "material",
        "centro",
        "almacen",
        "lote",
        "clase_movimiento",
        "fecha",
        "orden",
        "clase_transaccion_evento",
    ]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"Faltan columnas obligatorias en MB51: {missing}")

    for column in [
        "material",
        "centro",
        "almacen",
        "lote",
        "documento_material",
        "orden",
        "centro_receptor",
        "referencia",
    ]:
        if column in df.columns:
            df[column] = df[column].map(clean_key).astype("string")

    df["clase_movimiento"] = (
        df["clase_movimiento"].map(clean_key).astype("string").str.upper()
    )
    df["clase_transaccion_evento"] = (
        df["clase_transaccion_evento"].astype("string").str.strip().str.upper()
    )
    df["indicador_debe_haber"] = (
        df.get("indicador_debe_haber", pd.Series("", index=df.index))
        .astype("string")
        .str.strip()
        .str.upper()
    )
    df["fecha"] = parse_dates(df["fecha"])

    for column in ["cantidad_um_entrada", "cantidad_ump", "cantidad"]:
        if column in df.columns:
            df[column] = df[column].map(parse_sap_number)

    df["cantidad_kg"] = _choose_quantity_kg(df)
    df["cantidad_abs"] = df["cantidad_kg"].abs()

    bird_material = str(config.sap["bird_material"])
    entry_qty = pd.to_numeric(df.get("cantidad_um_entrada"), errors="coerce")
    fallback_qty = pd.to_numeric(df.get("cantidad"), errors="coerce")
    df["cantidad_unidades"] = np.where(
        df["material"].eq(bird_material).fillna(False),
        entry_qty.fillna(fallback_qty),
        np.nan,
    )

    start = pd.Timestamp(config.project["analysis_start"])
    end_raw = config.project.get("analysis_end")
    end = pd.Timestamp(end_raw) if end_raw else None

    df = df.loc[df["fecha"].notna()].copy()
    if end is not None:
        df = df.loc[df["fecha"].between(start, end)].copy()
    else:
        # Se conservan algunos días previos al scope para anclas y asociación.
        df = df.loc[df["fecha"].ge(start - pd.Timedelta(days=30))].copy()

    df = df.sort_values(["fecha", "centro", "almacen", "material"]).reset_index(drop=True)
    return df


def normalize_organization(
    organization_raw: pd.DataFrame,
    materials_raw: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    organization = organization_raw.copy()
    organization.columns = [normalize_text(c) for c in organization.columns]
    organization = organization.rename(
        columns={
            "granja_nombre": "granja",
            "modulo": "modulo",
            "almacen": "almacen",
            "orden": "orden",
            "centro": "centro",
        }
    )
    for column in ["centro", "almacen", "orden", "modulo"]:
        if column in organization.columns:
            organization[column] = organization[column].map(clean_key).astype("string")

    materials = materials_raw.copy()
    materials.columns = [normalize_text(c) for c in materials.columns]
    materials = materials.rename(
        columns={
            "materiales": "material",
            "categoria": "categoria_maestra",
            "descripcion": "descripcion_maestra",
        }
    )
    materials["material"] = materials["material"].map(clean_key).astype("string")
    return organization, materials
