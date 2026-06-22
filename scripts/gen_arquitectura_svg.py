"""
Genera docs/arquitectura_flujo.svg (diagrama de flujo de datos, Fase 1).

Reproducible y sin dependencias externas de Graphviz: dibuja el diagrama con
matplotlib y exporta SVG con texto seleccionable (svg.fonttype='none'), de modo
que el navegador renderice también el emoji del indicador "YOU ARE HERE".

Uso:
    python scripts/gen_arquitectura_svg.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["svg.fonttype"] = "none"
matplotlib.rcParams["font.family"] = "DejaVu Sans"

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

CRIO = {
    "green_light": "#88BD54",
    "green_dark": "#266041",
    "blue_light": "#00B2E3",
    "blue_dark": "#1A428A",
    "red": "#DC0814",
    "yellow": "#FDC600",
    "text": "#12335E",
    "pale_blue": "#DDF5FB",
    "surface_blue": "#F2FBFE",
    "surface_green": "#F5FAF0",
    "pale_green": "#EAF5DF",
    "note": "#FFF8D6",
    "gray": "#9DB4CD",
}

nodes: dict[str, dict[str, float]] = {}


def main() -> Path:
    fig, ax = plt.subplots(figsize=(15.2, 7.7))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 50)
    ax.axis("off")

    def cluster(x, y, w, h, label, fill, edge, dashed=False):
        ax.add_patch(
            FancyBboxPatch(
                (x, y), w, h,
                boxstyle="round,pad=0.3,rounding_size=1.4",
                linewidth=1.6, edgecolor=edge, facecolor=fill,
                linestyle="--" if dashed else "-", zorder=1,
            )
        )
        ax.text(x + w / 2, y + h - 1.4, label, ha="center", va="top",
                fontsize=8.5, fontweight="bold", color=edge, zorder=3)

    def node(key, cx, cy, w, h, label, fill="#FFFFFF", edge=CRIO["blue_dark"],
             fontcolor=None, lw=1.2, dashed=False, fontsize=7.2, bold=False):
        ax.add_patch(
            FancyBboxPatch(
                (cx - w / 2, cy - h / 2), w, h,
                boxstyle="round,pad=0.2,rounding_size=0.7",
                linewidth=lw, edgecolor=edge, facecolor=fill,
                linestyle="--" if dashed else "-", zorder=2,
            )
        )
        ax.text(cx, cy, label, ha="center", va="center", fontsize=fontsize,
                color=fontcolor or CRIO["text"],
                fontweight="bold" if bold else "normal",
                zorder=4, linespacing=1.3)
        nodes[key] = {"cx": cx, "cy": cy, "w": w, "h": h}

    def anchor(n, side):
        return {
            "right": (n["cx"] + n["w"] / 2, n["cy"]),
            "left": (n["cx"] - n["w"] / 2, n["cy"]),
            "top": (n["cx"], n["cy"] + n["h"] / 2),
            "bottom": (n["cx"], n["cy"] - n["h"] / 2),
        }[side]

    def arrow(a, b, sa="right", sb="left", color=None, dashed=False,
              label=None, rad=0.0):
        color = color or CRIO["text"]
        pa, pb = anchor(nodes[a], sa), anchor(nodes[b], sb)
        ax.add_patch(
            FancyArrowPatch(
                pa, pb, arrowstyle="-|>", mutation_scale=11, linewidth=1.15,
                color=color, linestyle="--" if dashed else "-",
                connectionstyle=f"arc3,rad={rad}", zorder=1.5,
            )
        )
        if label:
            ax.text((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2 + 0.7, label,
                    ha="center", va="bottom", fontsize=6, style="italic",
                    color=color, zorder=5)

    # Título
    ax.text(50, 49.3, "CRÍO · BI de anomalías de consumo — flujo de datos (Fase 1)",
            ha="center", va="top", fontsize=13, fontweight="bold",
            color=CRIO["blue_dark"])

    # Clústeres
    cluster(1, 6, 17, 40, "1 · Fuentes (SAP + maestros)",
            CRIO["surface_green"], CRIO["green_dark"])
    cluster(24, 2, 22, 45, "2 · Procesamiento · pipeline.py",
            CRIO["pale_blue"], CRIO["blue_light"])
    cluster(52, 12, 18, 30, "3 · Artefactos generados",
            CRIO["pale_green"], CRIO["green_dark"])
    cluster(75, 12, 13, 30, "4 · Frontend (sin API)",
            CRIO["surface_blue"], CRIO["blue_dark"])
    cluster(90, 12, 9, 30, "Fases siguientes",
            "#FFFFFF", CRIO["gray"], dashed=True)

    # 1 · Fuentes
    node("mb51", 9.5, 39, 14, 5, "Kárdex MB51\n(movimientos)", edge=CRIO["green_dark"])
    node("std", 9.5, 32, 14, 5, "Estándar SAP\n(consumo / prod / ICA)", edge=CRIO["green_dark"])
    node("org", 9.5, 25, 14, 5, "Organización\n(casetas / órdenes)", edge=CRIO["green_dark"])
    node("mb5b", 9.5, 18, 14, 5, "MB5B\n(stock inicial)", edge=CRIO["green_dark"])
    node("cfg", 9.5, 3.2, 15, 4.4, "config/project.yml\n(parámetros)",
         fill=CRIO["note"], edge=CRIO["yellow"], fontsize=6.6)

    # 2 · Procesamiento
    node("here", 35, 43.4, 19, 3.6, "📍 YOU ARE HERE (Fase 1)",
         fill=CRIO["yellow"], edge=CRIO["red"], lw=2.6, bold=True, fontsize=8.2)
    node("load", 35, 38, 18, 3.4, "Carga + normalización")
    node("classify", 35, 33.2, 18, 3.4, "Clasificación SAP")
    node("cycles", 35, 28.4, 18, 3.4, "Ciclos productivos")
    node("daily", 35, 23.6, 18, 3.4, "Línea diaria / semanal")
    node("stock", 35, 18.8, 18, 3.4, "Stock global")
    node("feats", 35, 14, 18, 3.4, "Features")
    node("rules", 35, 8.6, 18, 4, "Reglas + Isolation Forest\n(score de anomalía)",
         fill=CRIO["surface_blue"], edge=CRIO["blue_dark"], fontsize=6.8)

    # 3 · Artefactos
    node("csv", 61, 36, 15, 5, "CSV intermedios\n(interim / processed)", edge=CRIO["green_dark"])
    node("payload", 61, 27.5, 15, 4.6, "payload JSON\n(dashboard_payload.py)")
    node("html", 61, 19, 15, 4.8, "reports/dashboard.html\n(PAYLOAD + logo)",
         fill="#FFFFFF", edge=CRIO["blue_dark"], bold=True, fontsize=6.8)

    # 4 · Frontend
    node("chart", 81.5, 31, 11, 5.4, "Chart.js +\nestado único", edge=CRIO["blue_dark"])
    node("user", 81.5, 21, 11, 4.6, "Usuario /\noperación", fill=CRIO["pale_green"], edge=CRIO["green_dark"])

    # 5 · Futuro
    node("f2", 94.5, 31, 8, 5, "Fase 2\nModelado", edge=CRIO["gray"], dashed=True, fontsize=6.6)
    node("f3", 94.5, 21, 8, 5, "Fase 3\nMLOps", edge=CRIO["gray"], dashed=True, fontsize=6.6)

    # Aristas
    for s in ("mb51", "std", "org", "mb5b"):
        arrow(s, "load", color=CRIO["green_dark"])
    arrow("cfg", "load", sa="right", sb="bottom", dashed=True,
          color=CRIO["yellow"], label="parametriza", rad=-0.2)

    arrow("here", "load", sa="bottom", sb="top", dashed=True, color=CRIO["red"])
    for a, b in [("load", "classify"), ("classify", "cycles"), ("cycles", "daily"),
                 ("daily", "stock"), ("stock", "feats"), ("feats", "rules")]:
        arrow(a, b, sa="bottom", sb="top", color=CRIO["blue_dark"])

    arrow("rules", "csv", color=CRIO["blue_dark"], rad=-0.25)
    arrow("rules", "payload", color=CRIO["blue_dark"], rad=-0.1)
    arrow("payload", "html", sa="bottom", sb="top", color=CRIO["green_dark"])
    arrow("csv", "html", sa="right", sb="right", dashed=True,
          color=CRIO["gray"], label="trazabilidad", rad=-0.45)
    arrow("html", "chart", color=CRIO["blue_dark"])
    arrow("chart", "user", sa="bottom", sb="top", color=CRIO["blue_dark"])
    arrow("rules", "f2", dashed=True, color=CRIO["gray"], label="fase 2", rad=-0.35)
    arrow("f2", "f3", sa="bottom", sb="top", dashed=True, color=CRIO["gray"])

    out = Path(__file__).resolve().parents[1] / "docs" / "arquitectura_flujo.svg"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, format="svg", bbox_inches="tight")
    plt.close(fig)
    print(f"SVG generado: {out}")
    return out


if __name__ == "__main__":
    main()
