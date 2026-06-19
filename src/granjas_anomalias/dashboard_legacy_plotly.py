from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .config import ProjectConfig


def build_dashboard(
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    stock_global: pd.DataFrame,
    anomalies: pd.DataFrame,
    cycles: pd.DataFrame,
    config: ProjectConfig,
) -> Path:
    consumption = daily.pivot_table(
        index="fecha", columns="caseta", values="consumo_real_kg_dia", aggfunc="sum", fill_value=0
    ).reset_index()

    fig_stock = make_subplots(specs=[[{"secondary_y": True}]])
    fig_stock.add_trace(
        go.Scatter(x=stock_global["fecha"], y=stock_global["stock_global_kg"], name="Stock global", mode="lines"),
        secondary_y=False,
    )
    fig_stock.add_trace(
        go.Bar(x=stock_global["fecha"], y=stock_global["entradas_alimento_kg"], name="Entradas 101 WE", opacity=0.45),
        secondary_y=True,
    )
    fig_stock.update_layout(title="Almacén 1100: stock global y entradas diarias", barmode="overlay")

    fig_consumption = go.Figure()
    for column in [c for c in consumption.columns if c != "fecha"]:
        fig_consumption.add_trace(
            go.Bar(x=consumption["fecha"], y=consumption[column], name=f"Caseta {column}")
        )
    fig_consumption.update_layout(
        title="Consumo diario proveniente de las tres casetas", barmode="stack", yaxis_title="kg"
    )

    fig_weekly = px.line(
        weekly,
        x="edad_semana",
        y="brecha_ica_pct",
        color="cycle_id",
        markers=True,
        title="Brecha semanal de ICA frente a política",
        labels={"brecha_ica_pct": "Brecha ICA", "edad_semana": "Semana de edad"},
    )

    top = anomalies.sort_values("score_anomalia", ascending=False).head(50).copy()
    top["fecha_texto"] = top["fecha"].dt.strftime("%Y-%m-%d")
    fig_anomalies = px.scatter(
        top,
        x="fecha",
        y="score_anomalia",
        color="severidad",
        hover_data=["cycle_id", "caseta", "edad_semana", "motivo_anomalia", "consumo_real_kg_dia", "consumo_estandar_kg_dia"],
        title="Principales señales de anomalía de consumo",
    )

    kpis = {
        "Ciclos": len(cycles),
        "Anomalías": int(anomalies["es_anomalia"].sum()),
        "Críticas": int(anomalies["severidad"].eq("critica").sum()),
        "Stock final kg": round(float(stock_global["stock_global_kg"].iloc[-1]), 2),
    }

    cards = "".join(
        f'<div class="card"><span>{key}</span><strong>{value:,}</strong></div>'
        for key, value in kpis.items()
    )
    table = top[[
        "fecha_texto", "cycle_id", "caseta", "edad_semana", "score_anomalia", "severidad", "motivo_anomalia"
    ]].to_html(index=False, classes="data-table", escape=True)

    site_name = str(config.project.get("farm_name") or "Sitio piloto")

    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Dashboard anomalías productivas</title>
<style>
body{{font-family:Arial,sans-serif;background:#f2fbfe;color:#12335e;margin:0;padding:20px}}
header{{background:#1a428a;color:white;padding:20px;border-radius:14px}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:16px 0}}
.card{{background:white;border:1px solid #cbeaf4;border-radius:12px;padding:14px}}
.card span{{display:block;font-size:12px;color:#315b7f}}.card strong{{font-size:25px}}
.panel{{background:white;padding:12px;border-radius:14px;margin:12px 0;border:1px solid #cbeaf4}}
.data-table{{border-collapse:collapse;width:100%;font-size:12px}}.data-table th,.data-table td{{border:1px solid #ddd;padding:6px}}
@media(max-width:900px){{.grid{{grid-template-columns:1fr 1fr}}}}
</style></head><body>
<header><h1>{site_name} — consumo, stock, ciclos y anomalías</h1><p>Vista ejecutiva global con trazabilidad SAP por orden y ciclo.</p></header>
<div class="grid">{cards}</div>
<div class="panel">{fig_stock.to_html(full_html=False, include_plotlyjs='cdn')}</div>
<div class="panel">{fig_consumption.to_html(full_html=False, include_plotlyjs=False)}</div>
<div class="panel">{fig_weekly.to_html(full_html=False, include_plotlyjs=False)}</div>
<div class="panel">{fig_anomalies.to_html(full_html=False, include_plotlyjs=False)}</div>
<div class="panel"><h2>Top 50 señales para revisión</h2>{table}</div>
</body></html>"""
    path = config.root / "reports" / "dashboard.html"
    path.write_text(html, encoding="utf-8")
    return path
