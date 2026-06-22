from __future__ import annotations

from collections import Counter
from html.parser import HTMLParser
from pathlib import Path


class _IdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del tag
        attributes = dict(attrs)
        identifier = attributes.get("id")
        if identifier:
            self.ids.append(identifier)


def _template_text() -> str:
    path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "granjas_anomalias"
        / "templates"
        / "dashboard_productivo.html"
    )
    return path.read_text(encoding="utf-8")


def test_template_has_single_payload_marker_and_unique_ids() -> None:
    template = _template_text()
    assert template.count("__PAYLOAD_JSON__") == 1

    parser = _IdCollector()
    parser.feed(template)
    duplicates = [
        identifier
        for identifier, count in Counter(parser.ids).items()
        if count > 1
    ]
    assert duplicates == []


def test_template_uses_group_and_house_selectors() -> None:
    template = _template_text()

    required_ids = {
        "periodSelect",
        "houseSelect",
        "groupKpiAves",
        "groupKpiStock",
        "groupKpiConsumo",
        "groupKpiEntradas",
        "groupKpiProduccion",
        "groupKpiMortalidad",
        "groupHouseCards",
        "detailContext",
    }

    for identifier in required_ids:
        assert f'id="{identifier}"' in template

    assert "PAYLOAD.cycle_group_ids" in template
    assert "PAYLOAD.cycle_groups" in template
    assert "period_id_por_caseta" in template
    assert "function renderCycleGroup" in template
    assert "function updateGroupSummary" in template


def test_group_summary_explains_sums_and_stock_origin() -> None:
    template = _template_text()

    assert "formulaFromMap" in template
    assert "Suma conciliada" not in template  # wording changed to Día conciliado
    assert "Día conciliado" in template
    assert "Acumulado:" in template
    assert "Apertura + entradas - consumo almacén + otros netos" in template
    assert "No se suma por caseta" in template
