from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from granjas_anomalias.pipeline import run_pipeline  # noqa: E402


def main() -> None:
    """Entrena el modelo oficial de forma explicita y auditable."""

    os.environ.setdefault("MPLBACKEND", "Agg")
    run_pipeline(ROOT / "config" / "project.yml", model_mode="train")


if __name__ == "__main__":
    main()
