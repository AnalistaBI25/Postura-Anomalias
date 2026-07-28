from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from granjas_anomalias.config import load_config  # noqa: E402


REQUIRED_ROOT_DIRECTORIES = {
    ".github",
    ".streamlit",
    "agents",
    "config",
    "docs",
    "farms",
    "legacy",
    "notebooks",
    "scripts",
    "src",
    "streamlit_components",
    "tests",
}

FORBIDDEN_RUNTIME_ROOTS = {
    "data",
    "logs",
    "models",
    "outputs",
    "reports",
}

GENERATED_CLUTTER = {
    ".agents",
    ".claude",
    ".codex",
    ".pytest_cache",
    ".ruff_cache",
    ".ua",
    "__pycache__",
}

REQUIRED_FARM_DIRECTORIES = {
    "data/raw/cargas",
    "data/incoming",
    "data/rejected",
    "data/cache",
    "data/interim",
    "data/processed",
    "models",
    "reports/figures",
    "reports/tables",
    "outputs/latest",
    "outputs/dashboard",
    "outputs/history",
    "logs",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Valida la estructura limpia y aislada del proyecto.",
    )
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "project.yml"),
        help="Archivo YAML que contiene project.farm_id.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    errors: list[str] = []
    warnings: list[str] = []

    for name in sorted(REQUIRED_ROOT_DIRECTORIES):
        if not (ROOT / name).is_dir():
            errors.append(f"Falta la carpeta requerida en raíz: {name}/")

    for name in sorted(FORBIDDEN_RUNTIME_ROOTS):
        if (ROOT / name).exists():
            errors.append(
                f"La carpeta operativa root/{name}/ debe estar dentro de "
                f"farms/{config.farm_id}/."
            )

    for name in sorted(GENERATED_CLUTTER):
        if (ROOT / name).exists():
            warnings.append(f"Carpeta regenerable o de herramienta en raíz: {name}/")

    for relative in sorted(REQUIRED_FARM_DIRECTORIES):
        if not (config.farm_root / relative).is_dir():
            errors.append(
                f"Falta farms/{config.farm_id}/{relative}/"
            )

    print(f"farm_id: {config.farm_id}")
    print(f"farm_root: {config.farm_root}")
    if warnings:
        print("\nAdvertencias:")
        for warning in warnings:
            print(f"- {warning}")
    if errors:
        print("\nErrores:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nEstructura válida: raíz limpia y runtime aislado por granja.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
