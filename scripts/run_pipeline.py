import argparse
from pathlib import Path

from granjas_anomalias.pipeline import run_pipeline


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Ejecuta el pipeline de una granja.")
    parser.add_argument(
        "--config",
        default=str(root / "config" / "project.yml"),
        help="Archivo YAML que contiene project.farm_id.",
    )
    args = parser.parse_args()
    run_pipeline(args.config)
