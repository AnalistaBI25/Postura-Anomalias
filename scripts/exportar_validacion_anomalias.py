"""
Exporta el paquete de validación experta de alertas y modelos sombra.

Toma la unión de alertas oficiales, IF global, IF segmentado y LOF segmentado,
les añade EXPLICABILIDAD y deja columnas vacías para el veredicto del experto.
Los modelos sombra no modifican la alerta oficial.

No modifica el pipeline ni el modelo: solo lee la salida ya generada.

Uso:
    python scripts/exportar_validacion_anomalias.py
    python scripts/exportar_validacion_anomalias.py --top 60
    python scripts/exportar_validacion_anomalias.py --solo-oficial

Salida:
    reports/tables/validacion_top_anomalias_explicada.csv

ADVERTENCIA: el archivo contiene datos reales. No publicar (reports/ está en
.gitignore). Es para revisión operativa local.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from granjas_anomalias.config import load_config  # noqa: E402

# Features interpretables para explicar la anomalía (con nombre amigable).
EXPLAIN_FEATURES = {
    "consumo_g_ave_dia_real": "consumo g/ave",
    "brecha_consumo_pct_dia": "brecha consumo vs estandar",
    "cambio_consumo_pct_dia": "cambio diario de consumo",
    "mortalidad_por_1000": "mortalidad por mil",
    "ratio_produccion_vs_estandar": "produccion vs estandar",
    "consumo_std_7d": "variabilidad consumo 7d",
}


def _robust_z_per_group(series: pd.Series) -> pd.Series:
    median = series.median()
    mad = (series - median).abs().median() * 1.4826
    if not np.isfinite(mad) or mad < 1e-9:
        return pd.Series(0.0, index=series.index)
    return (series - median) / mad


def _candidate_origin(row: pd.Series) -> str:
    official = bool(row.get("es_anomalia", False))
    if_global = bool(row.get("flag_ml", False))
    if_age = bool(row.get("flag_iforest_segmentado", False))
    lof = bool(row.get("flag_lof", False))
    agreement = int(row.get("acuerdo_modelos", 0) or 0)
    if agreement >= 2:
        return f"consenso_{agreement}_de_3" + ("_y_oficial" if official else "")
    if official:
        return "alerta_oficial"
    if lof:
        return "solo_lof_sombra"
    if if_age:
        return "solo_if_segmentado"
    if if_global:
        return "solo_if_global"
    return "sin_bandera"


def build_package(
    df: pd.DataFrame,
    top: int | None,
    include_shadow: bool = True,
) -> pd.DataFrame:
    available = [c for c in EXPLAIN_FEATURES if c in df.columns]
    # z robusto por ciclo: "que tan raro es este dia para ESTA parvada".
    z_cols = {}
    for col in available:
        z = df.groupby("cycle_id")[col].transform(_robust_z_per_group)
        z_cols[col] = z.replace([np.inf, -np.inf], np.nan)
    z_frame = pd.DataFrame(z_cols, index=df.index)

    def dominant(idx, k=3):
        row_z = z_frame.loc[idx].abs().dropna()
        if row_z.empty:
            return "(sin desviaciones medibles)"
        top_feats = row_z.sort_values(ascending=False).head(k)
        parts = []
        for feat in top_feats.index:
            z_val = z_frame.loc[idx, feat]
            raw_val = df.loc[idx, feat]
            parts.append(f"{EXPLAIN_FEATURES[feat]} (z={z_val:+.1f}, valor={raw_val:.2f})")
        return "; ".join(parts)

    official = df["es_anomalia"].fillna(False).astype(bool)
    shadow_flags = [
        column
        for column in ["flag_ml", "flag_iforest_segmentado", "flag_lof"]
        if column in df.columns
    ]
    candidate = official.copy()
    if include_shadow and shadow_flags:
        candidate |= df[shadow_flags].fillna(False).astype(bool).any(axis=1)

    anomalies = df.loc[candidate].copy()
    anomalies["origen_candidato"] = anomalies.apply(_candidate_origin, axis=1)
    score_columns = [
        column
        for column in [
            "score_anomalia",
            "score_ml",
            "score_iforest_segmentado",
            "score_lof",
        ]
        if column in anomalies.columns
    ]
    anomalies["score_maximo_modelos"] = anomalies[score_columns].max(axis=1)
    sort_columns = ["es_anomalia", "score_maximo_modelos"]
    if "acuerdo_modelos" in anomalies.columns:
        sort_columns.insert(1, "acuerdo_modelos")
    anomalies = anomalies.sort_values(sort_columns, ascending=False)
    if top:
        anomalies = anomalies.head(top)

    anomalies["features_dominantes"] = [dominant(i) for i in anomalies.index]

    out_cols = [
        ("fecha", "fecha"),
        ("caseta", "caseta"),
        ("orden_operativa", "orden"),
        ("edad_semana", "edad_semana"),
        ("fase_alimento_principal", "fase"),
        ("consumo_real_kg_dia", "consumo_real_kg"),
        ("consumo_estandar_kg_dia", "consumo_estandar_kg"),
        ("score_anomalia", "score"),
        ("score_ml", "score_if_global"),
        ("flag_ml", "flag_if_global"),
        ("score_iforest_segmentado", "score_if_edad"),
        ("flag_iforest_segmentado", "flag_if_edad"),
        ("score_lof", "score_lof_edad"),
        ("flag_lof", "flag_lof_edad"),
        ("segmento_modelo_sombra", "segmento_modelo"),
        ("acuerdo_modelos", "acuerdo_modelos"),
        ("origen_candidato", "origen_candidato"),
        ("severidad", "severidad"),
        ("motivo_anomalia", "motivo_modelo"),
        ("features_dominantes", "features_dominantes"),
    ]
    present = [(src, dst) for src, dst in out_cols if src in anomalies.columns]
    package = anomalies[[src for src, _ in present]].copy()
    package.columns = [dst for _, dst in present]

    # Columnas vacias para el veredicto del experto.
    package["clasificacion_experto"] = ""  # real | esperado | ajuste_sap | error_dato | falsa_alarma
    package["es_anomalia_real"] = ""        # si | no
    package["comentario"] = ""
    return package.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Exporta paquete de validacion de anomalias")
    parser.add_argument(
        "--config",
        default=str(ROOT / "config" / "project.yml"),
        help="Archivo YAML que contiene project.farm_id.",
    )
    parser.add_argument("--input")
    parser.add_argument("--output")
    parser.add_argument("--top", type=int, default=0, help="0 = todas las anomalias")
    parser.add_argument(
        "--solo-oficial",
        action="store_true",
        help="Excluye candidatos exclusivos de IF/LOF sombra.",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    input_path = (
        Path(args.input)
        if args.input
        else config.resolve("processed_dir") / "10_features_y_scores_diarios.csv"
    )
    if not input_path.exists():
        raise FileNotFoundError(
            f"No existe {input_path}. Ejecuta primero el pipeline de Fase 1."
        )

    df = pd.read_csv(input_path, parse_dates=["fecha"])
    if "es_anomalia" not in df.columns:
        raise ValueError("El CSV no contiene la columna 'es_anomalia'.")

    package = build_package(
        df,
        top=args.top or None,
        include_shadow=not args.solo_oficial,
    )

    output_path = (
        Path(args.output)
        if args.output
        else config.resolve("tables_dir") / "validacion_top_anomalias_explicada.csv"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    package.to_csv(output_path, index=False, encoding="utf-8-sig")

    print(f"Casos exportados para validacion: {len(package)}")
    print(f"Archivo: {output_path}")
    print("\nVista previa (top 8 por score):")
    preview_cols = [c for c in ["fecha", "caseta", "score", "severidad", "features_dominantes"] if c in package.columns]
    with pd.option_context("display.max_colwidth", 70, "display.width", 200):
        print(package[preview_cols].head(8).to_string(index=False))


if __name__ == "__main__":
    main()
