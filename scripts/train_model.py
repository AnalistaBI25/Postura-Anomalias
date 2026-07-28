from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from granjas_anomalias.pipeline import run_pipeline  # noqa: E402


def main() -> None:
    """Entrena el modelo oficial de forma explicita y auditable."""

    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "project.yml"),
        help="Archivo YAML que contiene project.farm_id.",
    )
    args = parser.parse_args()
    os.environ.setdefault("MPLBACKEND", "Agg")
    run_pipeline(args.config, model_mode="train")


if __name__ == "__main__":
    main()
