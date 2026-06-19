from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "project.yml"


def load_reference_validation() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    return config.get("reference_validation", {}) or {}


def assert_if_configured(condition: bool, message: str, key: str) -> None:
    if not condition:
        raise AssertionError(f"{message} Revise reference_validation.{key} en config/project.yml.")


cycles = pd.read_csv(ROOT / "data/processed/05_ciclos_detectados.csv")
stock = pd.read_csv(
    ROOT / "data/processed/09_stock_alimento_diario_global.csv",
    parse_dates=["fecha"],
)
reference = load_reference_validation()

assert not cycles.empty, "No se detectaron ciclos."
assert not stock.empty, "No se encontro stock global."
assert cycles["caseta"].notna().any(), "No hay casetas en ciclos detectados."

expected_cycles = reference.get("expected_cycles")
if expected_cycles is not None:
    assert_if_configured(
        len(cycles) == int(expected_cycles),
        f"Se esperaban {expected_cycles} ciclos y se obtuvieron {len(cycles)}.",
        "expected_cycles",
    )

expected_houses = reference.get("expected_houses")
if expected_houses:
    expected_houses = {str(value) for value in expected_houses}
    actual_houses = set(cycles["caseta"].astype(str))
    assert_if_configured(
        actual_houses == expected_houses,
        f"Casetas esperadas {sorted(expected_houses)}; casetas obtenidas {sorted(actual_houses)}.",
        "expected_houses",
    )

reference_stock_date = reference.get("reference_stock_date")
if reference_stock_date:
    row = stock.loc[stock["fecha"].eq(pd.Timestamp(reference_stock_date))]
    assert_if_configured(
        len(row) == 1,
        f"No se encontro la fecha de referencia {reference_stock_date} en stock global.",
        "reference_stock_date",
    )

    expected_feed_entry_kg = reference.get("expected_feed_entry_kg")
    if expected_feed_entry_kg is not None:
        assert_if_configured(
            abs(float(row.iloc[0]["entradas_alimento_kg"]) - float(expected_feed_entry_kg)) < 1e-6,
            "La entrada de alimento de referencia no coincide.",
            "expected_feed_entry_kg",
        )

    expected_stock_global_kg = reference.get("expected_stock_global_kg")
    if expected_stock_global_kg is not None:
        assert_if_configured(
            abs(float(row.iloc[0]["stock_global_kg"]) - float(expected_stock_global_kg)) < 1e-6,
            "El stock global de referencia no coincide.",
            "expected_stock_global_kg",
        )

print("Validacion de referencia completada.")
print(f"- ciclos detectados: {len(cycles)}")
print(f"- casetas detectadas: {cycles['caseta'].nunique()}")
print(f"- dias de stock global: {len(stock)}")
