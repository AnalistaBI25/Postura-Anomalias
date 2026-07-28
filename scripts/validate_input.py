"""Valida un archivo SAP crudo sin cargarlo.

Uso:
    python scripts/validate_input.py --input "archivo_sap.xlsx" [--config config/project.yml]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from granjas_anomalias.config import load_config  # noqa: E402
from granjas_anomalias.db import Warehouse  # noqa: E402
from granjas_anomalias.ingestion import validar_archivo  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Ruta del archivo a validar")
    parser.add_argument("--config", default=str(ROOT / "config" / "project.yml"))
    args = parser.parse_args()

    config = load_config(args.config)
    db = Warehouse(config.resolve_ingestion("db_path", "data/warehouse.db"))
    informe = validar_archivo(args.input, config, db)

    print(json.dumps(informe.resumen(), indent=2, ensure_ascii=False))
    if informe.granularidad:
        print("\nGranularidad detectada:")
        print(json.dumps(informe.granularidad, indent=2, ensure_ascii=False))
    return 0 if informe.valido else 1


if __name__ == "__main__":
    raise SystemExit(main())
