"""Pipeline incremental: ingesta idempotente + recálculo completo.

Uso:
    # Primera vez (histórico): ingiere el kardex configurado en config/project.yml
    python scripts/run_incremental.py --bootstrap

    # Carga incremental por CLI (la app web publica procesa un solo MB51)
    python scripts/run_incremental.py --input nuevo_mb51.xlsx

    # Solo reprocesar con lo ya cargado
    python scripts/run_incremental.py --solo-pipeline
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from granjas_anomalias.config import load_config  # noqa: E402
from granjas_anomalias.db import Warehouse  # noqa: E402
from granjas_anomalias.ingestion import (  # noqa: E402
    ingerir_archivo,
    materializar_kardex_cache,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", default=[], help="Archivo MB51 crudo")
    parser.add_argument("--config", default=str(ROOT / "config" / "project.yml"))
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Ingiere el kardex configurado como histórico inicial",
    )
    parser.add_argument(
        "--solo-pipeline",
        action="store_true",
        help="No ingiere archivos; materializa y ejecuta el pipeline",
    )
    parser.add_argument("--sin-pipeline", action="store_true", help="Solo ingesta")
    args = parser.parse_args()

    config = load_config(args.config)
    db = Warehouse(config.resolve_ingestion("db_path", "data/warehouse.db"))

    entradas = [Path(p) for p in args.input]
    if args.bootstrap:
        entradas.insert(0, config.resolve("kardex_excel"))

    for entrada in entradas:
        print(f"== Ingesta: {entrada}")
        resumen = ingerir_archivo(entrada, config, db, usuario="cli")
        print(f"   [{resumen.estado}] {resumen.mensaje}")
        if resumen.informe and resumen.informe.traslape:
            print(f"   Traslape: {resumen.informe.traslape}")
        if resumen.estado == "RECHAZADO":
            print("   El archivo fue rechazado; revisa data/rejected/ y el registro de cargas.")

    if args.sin_pipeline:
        return 0

    if not entradas and not args.solo_pipeline:
        parser.error("Indica --input, --bootstrap o --solo-pipeline")

    print("== Materializando kardex del centro configurado desde el almacén lógico")
    cache = materializar_kardex_cache(db, config)
    print(f"   Cache: {cache}")

    print("== Ejecutando pipeline completo")
    from granjas_anomalias.pipeline import run_pipeline  # import tardío (pesado)

    outputs = run_pipeline(args.config)
    print(f"== Pipeline completado; dashboard: {outputs.get('dashboard', 'n/a')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
