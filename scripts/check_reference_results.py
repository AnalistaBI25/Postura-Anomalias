from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from granjas_anomalias.config import load_config  # noqa: E402


def assert_if_configured(
    condition: bool,
    message: str,
    key: str,
    config_path: Path,
) -> None:
    if not condition:
        raise AssertionError(
            f"{message} Revise reference_validation.{key} en {config_path}."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Valida referencias de una granja.")
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "project.yml"),
        help="Archivo YAML que contiene project.farm_id.",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_config(config_path)
    processed = config.resolve("processed_dir")
    cycles = pd.read_csv(processed / "05_ciclos_detectados.csv")
    stock = pd.read_csv(
        processed / "09_stock_alimento_diario_global.csv",
        parse_dates=["fecha"],
    )
    reference = config.raw.get("reference_validation", {}) or {}

    assert not cycles.empty, "No se detectaron ciclos."
    assert not stock.empty, "No se encontro stock global."
    assert cycles["caseta"].notna().any(), "No hay casetas en ciclos detectados."

    expected_cycles = reference.get("expected_cycles")
    if expected_cycles is not None:
        assert_if_configured(
            len(cycles) == int(expected_cycles),
            f"Se esperaban {expected_cycles} ciclos y se obtuvieron {len(cycles)}.",
            "expected_cycles",
            config_path,
        )

    expected_houses = reference.get("expected_houses")
    if expected_houses:
        expected_houses = {str(value) for value in expected_houses}
        actual_houses = set(cycles["caseta"].astype(str))
        assert_if_configured(
            actual_houses == expected_houses,
            f"Casetas esperadas {sorted(expected_houses)}; "
            f"casetas obtenidas {sorted(actual_houses)}.",
            "expected_houses",
            config_path,
        )

    reference_stock_date = reference.get("reference_stock_date")
    if reference_stock_date:
        row = stock.loc[stock["fecha"].eq(pd.Timestamp(reference_stock_date))]
        assert_if_configured(
            len(row) == 1,
            f"No se encontro la fecha de referencia {reference_stock_date}.",
            "reference_stock_date",
            config_path,
        )

        expected_feed_entry_kg = reference.get("expected_feed_entry_kg")
        if expected_feed_entry_kg is not None:
            assert_if_configured(
                abs(
                    float(row.iloc[0]["entradas_alimento_kg"])
                    - float(expected_feed_entry_kg)
                )
                < 1e-6,
                "La entrada de alimento de referencia no coincide.",
                "expected_feed_entry_kg",
                config_path,
            )

        expected_stock_global_kg = reference.get("expected_stock_global_kg")
        if expected_stock_global_kg is not None:
            assert_if_configured(
                abs(
                    float(row.iloc[0]["stock_global_kg"])
                    - float(expected_stock_global_kg)
                )
                < 1e-6,
                "El stock global de referencia no coincide.",
                "expected_stock_global_kg",
                config_path,
            )

    print("Validacion de referencia completada.")
    print(f"- farm_id: {config.farm_id}")
    print(f"- ciclos detectados: {len(cycles)}")
    print(f"- casetas detectadas: {cycles['caseta'].nunique()}")
    print(f"- dias de stock global: {len(stock)}")


if __name__ == "__main__":
    main()
