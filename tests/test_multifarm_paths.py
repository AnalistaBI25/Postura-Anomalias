from __future__ import annotations

from pathlib import Path

import pytest

from granjas_anomalias.config import ProjectConfig


def _config(root: Path, farm_id: str) -> ProjectConfig:
    return ProjectConfig(
        root=root,
        raw={
            "project": {"farm_id": farm_id},
            "paths": {
                "kardex_excel": "data/raw/kardex.xlsx",
                "kardex_cache_csv": "data/cache/kardex.csv",
                "interim_dir": "data/interim",
                "processed_dir": "data/processed",
                "figures_dir": "reports/figures",
                "tables_dir": "reports/tables",
                "reports_dir": "reports",
                "outputs_dir": "outputs",
                "models_dir": "models",
                "logs_dir": "logs",
            },
            "ingestion": {
                "db_path": "data/warehouse.db",
                "incoming_dir": "data/incoming",
                "rejected_dir": "data/rejected",
                "raw_archive_dir": "data/raw/cargas",
            },
            "model_lifecycle": {
                "active_model_path": "models/isolation_forest.joblib",
                "metadata_path": "models/isolation_forest_metadata.json",
            },
        },
    )


def test_runtime_paths_are_scoped_by_farm_id(tmp_path: Path) -> None:
    first = _config(tmp_path, "granja-a")
    second = _config(tmp_path, "granja-b")

    selectors = [
        lambda config: config.resolve("kardex_cache_csv"),
        lambda config: config.resolve("processed_dir"),
        lambda config: config.resolve("reports_dir"),
        lambda config: config.resolve("outputs_dir"),
        lambda config: config.resolve("models_dir"),
        lambda config: config.resolve("logs_dir"),
        lambda config: config.resolve_ingestion("db_path", "data/warehouse.db"),
        lambda config: config.resolve_ingestion("incoming_dir", "data/incoming"),
        lambda config: config.resolve_ingestion("rejected_dir", "data/rejected"),
        lambda config: config.resolve_ingestion(
            "raw_archive_dir",
            "data/raw/cargas",
        ),
        lambda config: config.resolve_model_lifecycle(
            "active_model_path",
            "models/isolation_forest.joblib",
        ),
        lambda config: config.resolve_model_lifecycle(
            "metadata_path",
            "models/isolation_forest_metadata.json",
        ),
    ]

    for select in selectors:
        first_path = select(first)
        second_path = select(second)
        assert first_path != second_path
        assert first_path.is_relative_to(first.farm_root)
        assert second_path.is_relative_to(second.farm_root)


@pytest.mark.parametrize(
    "farm_id",
    ["", "Chencopo", "../otra", "granja/otra", "granja otra", "a" * 65],
)
def test_invalid_farm_id_is_rejected(tmp_path: Path, farm_id: str) -> None:
    with pytest.raises(ValueError, match="farm_id"):
        _ = _config(tmp_path, farm_id).farm_root


@pytest.mark.parametrize("runtime_path", ["../fuera", "data/../../fuera"])
def test_runtime_path_cannot_escape_farm_root(
    tmp_path: Path,
    runtime_path: str,
) -> None:
    config = _config(tmp_path, "granja-segura")

    with pytest.raises(ValueError, match="escapa"):
        config.resolve_runtime_path(runtime_path)


def test_ensure_directories_creates_complete_farm_layout(tmp_path: Path) -> None:
    config = _config(tmp_path, "granja-completa")

    config.ensure_directories()

    expected_directories = [
        "data/raw",
        "data/raw/cargas",
        "data/incoming",
        "data/rejected",
        "data/cache",
        "data/interim",
        "data/processed",
        "models",
        "reports",
        "reports/figures",
        "reports/tables",
        "outputs",
        "logs",
    ]
    for relative in expected_directories:
        assert (config.farm_root / relative).is_dir()
