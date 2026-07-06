from __future__ import annotations

import hashlib
import re
from pathlib import Path


TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "granjas_anomalias"
    / "templates"
    / "dashboard_productivo.html"
)


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_header_exposes_compact_sticky_global_filters() -> None:
    template = _template()

    assert ".control-dock{" in template
    assert "position:sticky;top:0" in template
    for identifier in (
        "farmFilter",
        "centerFilter",
        "statusFilter",
        "scopeFilter",
        "periodSelect",
        "singleDate",
    ):
        assert f'id="{identifier}"' in template

    assert '<option value="cycle">Ciclo completo</option>' in template
    assert '<option value="week">Semana</option>' in template
    assert '<option value="day">Día específico</option>' in template
    assert 'data-workspace="cycles"' in template
    assert "filteredCycleGroupIds" in template


def test_food_workspace_is_independent_and_has_temporal_playback() -> None:
    template = _template()

    assert "Cobertura de alimento preventivo" in template
    for identifier in (
        "foodInventoryChart",
        "foodDateSlider",
        "foodPlayPause",
        "foodLatestBtn",
        "foodEventStrip",
    ):
        assert f'id="{identifier}"' in template

    assert "function firstCycleDate" in template
    assert "function foodHistoryRows" in template
    assert "function setupFoodTimeline" in template
    assert "PAYLOAD.shared_store?.daily" in template
    assert "Distribución del alimento hacia las casetas" not in template
    assert "foodFlow" not in template


def test_historical_eda_has_its_own_workspace_and_ranked_movements() -> None:
    template = _template()

    assert 'id="tab-history"' in template
    assert 'data-workspace="history"' in template
    assert "Análisis histórico EDA" in template
    assert "function movementChartRows" in template
    assert "indexAxis:'y'" in template
    assert "type:'doughnut'" not in template


def test_protected_productive_section_markup_remains_unchanged() -> None:
    template = _template()
    match = re.search(
        r'(?s)<section class="panel section-bar">\s*'
        r'<div><h2>Casetas, órdenes, aves y producción</h2>.*?'
        r'<section class="group-house-wrap"><div class="group-house-grid" '
        r'id="groupHouseCards"></div></section>',
        template,
    )

    assert match is not None
    digest = hashlib.sha256(match.group(0).encode("utf-8")).hexdigest()
    assert digest == "385ca5c03b0705bb2d703dfd949d191de185ddf46ea1e6e9bbb9ea2717582185"


def test_single_playback_engine_with_mirrored_feed_controls() -> None:
    template = _template()

    # Un único motor lógico de reproducción: un solo timer activo.
    assert template.count("setInterval(") == 1
    assert template.count("clearInterval(") == 1

    # El reproductor de alimento dejó de tener motor, timer y fecha propios.
    for forbidden in (
        "state.food.timer",
        "state.food.playing",
        "state.food.speedMs",
        "toggleFoodPlayback",
        "stopFoodPlayback",
        "updateFoodPlayButton",
    ):
        assert forbidden not in template

    # Los controles de alimento accionan el mismo motor y fecha globales.
    assert "el('foodPlayPause').addEventListener('click',togglePlayback)" in template
    assert "function goToGlobalDate" in template
    assert "function foodIndexForDate" in template
    assert "function syncFoodCursorFromGlobal" in template


def test_hidden_workspaces_are_deferred_not_rebuilt_per_tick() -> None:
    template = _template()

    # Existe el mecanismo dirty-workspace.
    assert "dirty:new Set()" in template
    assert "function refreshDeferredWorkspaces" in template
    assert "function renderDeferredWorkspace" in template
    assert "refreshDeferredWorkspaces()" in template

    # Las tablas pesadas y el catálogo dejaron de invocarse incondicionalmente en
    # cada tick: ahora pasan por el despachador diferido.
    assert "renderDeferredWorkspace(name)" in template


def test_ica_chart_range_uses_chart_labels_not_mismatched_etiqueta() -> None:
    template = _template()

    # El bug previo acotaba el eje X del ICA con el formato de
    # selectedHouseWeeklyRows ("Sem. N · fechas"), que no coincide con las
    # categorías del eje ("Semana N"), dejando la gráfica vacía.
    assert "state.charts.ica.options.scales.x.min=visible[0]?.etiqueta" not in template
    assert "state.charts.ica.options.scales.x.min=inRange.length?labels[inRange[0]]" in template


def test_brand_uses_png_logo_marker() -> None:
    template = _template()

    # El logo de texto se sustituye por la imagen incrustada por el pipeline.
    assert 'class="crio-logo"' in template
    assert template.count("__LOGO_DATA_URI__") == 1
    assert "crio-wordmark" not in template


def test_night_mode_and_print_button_are_removed() -> None:
    template = _template()

    # Modo noche y botón de imprimir retirados; sin referencias colgantes.
    assert 'id="themeToggle"' not in template
    assert 'id="printBtn"' not in template
    assert 'html[data-theme="dark"]' not in template
    assert "function applyTheme" not in template
    assert "el('printBtn')" not in template


def test_literal_element_references_have_matching_dom_ids() -> None:
    template = _template()
    identifiers = set(re.findall(r'\bid="([^"]+)"', template))
    references = set(re.findall(r"\bel\('([^']+)'\)", template))

    assert references - identifiers == set()


def test_anomaly_workspace_exposes_shadow_model_comparison() -> None:
    template = _template()

    for text in (
        "Comparación en modo sombra",
        "IF global",
        "IF por edad",
        "LOF por edad",
        "Consenso ≥2 modelos",
    ):
        assert text in template
    for identifier in (
        "anomalyModelSummary",
        "anomalySummary",
        "anomalyHistoryBody",
    ):
        assert f'id="{identifier}"' in template
    assert "function modelOriginLabel" in template
    assert "r.flag_lof" in template
