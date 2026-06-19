from pathlib import Path

from granjas_anomalias.pipeline import run_pipeline


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    run_pipeline(root / "config" / "project.yml")
