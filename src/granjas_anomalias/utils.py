from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def clean_key(value: object) -> object:
    if pd.isna(value):
        return pd.NA
    text = str(value).strip().replace(",", "")
    if text.endswith(".0"):
        text = text[:-2]
    if text.lower() in {"", "nan", "none", "<na>"}:
        return pd.NA
    return text


def parse_sap_number(value: object) -> float:
    if pd.isna(value):
        return np.nan
    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)

    text = str(value).strip().replace(" ", "")
    if text.lower() in {"", "nan", "none", "<na>"}:
        return np.nan

    negative = text.endswith("-") or text.startswith("-")
    text = text.strip("-").replace(",", "")
    try:
        number = float(text)
    except ValueError:
        return np.nan
    return -abs(number) if negative else number


def parse_dates(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        return pd.to_datetime(series, errors="coerce").dt.normalize()

    text = series.astype("string").str.strip()
    result = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    slash_mask = text.str.match(r"^\d{1,2}/\d{1,2}/\d{4}$", na=False)
    result.loc[slash_mask] = pd.to_datetime(
        text.loc[slash_mask], format="mixed", errors="coerce", dayfirst=False
    )

    dot_mask = text.str.match(r"^\d{1,2}\.\d{1,2}\.\d{4}$", na=False)
    result.loc[dot_mask] = pd.to_datetime(
        text.loc[dot_mask], format="%d.%m.%Y", errors="coerce"
    )

    remaining = result.isna() & text.notna()
    result.loc[remaining] = pd.to_datetime(text.loc[remaining], errors="coerce")
    return result.dt.normalize()


def compact_unique(values: Iterable[object], limit: int = 12) -> str:
    output: list[str] = []
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if not text or text in output:
            continue
        output.append(text)
        if len(output) >= limit:
            break
    return ", ".join(output)


def save_csv(df: pd.DataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = pd.to_numeric(denominator, errors="coerce")
    numerator = pd.to_numeric(numerator, errors="coerce")
    return numerator.div(denominator.where(denominator.abs() > 1e-12))
