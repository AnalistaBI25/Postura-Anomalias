from pathlib import Path

from granjas_anomalias.config import ProjectConfig
from granjas_anomalias.dashboard_payload import _build_cycle_groups


def _config() -> ProjectConfig:
    return ProjectConfig(
        root=Path("."),
        raw={
            "project": {
                "farm_id": "test-farm",
                "center_id": "1217",
                "farm_name": "GRANJA PRUEBA",
                "timezone": "America/Merida",
            },
            "paths": {"standard_excel": "standard.xlsx"},
            "sap": {
                "houses": ["1007", "1008", "1009"],
                "feed_materials": {"10007": "Fase 1"},
            },
            "stock": {},
            "anomaly_detection": {},
            "outputs": {},
            "dashboard": {
                "cycle_group_start_tolerance_days": 2,
            },
        },
    )


def _period(
    caseta: str,
    start: str,
    end: str,
    lote: str,
    orden: str,
    estado: str = "cerrado_confirmado",
) -> dict:
    return {
        "meta": {
            "centro": "1217",
            "granja": "GRANJA PRUEBA",
            "caseta": caseta,
            "lote": lote,
            "orden": orden,
            "estado": estado,
            "fecha_inicio": start,
            "fecha_fin": end,
            "aves_iniciales": 5000.0,
            "fuente_estandar": "standard.xlsx",
        },
        "daily": [{}],
        "weekly": [],
        "scatter": [],
        "regression_stats": {},
    }


def _shared_store() -> dict:
    return {
        "casetas": ["1007", "1008", "1009"],
        "daily": [
            {"fecha": "2024-07-07"},
            {"fecha": "2024-07-08"},
            {"fecha": "2026-02-07"},
            {"fecha": "2026-02-08"},
        ],
        "weekly": [
            {
                "fecha_inicio": "2024-07-01",
                "fecha_fin": "2024-07-07",
            },
            {
                "fecha_inicio": "2026-02-02",
                "fecha_fin": "2026-02-08",
            },
        ],
    }


def test_cycle_groups_join_three_houses_with_close_start_dates() -> None:
    periods = {
        "p1007_old": _period(
            "1007", "2024-07-07", "2025-12-15", "4130", "o1"
        ),
        "p1008_old": _period(
            "1008", "2024-07-07", "2025-12-15", "4130", "o2"
        ),
        "p1009_old": _period(
            "1009", "2024-07-07", "2025-12-16", "4131", "o3"
        ),
        "p1007_new": _period(
            "1007", "2026-02-07", "2026-06-14", "4784", "o4",
            "abierto_en_proceso",
        ),
        "p1008_new": _period(
            "1008", "2026-02-07", "2026-06-14", "4784", "o5",
            "abierto_en_proceso",
        ),
        "p1009_new": _period(
            "1009", "2026-02-08", "2026-06-14", "4785", "o6",
            "abierto_en_proceso",
        ),
    }
    period_ids = list(periods)

    group_ids, groups = _build_cycle_groups(
        period_ids=period_ids,
        periods=periods,
        shared_store=_shared_store(),
        config=_config(),
    )

    assert len(group_ids) == 2

    first = groups[group_ids[0]]
    second = groups[group_ids[1]]

    assert first["meta"]["casetas"] == ["1007", "1008", "1009"]
    assert first["meta"]["grupo_completo"] is True
    assert first["meta"]["aves_iniciales_total"] == 15000.0
    assert first["meta"]["fecha_inicio"] == "2024-07-07"

    assert second["meta"]["casetas"] == ["1007", "1008", "1009"]
    assert second["meta"]["grupo_completo"] is True
    assert second["meta"]["fecha_inicio"] == "2026-02-07"
    assert second["period_id_por_caseta"]["1009"] == "p1009_new"

    for group_id, group in groups.items():
        for period_id in group["period_ids"]:
            assert periods[period_id]["cycle_group_id"] == group_id
            assert periods[period_id]["meta"]["cycle_group_id"] == group_id


def test_cycle_groups_do_not_put_two_cycles_of_same_house_together() -> None:
    periods = {
        "old_1007": _period(
            "1007", "2024-07-01", "2024-07-01", "a", "o1"
        ),
        "new_1007": _period(
            "1007", "2024-07-02", "2024-12-01", "b", "o2"
        ),
        "new_1008": _period(
            "1008", "2024-07-02", "2024-12-01", "b", "o3"
        ),
    }

    group_ids, groups = _build_cycle_groups(
        period_ids=list(periods),
        periods=periods,
        shared_store=_shared_store(),
        config=_config(),
    )

    assert len(group_ids) == 2
    assert all(
        len(group["meta"]["casetas"])
        == len(set(group["meta"]["casetas"]))
        for group in groups.values()
    )

    new_group = next(
        group
        for group in groups.values()
        if "new_1007" in group["period_ids"]
    )
    assert set(new_group["period_ids"]) == {"new_1007", "new_1008"}
    assert new_group["meta"]["grupo_completo"] is False
    assert new_group["meta"]["casetas_faltantes"] == ["1009"]
