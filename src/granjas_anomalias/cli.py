from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline BI/Data Science de anomalías de consumo avícola"
    )
    parser.add_argument(
        "command",
        choices=["run"],
        help="run: ejecuta carga, transformación, EDA, stock y anomalías",
    )
    parser.add_argument(
        "--config",
        default="config/project.yml",
        help="Ruta al archivo YAML de configuración",
    )
    args = parser.parse_args()

    if args.command == "run":
        outputs = run_pipeline(Path(args.config))
        print("\nArchivos generados:")
        for name, path in outputs.items():
            print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
