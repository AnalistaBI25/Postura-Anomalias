from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import ProjectConfig


BRAND = {
    "blue_dark": "#1A428A",
    "blue_light": "#00B2E3",
    "green_dark": "#266041",
    "green_light": "#88BD54",
    "red": "#DC0814",
    "yellow": "#FDC600",
}


def _save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def generate_eda_figures(
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    stock_global: pd.DataFrame,
    anomalies: pd.DataFrame,
    config: ProjectConfig,
) -> list[Path]:
    output = config.resolve("figures_dir")
    paths: list[Path] = []

    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(stock_global["fecha"], stock_global["stock_global_kg"], label="Stock global", color=BRAND["blue_dark"])
    ax.bar(stock_global["fecha"], stock_global["entradas_alimento_kg"], alpha=0.35, label="Entradas", color=BRAND["green_light"])
    ax.set_title("Stock global y entradas de alimento — almacén 1100")
    ax.set_ylabel("kg")
    ax.legend()
    path = output / "01_stock_global_alimento.png"
    _save(fig, path)
    paths.append(path)

    pivot = daily.pivot_table(index="fecha", columns="caseta", values="consumo_real_kg_dia", aggfunc="sum", fill_value=0)
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.stackplot(pivot.index, *[pivot[c] for c in pivot.columns], labels=[str(c) for c in pivot.columns])
    ax.set_title("Consumo diario de alimento por caseta")
    ax.set_ylabel("kg/día")
    ax.legend(title="Caseta", loc="upper left")
    path = output / "02_consumo_diario_por_caseta.png"
    _save(fig, path)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(14, 6))
    for cycle_id, group in weekly.groupby("cycle_id"):
        ax.plot(group["edad_semana"], group["ica_real"], marker="o", alpha=0.75, label=cycle_id)
    policy = weekly.groupby("edad_semana")["ica_estandar_principal"].median()
    ax.plot(policy.index, policy.values, color=BRAND["green_dark"], linewidth=3, label="ICA estándar")
    ax.set_title("ICA semanal por ciclo frente a política")
    ax.set_xlabel("Semana de edad")
    ax.set_ylabel("ICA")
    ax.set_ylim(bottom=0)
    ax.legend(fontsize=7, ncol=2)
    path = output / "03_ica_semanal_vs_estandar.png"
    _save(fig, path)
    paths.append(path)

    top = anomalies.sort_values("score_anomalia", ascending=False).head(20).copy()
    top["label"] = top["cycle_id"] + " | " + top["fecha"].dt.strftime("%Y-%m-%d")
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.barh(top["label"][::-1], top["score_anomalia"][::-1], color=BRAND["red"])
    ax.set_title("Top 20 señales de anomalía de consumo")
    ax.set_xlabel("Score 0–100")
    path = output / "04_top_anomalias_consumo.png"
    _save(fig, path)
    paths.append(path)

    fig, ax = plt.subplots(figsize=(14, 5))
    for cycle_id, group in anomalies.groupby("cycle_id"):
        ax.plot(group["fecha"], group["score_anomalia"], alpha=0.7, label=cycle_id)
    ax.axhline(float(config.anomaly["scoring"]["high_threshold"]), linestyle="--", color=BRAND["red"], label="Umbral alto")
    ax.set_title("Score de anomalía a lo largo del tiempo")
    ax.set_ylabel("Score")
    ax.legend(fontsize=7, ncol=2)
    path = output / "05_score_anomalia_tiempo.png"
    _save(fig, path)
    paths.append(path)
    return paths


def write_eda_report(
    kardex: pd.DataFrame,
    cycles: pd.DataFrame,
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    anomalies: pd.DataFrame,
    config: ProjectConfig,
) -> Path:
    anomaly_count = int(anomalies["es_anomalia"].sum())
    critical_count = int(anomalies["severidad"].eq("critica").sum())
    high_count = int(anomalies["severidad"].eq("alta").sum())
    report = f"""# Reporte EDA y detección inicial de anomalías

## Resumen de ejecución

- Centro: **{config.project['center_id']} — {config.project['farm_name']}**
- Registros normalizados de MB51: **{len(kardex):,}**
- Periodo: **{kardex['fecha'].min().date()} a {kardex['fecha'].max().date()}**
- Ciclos detectados: **{len(cycles):,}**
- Filas diarias por ciclo: **{len(daily):,}**
- Filas semanales: **{len(weekly):,}**
- Señales de anomalía media o superior: **{anomaly_count:,}**
- Señales altas: **{high_count:,}**
- Señales críticas: **{critical_count:,}**

## Interpretación

El score es una **señal de revisión**, no una conclusión de fraude, error operativo o problema sanitario. Combina reglas de negocio auditables y un baseline no supervisado de Isolation Forest.

## Reglas productivas preservadas

- Inicio biológico: material 20019 + 101 WE por centro, caseta y lote.
- Edad inicial: semana 16, día 0.
- Consumo de ciclo: materiales 10007–10011, 261 WA menos 262 WA, asignados por orden.
- Producción de ciclo: 101/102 WF para huevo principal y 531/532 WA para subproductos.
- Stock: almacén global 1100, separado de la asignación del consumo por orden.
- ICA: consumo neto de la orden dividido entre producción neta de la orden, evaluado semanalmente.

## Próxima validación de negocio

Revisar primero `data/processed/anomalias_consumo.csv`, priorizando severidad crítica y alta. Agregar una columna de etiqueta validada para preparar la fase supervisada.
"""
    path = config.resolve("reports_dir") / "EDA_Y_ANOMALIAS.md"
    path.write_text(report, encoding="utf-8")
    return path
