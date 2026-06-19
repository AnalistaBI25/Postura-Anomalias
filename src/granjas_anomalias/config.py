from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ProjectConfig:
    root: Path
    raw: dict[str, Any]

    @property
    def project(self) -> dict[str, Any]:
        return self.raw["project"]

    @property
    def paths(self) -> dict[str, Any]:
        return self.raw["paths"]

    @property
    def sap(self) -> dict[str, Any]:
        return self.raw["sap"]

    @property
    def stock(self) -> dict[str, Any]:
        return self.raw["stock"]

    @property
    def anomaly(self) -> dict[str, Any]:
        return self.raw["anomaly_detection"]

    @property
    def outputs(self) -> dict[str, Any]:
        return self.raw["outputs"]

    def resolve(self, path_key: str) -> Path:
        return (self.root / self.paths[path_key]).resolve()

    def ensure_directories(self) -> None:
        for key in [
            "interim_dir",
            "processed_dir",
            "figures_dir",
            "tables_dir",
            "models_dir",
            "logs_dir",
        ]:
            self.resolve(key).mkdir(parents=True, exist_ok=True)


def load_config(config_path: str | Path) -> ProjectConfig:
    config_path = Path(config_path).resolve()
    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    root = config_path.parent.parent
    config = ProjectConfig(root=root, raw=raw)
    config.ensure_directories()
    return config
