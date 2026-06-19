from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import ProjectConfig


KARDEX_REQUIRED_SOURCE_COLUMNS = [
    "Material",
    "Descripción material",
    "Centro",
    "Almacén",
    "Lote",
    "Documento material",
    "Ctd.en UM entrada",
    "Un.medida de entrada",
    "Ctd.en UMP",
    "Unidad medida paral.",
    "Clase de movimiento",
    "Texto clase de mov.",
    "Fecha contabiliz.",
    "Referencia",
    "Nombre del usuario",
    "Orden",
    "Centro receptor",
    "Clase de trans./eve.",
    "Indicador Debe/Haber",
    "Cantidad",
    "Texto cab.documento",
    "Texto",
    "Motivo movimiento",
]


def load_kardex(config: ProjectConfig) -> tuple[pd.DataFrame, str]:
    cache_path = config.resolve("kardex_cache_csv")
    excel_path = config.resolve("kardex_excel")

    if cache_path.exists():
        df = pd.read_csv(cache_path, low_memory=False)
        return df, f"cache_csv:{cache_path.name}"

    if not excel_path.exists():
        raise FileNotFoundError(f"No existe el kardex: {excel_path}")

    df = pd.read_excel(excel_path, sheet_name="Data")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(cache_path, index=False, encoding="utf-8-sig")
    return df, f"excel:{excel_path.name}"


def load_standard(config: ProjectConfig) -> pd.DataFrame:
    path = config.resolve("standard_excel")
    if not path.exists():
        raise FileNotFoundError(f"No existe el estándar: {path}")
    return pd.read_excel(path, sheet_name="Estandar Sap")


def load_organization(config: ProjectConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    path = config.resolve("organization_excel")
    if not path.exists():
        raise FileNotFoundError(f"No existe la organización: {path}")
    organization = pd.read_excel(path, sheet_name="Organizacion")
    materials = pd.read_excel(path, sheet_name="materiales")
    return organization, materials


def load_mb5b_raw(config: ProjectConfig) -> pd.DataFrame:
    path = config.resolve("mb5b_excel")
    if not path.exists():
        return pd.DataFrame()
    return pd.read_excel(path, sheet_name="Data", header=None)
