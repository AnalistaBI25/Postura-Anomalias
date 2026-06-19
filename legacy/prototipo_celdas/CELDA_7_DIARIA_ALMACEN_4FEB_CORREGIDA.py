# ============================================================
# CELDA 7 — Dashboard ejecutivo CRÍO con Chart.js
# Periodos productivos + estándar por edad + ICA semanal
# ============================================================

from pathlib import Path
from IPython.display import display, HTML, IFrame
import json
import re
import numpy as np
import pandas as pd


# ------------------------------------------------------------
# 0. Parámetros configurables
# ------------------------------------------------------------

MIN_RATIO_PRODUCCION_ESTANDAR = 0.30
USAR_ICA_ARRANQUE_DIARIO = True
ALTURA_IFRAME = 1080


# ------------------------------------------------------------
# 1. Validación y lectura de la base diaria
# ------------------------------------------------------------

_SOURCE_NAME = "linea_diaria_" + "cic" + "los_con_stock_alimento"

if _SOURCE_NAME not in globals():
    raise ValueError(
        "No existe la base diaria esperada. Ejecuta primero las celdas de reconstrucción y stock."
    )

_df_source = globals()[_SOURCE_NAME]

if not isinstance(_df_source, pd.DataFrame) or _df_source.empty:
    raise ValueError("La base diaria está vacía o no es un DataFrame.")

df_periodos = _df_source.copy()
df_periodos["fecha"] = pd.to_datetime(df_periodos["fecha"], errors="coerce")
df_periodos = df_periodos.dropna(subset=["fecha"]).copy()

if "cycle_id" not in df_periodos.columns:
    raise ValueError("No existe la columna `cycle_id` en la base diaria.")

FIGURES_DIR = Path(getattr(config, "figures_dir", Path(".")))
TABLES_DIR = Path(getattr(config, "tables_dir", Path(".")))
OUTPUT_DIR = FIGURES_DIR / "dashboard_periodos_chartjs_crio_fases_por_caseta_timeline_limpia"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TABLES_DIR.mkdir(parents=True, exist_ok=True)
HTML_OUTPUT_PATH = OUTPUT_DIR / "dashboard_periodos_chartjs_crio_fases_por_caseta_timeline_limpia.html"


# ------------------------------------------------------------
# 2. Helpers
# ------------------------------------------------------------

def save_table_safe(df, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if "save_table" in globals():
        save_table(df, path)
    else:
        df.to_csv(path, index=False, encoding="utf-8-sig")


def safe_num(df, col, default=0.0):
    if col not in df.columns:
        return pd.Series(default, index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def first_value(df, col, default=None):
    if col not in df.columns:
        return default
    values = df[col].dropna()
    return default if values.empty else values.iloc[0]


def normalize_col(value):
    text = str(value).strip().lower()
    text = (
        text.replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
        .replace("ñ", "n")
    )
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def find_col_contains(df, candidates):
    cols = list(df.columns)
    normalized = {col: normalize_col(col) for col in cols}

    for candidate in candidates:
        candidate_norm = normalize_col(candidate)
        for col, col_norm in normalized.items():
            if col_norm == candidate_norm:
                return col

    for candidate in candidates:
        candidate_norm = normalize_col(candidate)
        for col, col_norm in normalized.items():
            if candidate_norm in col_norm:
                return col

    return None


def get_consumo_col(df):
    if "consumo_orden_alimento_kg_dia" in df.columns:
        return "consumo_orden_alimento_kg_dia"
    if "consumo_neto_alimento_kg_dia" in df.columns:
        return "consumo_neto_alimento_kg_dia"
    raise ValueError("No se encontró una columna diaria de consumo de alimento.")


def date_str(value):
    value = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(value) else value.strftime("%Y-%m-%d")


def date_label(value):
    value = pd.to_datetime(value, errors="coerce")
    return "" if pd.isna(value) else value.strftime("%d-%b-%Y")


def json_value(value):
    if value is None:
        return None
    if isinstance(value, (np.floating, float)):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if pd.isna(value):
        return None
    return value


# ------------------------------------------------------------
# 3. Lectura y preparación del estándar
# ------------------------------------------------------------

def load_standard_table():
    variable_candidates = [
        "standard", "standard_sap", "standar_sap", "std_sap",
        "df_standard", "df_estandar", "standard_df",
    ]

    for name in variable_candidates:
        value = globals().get(name)
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value.copy(), f"variable:{name}"

    search_dirs = [Path.cwd(), Path("/mnt/data")]
    if "config" in globals() and hasattr(config, "raw_dir"):
        search_dirs.insert(0, Path(config.raw_dir))

    candidates = []
    for folder in search_dirs:
        if not folder.exists():
            continue
        for path in folder.glob("*.xlsx"):
            name_norm = normalize_col(path.stem)
            if "sap" in name_norm and any(token in name_norm for token in ["standar", "standard", "estandar"]):
                candidates.append(path)

    best = None
    best_score = -1

    for path in list(dict.fromkeys(candidates)):
        try:
            sheets = pd.read_excel(path, sheet_name=None)
        except Exception:
            continue

        for sheet_name, frame in sheets.items():
            if frame.empty:
                continue
            probe = frame.copy()
            probe.columns = [normalize_col(c) for c in probe.columns]
            joined = " ".join(probe.columns)
            score = sum(token in joined for token in ["semana", "edad", "ica", "consumo", "produccion", "peso"])
            if score > best_score:
                best_score = score
                best = (probe, f"archivo:{path.name} | hoja:{sheet_name}")

    if best is None:
        return pd.DataFrame(), "no_encontrado"

    return best


def prepare_standard_table(raw):
    if raw.empty:
        return pd.DataFrame()

    std = raw.copy()
    std.columns = [normalize_col(c) for c in std.columns]

    semana_col = find_col_contains(std, ["semana_edad", "edad_semana", "semana"])
    if semana_col is None:
        return pd.DataFrame()

    ica_col = find_col_contains(std, ["ica_estandar", "ica", "conv", "conversion"])
    consumo_col = find_col_contains(std, ["consumo_estandar_ave_dia", "consumo_ave_dia", "consumo"])
    produccion_col = find_col_contains(std, ["produccion_estandar_pct_ave_dia", "porcentaje_produccion", "produccion_pct", "produccion"])
    peso_col = find_col_contains(std, ["peso_huevo_estandar_g", "peso_huevo", "gramos_huevo", "peso_promedio_huevo"])
    mortalidad_col = find_col_contains(std, ["mortalidad_estandar_pct", "mortalidad"])
    viabilidad_col = find_col_contains(std, ["viabilidad_estandar_pct", "viabilidad"])

    out = pd.DataFrame({
        "edad_semana": pd.to_numeric(std[semana_col], errors="coerce"),
        "ica_estandar_sap": pd.to_numeric(std[ica_col], errors="coerce") if ica_col else np.nan,
        "consumo_estandar_ave_dia_raw": pd.to_numeric(std[consumo_col], errors="coerce") if consumo_col else np.nan,
        "produccion_estandar_pct_ave_dia_raw": pd.to_numeric(std[produccion_col], errors="coerce") if produccion_col else np.nan,
        "peso_huevo_estandar_g": pd.to_numeric(std[peso_col], errors="coerce") if peso_col else np.nan,
        "mortalidad_estandar_pct_raw": pd.to_numeric(std[mortalidad_col], errors="coerce") if mortalidad_col else np.nan,
        "viabilidad_estandar_pct_raw": pd.to_numeric(std[viabilidad_col], errors="coerce") if viabilidad_col else np.nan,
    })

    out = out.dropna(subset=["edad_semana"]).copy()
    out["edad_semana"] = out["edad_semana"].astype(int)

    return (
        out.groupby("edad_semana", as_index=False)
        .mean(numeric_only=True)
        .sort_values("edad_semana")
        .reset_index(drop=True)
    )


# ------------------------------------------------------------
# 4. Enriquecimiento diario y reglas de ICA
# ------------------------------------------------------------

def enrich_periods(df):
    df = df.copy().sort_values(["cycle_id", "fecha"]).reset_index(drop=True)

    if "edad_semana" not in df.columns:
        raise ValueError("No existe `edad_semana`. Ejecuta antes el cálculo de edad.")

    if "dias_desde_inicio" not in df.columns:
        start = df.groupby("cycle_id")["fecha"].transform("min")
        df["dias_desde_inicio"] = (df["fecha"] - start).dt.days

    dias_inicio = (
        pd.to_numeric(df["dias_desde_inicio"], errors="coerce")
        .fillna(0)
        .astype(int)
    )

    # Política de edad:
    # fecha de entrada de aves = semana 16, día 0
    df["edad_semana"] = 16 + (dias_inicio // 7)
    df["dia_semana_edad"] = dias_inicio % 7

    std_raw, std_source = load_standard_table()
    std = prepare_standard_table(std_raw)

    if not std.empty:
        df = df.merge(std, on="edad_semana", how="left")
    else:
        for col in [
            "ica_estandar_sap", "consumo_estandar_ave_dia_raw",
            "produccion_estandar_pct_ave_dia_raw", "peso_huevo_estandar_g",
            "mortalidad_estandar_pct_raw", "viabilidad_estandar_pct_raw",
        ]:
            df[col] = np.nan

    df["fuente_estandar"] = std_source

    # Base inicial para mortalidad y viabilidad.
    if "entrada_neta_aves_ciclo" in df.columns:
        aves_iniciales = safe_num(df, "entrada_neta_aves_ciclo").replace(0, np.nan)
    elif "entrada_neta_aves" in df.columns:
        aves_iniciales = safe_num(df, "entrada_neta_aves").replace(0, np.nan)
    else:
        aves_iniciales = safe_num(df, "saldo_aves_operativo").groupby(df["cycle_id"]).transform("max")

    aves_iniciales = aves_iniciales.groupby(df["cycle_id"]).transform(lambda s: s.ffill().bfill())
    df["aves_iniciales_estandar"] = aves_iniciales

    # Base diaria para consumo y producción esperada.
    aves_disponibles = safe_num(df, "saldo_aves_operativo").replace(0, np.nan)
    aves_disponibles = aves_disponibles.groupby(df["cycle_id"]).transform(lambda s: s.ffill().bfill())
    aves_disponibles = aves_disponibles.fillna(aves_iniciales)
    df["aves_disponibles_dia"] = aves_disponibles

    consumo_raw = pd.to_numeric(df["consumo_estandar_ave_dia_raw"], errors="coerce")
    produccion_raw = pd.to_numeric(df["produccion_estandar_pct_ave_dia_raw"], errors="coerce")
    peso_huevo = pd.to_numeric(df["peso_huevo_estandar_g"], errors="coerce")
    mortalidad_raw = pd.to_numeric(df["mortalidad_estandar_pct_raw"], errors="coerce")

    consumo_mediana = consumo_raw.dropna().median()
    produccion_mediana = produccion_raw.dropna().median()
    mortalidad_mediana = mortalidad_raw.dropna().median()

    if pd.notna(consumo_mediana) and consumo_mediana > 10:
        df["consumo_estandar_kg_dia"] = aves_disponibles * consumo_raw / 1000.0
        df["unidad_consumo_estandar"] = "g_ave_dia"
    else:
        df["consumo_estandar_kg_dia"] = aves_disponibles * consumo_raw
        df["unidad_consumo_estandar"] = "kg_ave_dia"

    if pd.notna(produccion_mediana) and produccion_mediana > 1:
        produccion_fraccion = produccion_raw / 100.0
        df["unidad_produccion_estandar"] = "porcentaje"
    else:
        produccion_fraccion = produccion_raw
        df["unidad_produccion_estandar"] = "fraccion"

    df["produccion_estandar_kg_dia"] = (
        aves_disponibles * produccion_fraccion * peso_huevo / 1000.0
    )

    if pd.notna(mortalidad_mediana) and mortalidad_mediana > 1:
        mortalidad_fraccion = mortalidad_raw / 100.0
    else:
        mortalidad_fraccion = mortalidad_raw

    df["mortalidad_estandar_acum"] = aves_iniciales * mortalidad_fraccion

    consumo_col = get_consumo_col(df)
    df["consumo_real_kg_dia"] = safe_num(df, consumo_col)
    df["produccion_real_kg_dia"] = safe_num(df, "produccion_neta_huevo_kg_dia")
    df["mortalidad_real_dia"] = safe_num(df, "mortalidad_neta_aves_dia")

    group_period = df.groupby("cycle_id", sort=False)
    df["consumo_real_kg_acum"] = group_period["consumo_real_kg_dia"].cumsum()
    df["produccion_real_kg_acum"] = group_period["produccion_real_kg_dia"].cumsum()
    df["mortalidad_real_acum"] = group_period["mortalidad_real_dia"].cumsum()
    df["consumo_estandar_kg_acum"] = group_period["consumo_estandar_kg_dia"].cumsum()
    df["produccion_estandar_kg_acum"] = group_period["produccion_estandar_kg_dia"].cumsum()

    df["ica_acumulado_referencia"] = np.where(
        df["produccion_real_kg_acum"].gt(0),
        df["consumo_real_kg_acum"] / df["produccion_real_kg_acum"],
        np.nan,
    )

    first_prod = (
        df.loc[df["produccion_real_kg_dia"].gt(0)]
        .groupby("cycle_id")["fecha"].min()
    )
    df["primera_fecha_produccion"] = df["cycle_id"].map(first_prod)
    df["hay_produccion"] = df["primera_fecha_produccion"].notna()
    df["es_preproduccion"] = df["hay_produccion"] & df["fecha"].lt(df["primera_fecha_produccion"])
    df["es_primer_dia_produccion"] = df["hay_produccion"] & df["fecha"].eq(df["primera_fecha_produccion"])

    df["consumo_preproductivo_kg_dia"] = np.where(
        df["es_preproduccion"], df["consumo_real_kg_dia"], 0.0
    )
    df["consumo_preproductivo_kg_acum"] = (
        df.groupby("cycle_id")["consumo_preproductivo_kg_dia"].cumsum()
    )

    productive_mask = df["hay_produccion"] & df["fecha"].ge(df["primera_fecha_produccion"])
    df["consumo_productivo_kg_dia"] = np.where(productive_mask, df["consumo_real_kg_dia"], 0.0)
    df["produccion_productiva_kg_dia"] = np.where(productive_mask, df["produccion_real_kg_dia"], 0.0)
    df["consumo_estandar_productivo_kg_dia"] = np.where(productive_mask, df["consumo_estandar_kg_dia"], 0.0)
    df["produccion_estandar_productiva_kg_dia"] = np.where(productive_mask, df["produccion_estandar_kg_dia"], 0.0)

    week_group = df.groupby(["cycle_id", "edad_semana"], sort=False)
    df["consumo_semana_productiva_kg"] = week_group["consumo_productivo_kg_dia"].cumsum()
    df["produccion_semana_productiva_kg"] = week_group["produccion_productiva_kg_dia"].cumsum()
    df["consumo_estandar_semana_productiva_kg"] = week_group["consumo_estandar_productivo_kg_dia"].cumsum()
    df["produccion_estandar_semana_productiva_kg"] = week_group["produccion_estandar_productiva_kg_dia"].cumsum()

    df["ica_arranque_diario"] = np.where(
        df["es_primer_dia_produccion"] & df["produccion_real_kg_dia"].gt(0),
        df["consumo_real_kg_dia"] / df["produccion_real_kg_dia"],
        np.nan,
    )

    df["ica_semanal_real"] = np.where(
        df["produccion_semana_productiva_kg"].gt(0),
        df["consumo_semana_productiva_kg"] / df["produccion_semana_productiva_kg"],
        np.nan,
    )

    df["ica_estandar_calculado"] = np.where(
        df["produccion_estandar_semana_productiva_kg"].gt(0),
        df["consumo_estandar_semana_productiva_kg"] / df["produccion_estandar_semana_productiva_kg"],
        np.nan,
    )
    df["ica_estandar_principal"] = df["ica_estandar_sap"].combine_first(df["ica_estandar_calculado"])

    df["ratio_produccion_vs_estandar"] = np.where(
        df["produccion_estandar_semana_productiva_kg"].gt(0),
        df["produccion_semana_productiva_kg"] / df["produccion_estandar_semana_productiva_kg"],
        np.nan,
    )

    conditions = [
        ~df["hay_produccion"],
        df["es_preproduccion"],
        df["es_primer_dia_produccion"],
        df["produccion_semana_productiva_kg"].le(0),
        df["ratio_produccion_vs_estandar"].notna()
        & df["ratio_produccion_vs_estandar"].lt(MIN_RATIO_PRODUCCION_ESTANDAR),
    ]
    labels = [
        "Sin producción registrada",
        "Preproducción: ICA no evaluable",
        "Arranque sensible",
        "No evaluable: sin producción semanal",
        "No estable: producción baja vs estándar",
    ]
    df["estado_ica"] = np.select(conditions, labels, default="Evaluable: ICA semanal")

    df["ica_principal"] = np.nan
    if USAR_ICA_ARRANQUE_DIARIO:
        df.loc[df["es_primer_dia_produccion"], "ica_principal"] = df.loc[
            df["es_primer_dia_produccion"], "ica_arranque_diario"
        ]

    weekly_mask = df["hay_produccion"] & ~df["es_preproduccion"] & ~df["es_primer_dia_produccion"]
    df.loc[weekly_mask, "ica_principal"] = df.loc[weekly_mask, "ica_semanal_real"]

    df["brecha_ica"] = np.where(
        df["ica_principal"].notna() & df["ica_estandar_principal"].notna(),
        df["ica_principal"] - df["ica_estandar_principal"],
        np.nan,
    )
    df["brecha_ica_pct"] = np.where(
        df["ica_principal"].notna()
        & df["ica_estandar_principal"].gt(0),
        (df["ica_principal"] / df["ica_estandar_principal"] - 1) * 100,
        np.nan,
    )

    return df, std, std_source


df_periodos, standard_preparado, fuente_estandar = enrich_periods(df_periodos)

save_table_safe(standard_preparado, TABLES_DIR / "07_estandar_preparado_chartjs.csv")
save_table_safe(df_periodos, TABLES_DIR / "07_periodos_enriquecidos_chartjs.csv")


# ------------------------------------------------------------
# 5. Resumen semanal y payload
# ------------------------------------------------------------

def linear_regression_points(x_values, y_values):
    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]

    if len(x) < 2 or np.allclose(x, x[0]):
        return [], None, None, None

    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = np.sum((y - pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan

    x_min, x_max = float(np.min(x)), float(np.max(x))
    line = [
        {"x": x_min, "y": float(slope * x_min + intercept)},
        {"x": x_max, "y": float(slope * x_max + intercept)},
    ]
    return line, float(slope), float(intercept), json_value(r2)


def build_period_payload(frame):
    frame = frame.sort_values("fecha").reset_index(drop=True).copy()

    weekly = (
        frame.groupby("edad_semana", as_index=False)
        .agg(
            fecha_inicio_semana=("fecha", "min"),
            fecha_fin_semana=("fecha", "max"),
            consumo_real_kg=("consumo_real_kg_dia", "sum"),
            consumo_estandar_kg=("consumo_estandar_kg_dia", "sum"),
            produccion_real_kg=("produccion_real_kg_dia", "sum"),
            produccion_estandar_kg=("produccion_estandar_kg_dia", "sum"),
            mortalidad_real=("mortalidad_real_dia", "sum"),
            aves_promedio=("aves_disponibles_dia", "mean"),
            ica_real=("ica_semanal_real", "last"),
            ica_estandar=("ica_estandar_principal", "last"),
            estado_ica=("estado_ica", "last"),
        )
        .sort_values("edad_semana")
    )

    scatter = []
    for _, row in frame.iterrows():
        if row["consumo_real_kg_dia"] > 0 or row["produccion_real_kg_dia"] > 0:
            scatter.append({
                "x": json_value(row["consumo_real_kg_dia"]),
                "y": json_value(row["produccion_real_kg_dia"]),
                "fecha": date_label(row["fecha"]),
                "edad": f"Semana {int(row['edad_semana'])}, día {int(row['dia_semana_edad'])}",
            })

    regression, slope, intercept, r2 = linear_regression_points(
        [p["x"] for p in scatter if p["x"] is not None],
        [p["y"] for p in scatter if p["y"] is not None],
    )

    last = frame.iloc[-1]
    meta = {
        "periodo_id": str(first_value(frame, "cycle_id", "")),
        "centro": str(first_value(frame, "centro", "")),
        "caseta": str(first_value(frame, "almacen_aves", "")),
        "lote": str(first_value(frame, "lote_aves", "")),
        "orden": str(first_value(frame, "orden_operativa", "")),
        "estado": str(first_value(frame, "estado_ciclo_negocio", "")),
        "fecha_inicio": date_label(first_value(frame, "fecha_inicio_ciclo", frame["fecha"].min())),
        "fecha_fin": date_label(first_value(frame, "fecha_fin_ciclo", frame["fecha"].max())),
        "fuente_estandar": str(first_value(frame, "fuente_estandar", "")),
    }

    summary = {
        "aves_actuales": json_value(last["aves_disponibles_dia"]),
        "mortalidad_acum": json_value(last["mortalidad_real_acum"]),
        "consumo_acum": json_value(last["consumo_real_kg_acum"]),
        "produccion_acum": json_value(last["produccion_real_kg_acum"]),
        "ica_principal": json_value(last["ica_principal"]),
        "ica_estandar": json_value(last["ica_estandar_principal"]),
        "estado_ica": str(last["estado_ica"]),
        "consumo_preproductivo": json_value(last["consumo_preproductivo_kg_acum"]),
        "semana_actual": int(last["edad_semana"]),
        "dia_semana": int(last["dia_semana_edad"]),
        "fecha_actual": date_label(last["fecha"]),
    }

    daily_rows = []
    for _, row in frame.iterrows():
        daily_rows.append({
            "fecha": date_str(row["fecha"]),
            "fecha_label": date_label(row["fecha"]),
            "semana": int(row["edad_semana"]),
            "dia_semana": int(row["dia_semana_edad"]),
            "aves": json_value(row["aves_disponibles_dia"]),
            "mortalidad_dia": json_value(row["mortalidad_real_dia"]),
            "mortalidad_acum": json_value(row["mortalidad_real_acum"]),
            "consumo_real": json_value(row["consumo_real_kg_dia"]),
            "entrada_alimento": json_value(row.get("entrada_101_we_alimento_total_kg_dia", np.nan)),
            "consumo_estandar": json_value(row["consumo_estandar_kg_dia"]),
            "produccion_real": json_value(row["produccion_real_kg_dia"]),
            "produccion_estandar": json_value(row["produccion_estandar_kg_dia"]),
            "consumo_acum": json_value(row["consumo_real_kg_acum"]),
            "produccion_acum": json_value(row["produccion_real_kg_acum"]),
            "ica_principal": json_value(row["ica_principal"]),
            "ica_estandar": json_value(row["ica_estandar_principal"]),
            "estado_ica": str(row["estado_ica"]),
            "fase": str(row.get("fases_alimento_dia", "") or ""),
            "stock": json_value(row.get("stock_alimento_total_kg", np.nan)),

            # Movimientos que explican abastecimiento, consumo, stock y ajustes.
            "movimientos_resumen": str(row.get("movimientos_stock_resumen_dia", "") or ""),
            "movimientos_adicionales": str(row.get("eventos_contexto_sap_dia", "") or ""),
            "movimientos_operativos": str(row.get("movimientos_contexto_sap_resumen", "") or ""),

            "traspasos_internos": json_value(row.get("traspaso_301_311_alimento_kg_dia", np.nan)),
            "ajustes_inventario": json_value(row.get("ajuste_wi_alimento_kg_dia", np.nan)),
            "movimientos_logisticos": json_value(row.get("logistico_wl_alimento_kg_dia", np.nan)),
            "traslados_641_643": json_value(row.get("logistico_641_643_alimento_kg_dia", np.nan)),
            "ajustes_511_512": json_value(row.get("ajuste_511_512_alimento_kg_dia", np.nan)),
            "mermas_551_552": json_value(row.get("merma_551_552_alimento_kg_dia", np.nan)),
        })

    weekly_rows = []
    for _, row in weekly.iterrows():
        weekly_rows.append({
            "semana": int(row["edad_semana"]),
            "etiqueta": f"Sem {int(row['edad_semana'])}",
            "fecha_inicio": date_label(row["fecha_inicio_semana"]),
            "fecha_fin": date_label(row["fecha_fin_semana"]),
            "consumo_real": json_value(row["consumo_real_kg"]),
            "consumo_estandar": json_value(row["consumo_estandar_kg"]),
            "produccion_real": json_value(row["produccion_real_kg"]),
            "produccion_estandar": json_value(row["produccion_estandar_kg"]),
            "mortalidad_real": json_value(row["mortalidad_real"]),
            "aves_promedio": json_value(row["aves_promedio"]),
            "ica_real": json_value(row["ica_real"]),
            "ica_estandar": json_value(row["ica_estandar"]),
            "estado_ica": str(row["estado_ica"]),
        })

    return {
        "meta": meta,
        "summary": summary,
        "daily": daily_rows,
        "weekly": weekly_rows,
        "scatter": scatter,
        "regression": regression,
        "regression_stats": {
            "slope": json_value(slope),
            "intercept": json_value(intercept),
            "r2": r2,
        },
    }


def build_shared_store_payload(df):
    """
    Construye la vista DIARIA del almacén compartido.

    Reglas:
    - Consumo por caseta/fase: se obtiene de la línea diaria por ciclo.
    - Stock, entradas, traspasos, ajustes, logística y mermas:
      se obtienen de `linea_diaria_stock_alimento`, creada en la Celda 6A.
    - No se agrupa por semana.
    - Se conservan movimientos anteriores al inicio biológico de las aves,
      por ejemplo una entrada 101 WE de referencia.
    """
    base = df.copy()
    base["fecha"] = pd.to_datetime(base["fecha"], errors="coerce")
    base = base.dropna(subset=["fecha"]).copy()

    caseta_col = "almacen_aves" if "almacen_aves" in base.columns else None
    if caseta_col is None:
        raise ValueError(
            "No existe `almacen_aves`; no es posible separar el consumo por caseta."
        )

    base["caseta_consumo"] = (
        base[caseta_col]
        .astype(str)
        .str.strip()
        .replace({
            "nan": "Sin asignar",
            "None": "Sin asignar",
            "<NA>": "Sin asignar",
            "": "Sin asignar",
        })
    )

    base["consumo_caseta_kg"] = pd.to_numeric(
        base["consumo_real_kg_dia"],
        errors="coerce",
    ).fillna(0.0).abs()

    base["fase_consumo"] = (
        base.get("fases_alimento_dia", pd.Series("", index=base.index))
        .fillna("")
        .astype(str)
        .str.strip()
    )

    phase_material_map = {
        "Fase 1": "10007",
        "Fase 2": "10008",
        "Fase 3": "10009",
        "Fase 4": "10010",
        "Fase 5": "10011",
    }
    phase_order = list(phase_material_map.keys()) + [
        "Transición / sin desglose"
    ]

    # Detectar columnas de consumo por material/fase.
    normalized_cols = {col: normalize_col(col) for col in base.columns}
    phase_source_cols = {}

    for phase, material in phase_material_map.items():
        matches = []

        for col, norm in normalized_cols.items():
            if material not in norm:
                continue
            if not any(
                token in norm
                for token in ["consumo", "salida", "261", "262"]
            ):
                continue
            if any(
                token in norm
                for token in ["estandar", "stock", "entrada", "saldo"]
            ):
                continue

            score = 0
            score += 6 if "consumo" in norm else 0
            score += 4 if "kg_dia" in norm or norm.endswith("_kg") else 0
            score += 3 if "neto" in norm else 0
            score += 2 if "orden" in norm else 0
            matches.append((score, col))

        if matches:
            matches.sort(reverse=True)
            phase_source_cols[phase] = matches[0][1]

    phase_records = []
    using_material_columns = bool(phase_source_cols)

    for _, row in base.iterrows():
        total = float(row["consumo_caseta_kg"])
        found_specific = False

        if using_material_columns:
            for phase in phase_material_map:
                source_col = phase_source_cols.get(phase)

                if source_col is None:
                    continue

                value = pd.to_numeric(
                    pd.Series([row.get(source_col)]),
                    errors="coerce",
                ).iloc[0]

                value = 0.0 if pd.isna(value) else abs(float(value))

                if value > 1e-9:
                    found_specific = True
                    phase_records.append({
                        "fecha": row["fecha"],
                        "caseta_consumo": row["caseta_consumo"],
                        "fase": phase,
                        "consumo_kg": value,
                    })

        if total > 1e-9 and not found_specific:
            raw_phase = str(row["fase_consumo"] or "").strip()
            detected = [
                phase
                for phase in phase_material_map
                if phase.lower() in raw_phase.lower()
            ]
            phase = (
                detected[0]
                if len(detected) == 1
                else "Transición / sin desglose"
            )

            phase_records.append({
                "fecha": row["fecha"],
                "caseta_consumo": row["caseta_consumo"],
                "fase": phase,
                "consumo_kg": total,
            })

    phase_daily = pd.DataFrame(
        phase_records,
        columns=["fecha", "caseta_consumo", "fase", "consumo_kg"],
    )

    consumo_diario = (
        base.groupby(
            ["fecha", "caseta_consumo"],
            as_index=False,
        )["consumo_caseta_kg"]
        .sum()
    )

    # Fuente global creada por la Celda 6A.
    warehouse_candidates = [
        "linea_diaria_stock_alimento",
        "stock_alimento_diario",
        "linea_diaria_almacen_alimento",
        "almacen_alimento_diario",
        "stock_diario_alimento_1100",
    ]

    warehouse_source_name = None
    warehouse = None

    for name in warehouse_candidates:
        value = globals().get(name)

        if isinstance(value, pd.DataFrame) and not value.empty:
            warehouse_source_name = name
            warehouse = value.copy()
            break

    if warehouse is None:
        raise ValueError(
            "No existe una línea global diaria del almacén. "
            "Ejecuta primero la Celda 6A corregida y verifica que exista "
            "`linea_diaria_stock_alimento`."
        )

    warehouse.columns = [normalize_col(col) for col in warehouse.columns]

    if "fecha" not in warehouse.columns:
        raise ValueError(
            f"La fuente global `{warehouse_source_name}` no contiene `fecha`."
        )

    warehouse["fecha"] = pd.to_datetime(
        warehouse["fecha"],
        errors="coerce",
    )
    warehouse = warehouse.dropna(subset=["fecha"]).copy()

    def warehouse_col(candidates):
        for candidate in candidates:
            if candidate in warehouse.columns:
                return candidate
        return None

    source_cols = {
        "stock": warehouse_col([
            "stock_alimento_total_kg",
            "stock_cierre_kg",
            "stock_alimento",
        ]),
        "entradas": warehouse_col([
            "entrada_101_we_alimento_total_kg_dia",
            "entrada_101_we_kg_dia",
            "entrada_stock_alimento_total_kg_dia",
        ]),
        "consumo_total": warehouse_col([
            "consumo_total_almacen_alimento_kg_dia",
            "consumo_total_almacen_kg_dia",
        ]),
        "traspasos": warehouse_col([
            "traspaso_301_311_alimento_kg_dia",
            "traspaso_301_311_kg_dia",
        ]),
        "ajustes_wi": warehouse_col([
            "ajuste_wi_alimento_kg_dia",
            "ajuste_wi_kg_dia",
        ]),
        "ajustes_511_512": warehouse_col([
            "ajuste_511_512_alimento_kg_dia",
            "ajuste_511_512_kg_dia",
        ]),
        "logistica": warehouse_col([
            "logistico_wl_alimento_kg_dia",
            "logistico_wl_kg_dia",
        ]),
        "traslados_641_643": warehouse_col([
            "logistico_641_643_alimento_kg_dia",
            "logistico_641_643_kg_dia",
        ]),
        "mermas": warehouse_col([
            "merma_551_552_alimento_kg_dia",
            "merma_551_552_kg_dia",
        ]),
        "movimientos": warehouse_col([
            "movimientos_stock_resumen_dia",
            "movimientos_stock_resumen",
        ]),
        "eventos": warehouse_col([
            "eventos_stock_resumen_dia",
            "eventos_stock_resumen",
        ]),
    }

    daily_global = pd.DataFrame({
        "fecha": sorted(warehouse["fecha"].unique())
    })

    for out_col, source_col in source_cols.items():
        if source_col is None:
            daily_global[out_col] = (
                ""
                if out_col in ["movimientos", "eventos"]
                else (np.nan if out_col == "stock" else 0.0)
            )
            continue

        temp = warehouse[["fecha", source_col]].copy()

        if out_col in ["movimientos", "eventos"]:
            values = (
                temp.groupby("fecha")[source_col]
                .agg(compact_unique)
                .rename(out_col)
                .reset_index()
            )
        elif out_col == "stock":
            temp[source_col] = pd.to_numeric(
                temp[source_col],
                errors="coerce",
            )
            values = (
                temp.dropna(subset=[source_col])
                .groupby("fecha", as_index=False)[source_col]
                .last()
                .rename(columns={source_col: out_col})
            )
        else:
            temp[source_col] = pd.to_numeric(
                temp[source_col],
                errors="coerce",
            ).fillna(0.0)
            values = (
                temp.groupby("fecha", as_index=False)[source_col]
                .sum()
                .rename(columns={source_col: out_col})
            )

        daily_global = daily_global.merge(
            values,
            on="fecha",
            how="left",
        )

    daily_global["stock"] = pd.to_numeric(
        daily_global["stock"],
        errors="coerce",
    ).ffill()

    numeric_global_cols = [
        "entradas",
        "consumo_total",
        "traspasos",
        "ajustes_wi",
        "ajustes_511_512",
        "logistica",
        "traslados_641_643",
        "mermas",
    ]

    for col in numeric_global_cols:
        daily_global[col] = pd.to_numeric(
            daily_global[col],
            errors="coerce",
        ).fillna(0.0)

    for col in ["movimientos", "eventos"]:
        daily_global[col] = daily_global[col].fillna("")

    # Calendario diario global completo.
    first_date = min(
        daily_global["fecha"].min(),
        consumo_diario["fecha"].min(),
    )
    last_date = max(
        daily_global["fecha"].max(),
        consumo_diario["fecha"].max(),
    )

    calendar = pd.DataFrame({
        "fecha": pd.date_range(first_date, last_date, freq="D")
    })

    daily_global = (
        calendar.merge(daily_global, on="fecha", how="left")
        .sort_values("fecha")
        .reset_index(drop=True)
    )

    daily_global["stock"] = pd.to_numeric(
        daily_global["stock"],
        errors="coerce",
    ).ffill()

    for col in numeric_global_cols:
        daily_global[col] = pd.to_numeric(
            daily_global[col],
            errors="coerce",
        ).fillna(0.0)

    for col in ["movimientos", "eventos"]:
        daily_global[col] = daily_global[col].fillna("")

    casetas = sorted(
        consumo_diario["caseta_consumo"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    # Diccionarios diarios por caseta.
    consumo_lookup = {}
    for _, row in consumo_diario.iterrows():
        key = date_str(row["fecha"])
        consumo_lookup.setdefault(
            key,
            {caseta: 0.0 for caseta in casetas},
        )
        consumo_lookup[key][str(row["caseta_consumo"])] = float(
            row["consumo_caseta_kg"]
        )

    phase_lookup = {}
    if not phase_daily.empty:
        grouped_phase = (
            phase_daily.groupby(
                ["fecha", "caseta_consumo", "fase"],
                as_index=False,
            )["consumo_kg"]
            .sum()
        )

        for _, row in grouped_phase.iterrows():
            key = date_str(row["fecha"])
            caseta = str(row["caseta_consumo"])
            phase = str(row["fase"])

            phase_lookup.setdefault(key, {})
            phase_lookup[key].setdefault(
                caseta,
                {p: 0.0 for p in phase_order},
            )
            phase_lookup[key][caseta][phase] = (
                phase_lookup[key][caseta].get(phase, 0.0)
                + float(row["consumo_kg"])
            )

    rows = []

    for _, grow in daily_global.iterrows():
        key = date_str(grow["fecha"])

        consumption = {
            caseta: float(
                consumo_lookup.get(key, {}).get(caseta, 0.0)
            )
            for caseta in casetas
        }

        consumption_by_phase = {
            caseta: {
                phase: float(
                    phase_lookup
                    .get(key, {})
                    .get(caseta, {})
                    .get(phase, 0.0)
                )
                for phase in phase_order
            }
            for caseta in casetas
        }

        rows.append({
            "fecha": key,
            "etiqueta": date_label(grow["fecha"]),
            "consumo_por_caseta": consumption,
            "consumo_por_caseta_fase": consumption_by_phase,
            "stock": json_value(grow["stock"]),
            "entradas": json_value(grow["entradas"]),
            "consumo_total": json_value(grow["consumo_total"]),
            "traspasos": json_value(grow["traspasos"]),
            "ajustes": json_value(
                grow["ajustes_wi"] + grow["ajustes_511_512"]
            ),
            "logistica": json_value(
                grow["logistica"] + grow["traslados_641_643"]
            ),
            "mermas": json_value(grow["mermas"]),
            "movimientos": str(grow["movimientos"] or ""),
            "eventos": str(grow["eventos"] or ""),
        })

    return {
        "casetas": casetas,
        "phases": phase_order,
        "daily": rows,
        "warehouse_source": warehouse_source_name,
        "phase_source_columns": {
            phase: str(col)
            for phase, col in phase_source_cols.items()
        },
        "phase_split_mode": (
            "columnas_por_material"
            if using_material_columns
            else "fase_diaria_con_respaldo_transicion"
        ),
        "nota": (
            "Stock y movimientos globales diarios del almacén 1100. "
            "Consumo diario asignado por caseta y fase."
        ),
    }


def _select_warehouse_history_source(fallback_df):
    """
    Busca una base diaria global de almacén creada en celdas anteriores.
    Se priorizan tablas que contengan fecha y stock/entradas de alimento.
    Si no existe otra base adecuada, se usa la base enriquecida por ciclos.
    """
    preferred_names = [
        "linea_diaria_stock_alimento",
        "linea_stock_alimento",
        "stock_alimento_diario",
        "linea_diaria_almacen_alimento",
        "almacen_alimento_diario",
        "linea_diaria_ciclos_con_stock_alimento",
    ]

    candidates = []

    for name in preferred_names:
        value = globals().get(name)
        if isinstance(value, pd.DataFrame) and not value.empty:
            candidates.append((100, name, value))

    for name, value in globals().items():
        if not isinstance(value, pd.DataFrame) or value.empty:
            continue

        normalized = [normalize_col(c) for c in value.columns]
        joined = " ".join(normalized)

        has_date = any(c in normalized for c in ["fecha", "fecha_contabiliz", "fecha_contabilizacion"])
        has_stock = "stock_alimento_total_kg" in joined or (
            "stock" in joined and "alimento" in joined
        )
        has_entry = "entrada_101_we_alimento" in joined or (
            "entrada" in joined and "alimento" in joined
        )

        if not has_date or not (has_stock or has_entry):
            continue

        score = 0
        score += 12 if "diaria" in normalize_col(name) else 0
        score += 10 if has_stock else 0
        score += 8 if has_entry else 0
        score += 4 if "traspaso" in joined else 0
        score += 4 if "merma" in joined else 0
        score += 4 if "logistico" in joined else 0
        candidates.append((score, name, value))

    if not candidates:
        return fallback_df.copy(), "base_ciclos_enriquecida"

    candidates.sort(key=lambda item: (item[0], len(item[2])), reverse=True)
    _, name, frame = candidates[0]
    return frame.copy(), f"variable:{name}"


def build_global_center_payload(df, shared_store):
    """
    Construye una vista global del centro:
    - almacén compartido de alimento;
    - consumo y producción agregados de todos los ciclos;
    - aves activas;
    - línea del tiempo con todos los inicios, fases y cierres.
    """
    base = df.copy()
    base["fecha"] = pd.to_datetime(base["fecha"], errors="coerce")
    base = base.dropna(subset=["fecha"]).copy()

    warehouse_raw, warehouse_source = _select_warehouse_history_source(base)
    warehouse_raw = warehouse_raw.copy()
    warehouse_raw.columns = [normalize_col(c) for c in warehouse_raw.columns]

    warehouse_date_col = find_col_contains(
        warehouse_raw,
        ["fecha", "fecha_contabilizacion", "fecha_contabiliz"]
    )

    if warehouse_date_col is None:
        warehouse = pd.DataFrame({"fecha": sorted(base["fecha"].unique())})
    else:
        warehouse_raw["fecha"] = pd.to_datetime(
            warehouse_raw[warehouse_date_col], errors="coerce"
        )
        warehouse_raw = warehouse_raw.dropna(subset=["fecha"]).copy()

        def candidate_col(candidates):
            return find_col_contains(warehouse_raw, candidates)

        source_cols = {
            "stock": candidate_col([
                "stock_alimento_total_kg",
                "stock_alimento",
                "saldo_alimento",
                "stock"
            ]),
            "entrada_alimento": candidate_col([
                "entrada_101_we_alimento_total_kg_dia",
                "entrada_alimento_kg_dia",
                "entrada_101_we_alimento",
                "entrada_alimento"
            ]),
            "traspasos_internos": candidate_col([
                "traspaso_301_311_alimento_kg_dia",
                "traspasos_internos",
                "traspaso_301_311"
            ]),
            "ajustes_inventario": candidate_col([
                "ajuste_wi_alimento_kg_dia",
                "ajustes_inventario",
                "ajuste_wi"
            ]),
            "ajustes_511_512": candidate_col([
                "ajuste_511_512_alimento_kg_dia",
                "ajustes_511_512"
            ]),
            "movimientos_logisticos": candidate_col([
                "logistico_wl_alimento_kg_dia",
                "movimientos_logisticos",
                "logistico_wl"
            ]),
            "traslados_641_643": candidate_col([
                "logistico_641_643_alimento_kg_dia",
                "traslados_641_643"
            ]),
            "mermas_551_552": candidate_col([
                "merma_551_552_alimento_kg_dia",
                "mermas_551_552"
            ]),
        }

        warehouse = pd.DataFrame({"fecha": sorted(warehouse_raw["fecha"].unique())})

        for out_col, src_col in source_cols.items():
            if src_col is None:
                warehouse[out_col] = np.nan if out_col == "stock" else 0.0
                continue

            temp = warehouse_raw[["fecha", src_col]].copy()
            temp[src_col] = pd.to_numeric(temp[src_col], errors="coerce")

            if out_col == "stock":
                agg = (
                    temp.dropna(subset=[src_col])
                    .groupby("fecha", as_index=False)[src_col]
                    .last()
                    .rename(columns={src_col: out_col})
                )
            else:
                # En bases replicadas por ciclo, el mismo movimiento global puede
                # aparecer varias veces. Se conserva el primer valor no nulo/no cero.
                def first_nonzero(series):
                    values = pd.to_numeric(series, errors="coerce").dropna()
                    if values.empty:
                        return 0.0
                    nonzero = values.loc[values.abs().gt(1e-9)]
                    return float(nonzero.iloc[0] if not nonzero.empty else values.iloc[0])

                agg = (
                    temp.groupby("fecha")[src_col]
                    .agg(first_nonzero)
                    .rename(out_col)
                    .reset_index()
                )

            warehouse = warehouse.merge(agg, on="fecha", how="left")

    required_warehouse_cols = [
        "stock", "entrada_alimento", "traspasos_internos",
        "ajustes_inventario", "ajustes_511_512",
        "movimientos_logisticos", "traslados_641_643",
        "mermas_551_552"
    ]
    for col in required_warehouse_cols:
        if col not in warehouse.columns:
            warehouse[col] = np.nan if col == "stock" else 0.0

    warehouse["stock"] = pd.to_numeric(
        warehouse["stock"], errors="coerce"
    ).ffill()
    for col in [c for c in required_warehouse_cols if c != "stock"]:
        warehouse[col] = pd.to_numeric(
            warehouse[col], errors="coerce"
        ).fillna(0.0)

    # Agregados productivos por fecha.
    cycle_daily = (
        base.groupby("fecha", as_index=False)
        .agg(
            consumo_real=("consumo_real_kg_dia", "sum"),
            produccion_real=("produccion_real_kg_dia", "sum"),
            consumo_estandar=("consumo_estandar_kg_dia", "sum"),
            produccion_estandar=("produccion_estandar_kg_dia", "sum"),
            aves=("aves_disponibles_dia", "sum"),
            mortalidad_dia=("mortalidad_real_dia", "sum"),
        )
        .sort_values("fecha")
    )
    cycle_daily["mortalidad_acum"] = cycle_daily["mortalidad_dia"].cumsum()

    # Inicio operativo global:
    # primera entrada real de alimento identificada en la base del almacén.
    # Puede ocurrir antes o después del inicio biológico de las parvadas.
    entradas_validas = warehouse.loc[
        pd.to_numeric(
            warehouse["entrada_alimento"],
            errors="coerce"
        ).fillna(0).gt(0)
    ].copy()

    fecha_inicio_alimento = (
        entradas_validas["fecha"].min()
        if not entradas_validas.empty
        else pd.NaT
    )

    # Inicio biológico más temprano entre todas las parvadas.
    fecha_inicio_aves = cycle_daily["fecha"].min()

    if pd.notna(fecha_inicio_alimento):
        date_min = min(fecha_inicio_alimento, fecha_inicio_aves)
    else:
        date_min = fecha_inicio_aves
    date_max = max(
        cycle_daily["fecha"].max(),
        warehouse["fecha"].max() if not warehouse.empty else cycle_daily["fecha"].max(),
    )

    calendar = pd.DataFrame({
        "fecha": pd.date_range(date_min, date_max, freq="D")
    })
    global_daily = (
        calendar.merge(cycle_daily, on="fecha", how="left")
        .merge(warehouse, on="fecha", how="left")
        .sort_values("fecha")
        .reset_index(drop=True)
    )

    for col in [
        "consumo_real", "produccion_real", "consumo_estandar",
        "produccion_estandar", "aves", "mortalidad_dia",
        "mortalidad_acum", "entrada_alimento", "traspasos_internos",
        "ajustes_inventario", "ajustes_511_512",
        "movimientos_logisticos", "traslados_641_643",
        "mermas_551_552"
    ]:
        global_daily[col] = pd.to_numeric(
            global_daily[col], errors="coerce"
        ).fillna(0.0)

    global_daily["stock"] = pd.to_numeric(
        global_daily["stock"], errors="coerce"
    ).ffill()

    global_daily["consumo_acum"] = global_daily["consumo_real"].cumsum()
    global_daily["produccion_acum"] = global_daily["produccion_real"].cumsum()
    global_daily["semana_calendario"] = (
        global_daily["fecha"]
        - pd.to_timedelta(global_daily["fecha"].dt.weekday, unit="D")
    )

    weekly = (
        global_daily.groupby("semana_calendario", as_index=False)
        .agg(
            fecha_fin=("fecha", "max"),
            consumo_real=("consumo_real", "sum"),
            consumo_estandar=("consumo_estandar", "sum"),
            produccion_real=("produccion_real", "sum"),
            produccion_estandar=("produccion_estandar", "sum"),
            mortalidad_real=("mortalidad_dia", "sum"),
            aves_promedio=("aves", "mean"),
        )
        .sort_values("semana_calendario")
        .reset_index(drop=True)
    )
    weekly["semana"] = np.arange(1, len(weekly) + 1)

    daily_rows = []
    for idx, row in global_daily.iterrows():
        daily_rows.append({
            "fecha": date_str(row["fecha"]),
            "fecha_label": date_label(row["fecha"]),
            "semana": int(idx // 7 + 1),
            "dia_semana": int(row["fecha"].weekday() + 1),
            "aves": json_value(row["aves"]),
            "mortalidad_dia": json_value(row["mortalidad_dia"]),
            "mortalidad_acum": json_value(row["mortalidad_acum"]),
            "consumo_real": json_value(row["consumo_real"]),
            "entrada_alimento": json_value(row["entrada_alimento"]),
            "consumo_estandar": json_value(row["consumo_estandar"]),
            "produccion_real": json_value(row["produccion_real"]),
            "produccion_estandar": json_value(row["produccion_estandar"]),
            "consumo_acum": json_value(row["consumo_acum"]),
            "produccion_acum": json_value(row["produccion_acum"]),
            "ica_principal": None,
            "ica_estandar": None,
            "estado_ica": "Vista global: ICA se evalúa por ciclo",
            "fase": "Vista global",
            "stock": json_value(row["stock"]),
            "movimientos_resumen": "",
            "movimientos_adicionales": "",
            "movimientos_operativos": "",
            "traspasos_internos": json_value(row["traspasos_internos"]),
            "ajustes_inventario": json_value(row["ajustes_inventario"]),
            "movimientos_logisticos": json_value(row["movimientos_logisticos"]),
            "traslados_641_643": json_value(row["traslados_641_643"]),
            "ajustes_511_512": json_value(row["ajustes_511_512"]),
            "mermas_551_552": json_value(row["mermas_551_552"]),
        })

    weekly_rows = []
    for _, row in weekly.iterrows():
        weekly_rows.append({
            "semana": int(row["semana"]),
            "etiqueta": pd.Timestamp(row["semana_calendario"]).strftime("%d-%b-%Y"),
            "fecha_inicio": date_label(row["semana_calendario"]),
            "fecha_fin": date_label(row["fecha_fin"]),
            "consumo_real": json_value(row["consumo_real"]),
            "consumo_estandar": json_value(row["consumo_estandar"]),
            "produccion_real": json_value(row["produccion_real"]),
            "produccion_estandar": json_value(row["produccion_estandar"]),
            "mortalidad_real": json_value(row["mortalidad_real"]),
            "aves_promedio": json_value(row["aves_promedio"]),
            "ica_real": None,
            "ica_estandar": None,
            "estado_ica": "Vista global",
        })

    scatter = [
        {
            "x": json_value(row["consumo_real"]),
            "y": json_value(row["produccion_real"]),
            "fecha": date_label(row["fecha"]),
            "edad": "Vista global",
        }
        for _, row in global_daily.iterrows()
        if float(row["consumo_real"]) > 0 or float(row["produccion_real"]) > 0
    ]

    cycle_events = []
    for cycle_id, group in base.groupby("cycle_id", dropna=True):
        group = group.sort_values("fecha")
        if group.empty:
            continue

        caseta = str(first_value(group, "almacen_aves", "-"))
        lote = str(first_value(group, "lote_aves", "-"))
        orden = str(first_value(group, "orden_operativa", "-"))
        start_date = group["fecha"].min()
        end_date = group["fecha"].max()

        cycle_events.append({
            "fecha": date_str(start_date),
            "tipo": "inicio_ciclo",
            "caseta": caseta,
            "lote": lote,
            "orden": orden,
            "titulo": f"Inicio biológico caseta {caseta}",
            "descripcion": (
                f"Lote {lote} · Orden {orden} · "
                f"Material 20019 · 101 WE · Semana 16, día 0"
            ),
        })

        first_prod_rows = group.loc[
            pd.to_numeric(group["produccion_real_kg_dia"], errors="coerce").fillna(0).gt(0)
        ]
        if not first_prod_rows.empty:
            first_prod_date = first_prod_rows["fecha"].min()
            cycle_events.append({
                "fecha": date_str(first_prod_date),
                "tipo": "primera_produccion",
                "caseta": caseta,
                "lote": lote,
                "orden": orden,
                "titulo": f"Primera producción {caseta}",
                "descripcion": f"Lote {lote} · Orden {orden}",
            })

        # Cambios de fase, no consumos diarios.
        phase_series = (
            group[["fecha", "fases_alimento_dia"]]
            .copy()
            if "fases_alimento_dia" in group.columns
            else pd.DataFrame()
        )
        if not phase_series.empty:
            phase_series["fase"] = (
                phase_series["fases_alimento_dia"]
                .fillna("")
                .astype(str)
                .str.strip()
            )
            phase_series = phase_series.loc[phase_series["fase"].ne("")].copy()
            phase_series["fase_anterior"] = phase_series["fase"].shift()
            changes = phase_series.loc[
                phase_series["fase"].ne(phase_series["fase_anterior"])
            ]
            for _, prow in changes.iterrows():
                cycle_events.append({
                    "fecha": date_str(prow["fecha"]),
                    "tipo": "cambio_fase",
                    "caseta": caseta,
                    "lote": lote,
                    "orden": orden,
                    "titulo": f"{caseta}: {prow['fase']}",
                    "descripcion": f"Cambio de fase · Lote {lote}",
                })

        cycle_events.append({
            "fecha": date_str(end_date),
            "tipo": "fin_ciclo",
            "caseta": caseta,
            "lote": lote,
            "orden": orden,
            "titulo": f"Cierre caseta {caseta}",
            "descripcion": f"Lote {lote} · Última fecha disponible",
        })

    last = global_daily.iloc[-1]
    return {
        "meta": {
            "periodo_id": "__GLOBAL__",
            "centro": str(first_value(base, "centro", "-")),
            "caseta": "Todas",
            "lote": "Todos",
            "orden": "Todas",
            "estado": "Vista global del centro",
            "fecha_inicio": date_label(global_daily["fecha"].min()),
            "fecha_fin": date_label(global_daily["fecha"].max()),
            "fuente_estandar": "ICA disponible en vista por ciclo",
            "warehouse_source": warehouse_source,
        },
        "summary": {
            "aves_actuales": json_value(last["aves"]),
            "mortalidad_acum": json_value(last["mortalidad_acum"]),
            "consumo_acum": json_value(last["consumo_acum"]),
            "produccion_acum": json_value(last["produccion_acum"]),
            "ica_principal": None,
            "ica_estandar": None,
            "estado_ica": "Selecciona un ciclo para evaluar ICA",
            "consumo_preproductivo": None,
            "semana_actual": int(len(weekly)),
            "dia_semana": int(last["fecha"].weekday() + 1),
            "fecha_actual": date_label(last["fecha"]),
        },
        "daily": daily_rows,
        "weekly": weekly_rows,
        "scatter": scatter,
        "regression": [],
        "regression_stats": {"slope": None, "intercept": None, "r2": None},
        "timeline_events": cycle_events,
        "warehouse_source": warehouse_source,
    }



periodos_payload = {}
for period_id, group in df_periodos.groupby("cycle_id", dropna=False):
    if pd.isna(period_id):
        continue
    periodos_payload[str(period_id)] = build_period_payload(group)

shared_store_payload = build_shared_store_payload(df_periodos)
global_center_payload = build_global_center_payload(
    df_periodos,
    shared_store_payload,
)

payload = {
    "generated_at": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
    "period_ids": list(periodos_payload.keys()),
    "periods": periodos_payload,
    "shared_store": shared_store_payload,
    "global": global_center_payload,
}


# ------------------------------------------------------------
# 6. Dashboard HTML5 + CSS3 + Chart.js
# ------------------------------------------------------------

html_template = r'''<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Dashboard productivo CRÍO</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8/hammer.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.2.0/dist/chartjs-plugin-zoom.min.js"></script>
<style>
:root{
  /* PALETA INSTITUCIONAL CRÍO: sustituye estos HEX aquí si Mercadotecnia actualiza la marca. */
  --crio-green-light:#88BD54;
  --crio-green-dark:#266041;
  --crio-blue-light:#00B2E3;
  --crio-blue-dark:#1A428A;
  --crio-red:#DC0814;
  --crio-yellow:#FDC600;

  /* Fondos permitidos por la identidad visual. */
  --surface:#FFFFFF;
  --surface-blue:#F2FBFE;
  --surface-green:#F5FAF0;
  --border:#CBEAF4;
  --text:#12335E;
  --text-soft:#315B7F;
  --shadow:0 10px 26px rgba(26,66,138,.10);
}
*{box-sizing:border-box;}
html,body{
  margin:0;
  min-height:100%;
  font-family:Montserrat,Arial,sans-serif;
  background:var(--surface-blue);
  color:var(--text);
}
body{padding:8px;overflow-x:hidden;}
.dashboard{
  width:min(1760px,100%);
  margin:0 auto;
  display:grid;
  gap:8px;
}
.panel{
  background:var(--surface);
  border:1px solid var(--border);
  border-radius:18px;
  box-shadow:var(--shadow);
  min-width:0;
}
.header{
  display:grid;
  grid-template-columns:minmax(290px,1.3fr) minmax(240px,.75fr) minmax(420px,1.25fr);
  gap:8px;
}
.brand{padding:24px;}
.brand h1{margin:0;font-size:clamp(21px,1.55vw,30px);line-height:1.05;color:var(--crio-blue-dark);}
.brand p{margin:5px 0 0;color:var(--text-soft);font-size:11px;line-height:1.3;}
.selector{padding:10px 12px;display:flex;flex-direction:column;justify-content:center;gap:5px;}
.selector label{font-size:12px;font-weight:800;color:var(--crio-green-dark);}
select{
  width:100%;
  min-height:34px;
  padding:7px 9px;
  border:1px solid var(--crio-blue-light);
  border-radius:12px;
  background:white;
  color:var(--crio-blue-dark);
  font-weight:800;
  outline:none;
}
.meta{
  padding:8px;
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:6px;
}
.meta-item{
  min-width:0;
  border:1px solid var(--border);
  border-radius:12px;
  padding:6px 8px;
  background:var(--surface-blue);
}
.meta-label{font-size:8px;font-weight:800;color:var(--crio-green-dark);}
.meta-value{font-size:10.5px;font-weight:900;margin-top:2px;overflow-wrap:anywhere;}
.kpis{
  display:grid;
  grid-template-columns:repeat(6,minmax(150px,1fr));
  gap:8px;
}
.kpi{padding:9px 11px;min-height:82px;display:flex;flex-direction:column;justify-content:space-between;}
.kpi-label{font-size:9px;font-weight:800;color:var(--text-soft);}
.kpi-value{font-size:clamp(18px,1.45vw,26px);font-weight:900;color:var(--crio-blue-dark);margin-top:3px;}
.kpi-note{font-size:8px;color:var(--text-soft);line-height:1.2;margin-top:3px;}
.status{
  display:inline-flex;
  align-items:center;
  width:max-content;
  max-width:100%;
  padding:4px 7px;
  border-radius:999px;
  font-size:9px;
  font-weight:900;
  background:#FFF8D6;
  color:#725A00;
  border:1px solid var(--crio-yellow);
}
.toolbar{
  padding:7px 10px;
  display:flex;
  flex-wrap:wrap;
  align-items:center;
  gap:6px;
}
.toolbar strong{color:var(--crio-blue-dark);margin-right:auto;}
button{
  min-height:30px;
  padding:5px 8px;
  border:1px solid var(--crio-blue-light);
  border-radius:10px;
  background:white;
  color:var(--crio-blue-dark);
  font-weight:900;
  cursor:pointer;
}
button:hover{background:var(--surface-blue);}
.date-slider{flex:1 1 260px;accent-color:var(--crio-blue-light);}
.date-pill{
  padding:5px 8px;
  border-radius:10px;
  background:var(--crio-blue-dark);
  color:white;
  font-size:10px;
  font-weight:900;
  white-space:nowrap;
}
.charts{
  display:grid;
  grid-template-columns:repeat(12,minmax(0,1fr));
  gap:8px;
}
.chart-card{padding:9px 11px;min-width:0;overflow:hidden;}
.chart-card.wide{grid-column:span 8;}
.chart-card.narrow{grid-column:span 4;}
.chart-card.half{grid-column:span 6;}
.chart-title{font-size:12px;font-weight:900;color:var(--crio-blue-dark);margin-bottom:2px;}
.chart-subtitle{font-size:8.5px;color:var(--text-soft);line-height:1.2;margin-bottom:5px;}
.chart-shell{position:relative;width:100%;height:205px;min-height:180px;}
.chart-shell.tall{height:225px;}
.chart-shell.timeline{height:255px;min-height:230px;}
.chart-shell canvas{display:block;width:100%!important;height:100%!important;}
.timeline-help{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px;font-size:8px;color:var(--text-soft);}
.timeline-help span{display:inline-flex;align-items:center;gap:4px;padding:3px 6px;border:1px solid var(--border);border-radius:999px;background:var(--surface-blue);}
.timeline-dot{width:8px;height:8px;border-radius:50%;display:inline-block;}
.play-button{min-width:118px;background:var(--blue-dark);color:#fff;border-color:var(--blue-dark);}
.play-button:hover{background:var(--green-dark);border-color:var(--green-dark);}
.play-button.active{background:var(--red);border-color:var(--red);}
.event-section{margin-top:6px;}
.event-strip{display:flex;gap:6px;overflow-x:auto;padding:3px 1px 5px;scroll-snap-type:x proximity;}
.event-card{flex:0 0 205px;min-height:88px;border:1px solid var(--border);border-top:4px solid var(--blue-light);border-radius:11px;padding:8px 9px;background:#fff;scroll-snap-align:start;transition:transform .2s ease,box-shadow .2s ease,opacity .2s ease;}
.event-card:hover{transform:translateY(-2px);box-shadow:var(--shadow);}
.event-card.future{opacity:.38;}

.event-card.current{box-shadow:0 0 0 3px rgba(0,178,227,.18);}
.event-card.movement{border-left:4px solid var(--blue-light);}
.event-movements{margin-top:4px;font-size:7.5px;line-height:1.25;color:var(--blue-dark);font-weight:700;}
.movement-grid{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);gap:8px;align-items:stretch;}
.movement-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px;margin-top:6px;}
.movement-mini{border:1px solid var(--border);border-radius:8px;padding:6px;background:#fff;}
.movement-mini span{display:block;font-size:7px;color:var(--text-soft);font-weight:800;}
.movement-mini strong{display:block;font-size:11px;color:var(--blue-dark);margin-top:2px;}
.play-button.active{position:relative;}
.play-button.active::after{
  content:"";
  width:6px;height:6px;border-radius:50%;
  background:var(--red);display:inline-block;margin-left:6px;
  animation:pulsePlay 1s infinite;
}
@keyframes pulsePlay{0%,100%{opacity:.35}50%{opacity:1}}
@media(max-width:900px){
  .movement-grid{grid-template-columns:1fr;}
}

.event-date{font-size:8px;font-weight:800;color:var(--blue-dark);}
.event-title{font-size:10px;font-weight:900;margin:2px 0;color:var(--blue-dark);}
.event-desc{font-size:8px;line-height:1.25;color:var(--text-soft);}
.event-value{display:inline-flex;margin-top:4px;padding:2px 5px;border-radius:999px;background:var(--pale-green);color:var(--green-dark);font-size:8px;font-weight:900;}
.cursor-note{font-size:11px;color:var(--text-soft);font-weight:700;}
.insight{
  margin-top:12px;
  padding:7px 9px;
  border-left:4px solid var(--crio-green-light);
  background:var(--surface-green);
  font-size:8px;
  line-height:1.25;
  color:var(--crio-green-dark);
}
.table-card{padding:8px 10px;overflow:hidden;}
.table-wrap{overflow:auto;max-height:250px;border:1px solid var(--border);border-radius:10px;}
table{width:100%;border-collapse:collapse;min-width:900px;background:white;}
th,td{padding:10px 11px;border-bottom:1px solid var(--border);text-align:left;font-size:11px;white-space:nowrap;}
th{position:sticky;top:0;background:var(--crio-blue-dark);color:white;z-index:1;}
tr:hover td{background:var(--surface-blue);}
.footer{padding:6px 10px;font-size:8px;color:var(--text-soft);text-align:right;}
@media(max-width:1300px){
  .header{grid-template-columns:1fr 1fr;}
  .meta{grid-column:1/-1;}
  .kpis{grid-template-columns:repeat(3,minmax(150px,1fr));}
  .chart-card.wide,.chart-card.narrow,.chart-card.half{grid-column:span 6;}
}
@media(max-width:820px){
  body{padding:10px;}
  .header{grid-template-columns:1fr;}
  .meta{grid-template-columns:repeat(2,minmax(0,1fr));}
  .kpis{grid-template-columns:repeat(2,minmax(135px,1fr));}
  .chart-card.wide,.chart-card.narrow,.chart-card.half{grid-column:1/-1;}
  .chart-shell,.chart-shell.tall{height:320px;}
  .chart-shell.timeline{height:460px;}
}
@media(max-width:520px){
  .meta,.kpis{grid-template-columns:1fr;}
  .toolbar{align-items:stretch;}
  .toolbar strong{width:100%;}
  .date-slider{flex-basis:100%;}
  .chart-shell,.chart-shell.tall{height:300px;}
  .chart-shell.timeline{height:420px;}
}

/* ============================================================
   EXTENSIONES EJECUTIVAS: GANTT, FASES Y VALIDADOR
   ============================================================ */
.gantt-shell{
  height:410px;
  min-height:360px;
}
.gantt-legend{
  display:flex;
  flex-wrap:wrap;
  gap:6px;
  margin-top:7px;
}
.gantt-chip{
  display:inline-flex;
  align-items:center;
  gap:5px;
  padding:4px 8px;
  border:1px solid var(--border);
  border-radius:999px;
  background:#fff;
  font-size:8px;
  font-weight:800;
  color:var(--blue-dark);
}
.gantt-chip b{font-size:12px;line-height:1;}
.validator-tabs{
  display:flex;
  flex-wrap:wrap;
  gap:6px;
  margin:8px 0;
}
.validator-tab{
  border:1px solid var(--border);
  background:#fff;
  color:var(--blue-dark);
  border-radius:999px;
  padding:6px 10px;
  font-size:9px;
  font-weight:900;
  cursor:pointer;
}
.validator-tab.active{
  color:#fff;
  background:var(--blue-dark);
  border-color:var(--blue-dark);
}
.validator-panel{display:none;}
.validator-panel.active{display:block;}
.validator-status{
  display:inline-flex;
  align-items:center;
  gap:5px;
  padding:3px 7px;
  border-radius:999px;
  font-size:8px;
  font-weight:900;
  background:var(--pale-green);
  color:var(--green-dark);
}
.validator-table td,.validator-table th{
  white-space:nowrap;
  vertical-align:top;
}
.validator-description{
  min-width:240px;
  max-width:420px;
  white-space:normal !important;
}
.phase-kpis{
  display:grid;
  grid-template-columns:repeat(2,minmax(0,1fr));
  gap:5px;
  margin-top:6px;
}
.phase-kpi{
  border:1px solid var(--border);
  border-radius:8px;
  padding:6px;
  background:#fff;
}
.phase-kpi span{
  display:block;
  color:var(--text-soft);
  font-size:7px;
  font-weight:800;
}
.phase-kpi strong{
  display:block;
  margin-top:2px;
  color:var(--blue-dark);
  font-size:11px;
}
.chart-card.full-analysis{grid-column:1/-1;}
@media(max-width:900px){
  .gantt-shell{height:470px;}
  .phase-kpis{grid-template-columns:1fr;}
}


.toolbar-calendar{grid-template-columns:auto auto auto auto auto auto auto minmax(180px,1fr) auto;align-items:end}.calendar-mode{display:flex;gap:8px;font-size:9px;font-weight:900;color:var(--blue-dark)}.calendar-fields{display:flex;gap:6px}.calendar-fields label{display:grid;gap:2px;font-size:8px;font-weight:900;color:var(--text-soft)}.calendar-fields input[type="date"]{border:1px solid var(--border);border-radius:8px;padding:6px;color:var(--blue-dark);background:#fff;font-weight:800}.calendar-actions{display:flex;gap:4px;flex-wrap:wrap}.hidden{display:none!important}.timeline-tools{display:flex;justify-content:flex-end;margin-bottom:6px}.timeline-expand{border:1px solid var(--border);background:#fff;color:var(--blue-dark);border-radius:8px;padding:6px 9px;font-size:8px;font-weight:900;cursor:pointer}.notion-timeline{position:relative;padding:10px 8px 12px 34px;max-height:520px;overflow:auto;border:1px solid var(--border);border-radius:12px;background:#fff}.notion-timeline::before{content:"";position:absolute;left:20px;top:16px;bottom:16px;width:3px;background:var(--blue-light);border-radius:999px}.notion-item{position:relative;display:grid;grid-template-columns:30px minmax(0,1fr);gap:8px;margin-bottom:8px}.notion-node{position:relative;width:26px;height:26px;border-radius:8px;display:grid;place-items:center;color:#fff;font-weight:950;font-size:10px;z-index:2}.notion-card{border:1px solid var(--border);border-left:5px solid var(--blue-light);border-radius:10px;padding:8px 10px;background:#fff}.notion-card.phase-block{background:var(--pale-green)}.notion-card.active{box-shadow:0 0 0 3px rgba(0,178,227,.14)}.notion-date{font-size:8px;color:var(--text-soft);font-weight:800}.notion-title{margin-top:2px;font-size:10px;color:var(--blue-dark);font-weight:950}.notion-desc{margin-top:3px;font-size:8px;color:var(--text-soft);line-height:1.35}.notion-meta{margin-top:4px;font-size:8px;color:var(--blue-dark);font-weight:850}.timeline-collapsed .notion-item:nth-child(n+16){display:none}@media(max-width:1100px){.toolbar-calendar{grid-template-columns:1fr 1fr}.calendar-actions,.calendar-fields{flex-wrap:wrap}}



/* --- Timeline horizontal con ramas --- */
.h-timeline-wrap{position:relative;border:1px solid var(--border);border-radius:12px;background:#fff;overflow:auto;padding:8px 10px 10px;}
.h-timeline{position:relative;min-height:390px;}
.h-trunk{position:absolute;left:80px;right:40px;top:172px;height:4px;background:var(--crio-blue-dark);border-radius:999px;}
.h-day-line{position:absolute;top:8px;bottom:12px;width:1px;background:rgba(0,178,227,.18);}
.h-day-label{position:absolute;top:180px;transform:translateX(-50%) rotate(-90deg);transform-origin:center;white-space:nowrap;font-size:7px;font-weight:800;color:var(--text-soft);}
.h-current-line{position:absolute;top:0;bottom:0;width:2px;border-left:2px dashed var(--red);}
.h-phase-band{position:absolute;top:18px;height:34px;border-radius:10px;padding:4px 8px;display:flex;align-items:center;justify-content:space-between;gap:8px;border:1px solid rgba(0,0,0,.06);color:#083b7a;font-size:8px;font-weight:900;overflow:hidden;white-space:nowrap;}
.h-phase-band small{font-size:7px;font-weight:800;color:rgba(8,59,122,.82);} 
.h-lane-label{position:absolute;left:8px;width:64px;text-align:right;padding-right:6px;font-size:9px;font-weight:900;color:var(--crio-blue-dark);} 
.h-event{position:absolute;min-width:54px;max-width:150px;background:#fff;border:1px solid var(--border);border-left:4px solid var(--crio-blue-light);border-radius:10px;padding:4px 7px;box-shadow:0 6px 14px rgba(0,0,0,.06);cursor:pointer;}
.h-event.compact{min-width:22px;max-width:26px;padding:3px 4px;text-align:center;border-left-width:2px;}
.h-event.current{box-shadow:0 0 0 3px rgba(220,0,20,.16),0 6px 14px rgba(0,0,0,.06);}
.h-event-icon{font-size:10px;font-weight:900;line-height:1;}
.h-event-title{font-size:7.8px;font-weight:900;color:var(--crio-blue-dark);line-height:1.15;}
.h-event-meta{margin-top:2px;font-size:7px;color:var(--text-soft);line-height:1.2;}
.h-connector{position:absolute;width:2px;background:rgba(8,59,122,.25);} 
.h-connector::after{content:'';position:absolute;left:50%;transform:translateX(-50%);width:8px;height:8px;border-radius:50%;bottom:-4px;background:currentColor;opacity:.9;}
.timeline-compact .h-event:not(.current){opacity:.92}
.timeline-compact .h-event .h-event-meta{display:none}
.timeline-compact .h-event{max-width:118px}

.chart-card.zoomable-active{box-shadow:0 0 0 3px rgba(220,0,20,.18), var(--shadow);} 
.chart-card.zoomable-active .chart-title::after{content:' · zoom activo';font-size:10px;color:var(--red);font-weight:900;}
.chart-zoom-note{margin-top:4px;font-size:7.5px;color:var(--text-soft);} 


.warehouse-phase-grid{
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:8px;
  margin-top:8px;
}
.warehouse-global-card{
  border:1px solid var(--border);
  border-radius:12px;
  padding:8px;
  background:#fff;
}
.warehouse-global-card .chart-shell{height:190px;}
.caseta-phase-card{
  border:1px solid var(--border);
  border-radius:12px;
  padding:8px;
  background:#fff;
  min-width:0;
}
.caseta-phase-title{
  font-size:10px;
  font-weight:950;
  color:var(--crio-blue-dark);
  margin-bottom:2px;
}
.caseta-phase-note{
  font-size:7.5px;
  color:var(--text-soft);
  margin-bottom:4px;
}
.caseta-phase-card .chart-shell{height:210px;}
@media(max-width:1050px){
  .warehouse-phase-grid{grid-template-columns:1fr;}
  .warehouse-global-card .chart-shell,
  .caseta-phase-card .chart-shell{height:260px;}
}

@media(max-width:900px){
  .h-timeline{min-height:430px;}
  .h-event{max-width:130px}
}

</style>
</head>
<body>
<div class="dashboard">
  <section class="header">
    <div class="panel brand">
      <h1>Análisis productivo avícola</h1>
      <p>Seguimiento diario y semanal de consumo, producción, aves disponibles e ICA frente al estándar por edad.</p>
    </div>
    <div class="panel selector">
      <label for="periodSelect">Seleccionar vista</label>
      <select id="periodSelect"></select>
      <small id="standardSource"></small>
    </div>
    <div class="panel meta">
      <div class="meta-item"><div class="meta-label">Centro</div><div class="meta-value" id="metaCentro">-</div></div>
      <div class="meta-item"><div class="meta-label">Caseta</div><div class="meta-value" id="metaCaseta">-</div></div>
      <div class="meta-item"><div class="meta-label">Estado</div><div class="meta-value" id="metaEstado">-</div></div>
      <div class="meta-item"><div class="meta-label">Lote</div><div class="meta-value" id="metaLote">-</div></div>
      <div class="meta-item"><div class="meta-label">Orden</div><div class="meta-value" id="metaOrden">-</div></div>
      <div class="meta-item"><div class="meta-label">Inicio</div><div class="meta-value" id="metaInicio">-</div></div>
    </div>
  </section>

  <section class="kpis">
    <div class="panel kpi"><div><div class="kpi-label">Aves disponibles</div><div class="kpi-value" id="kpiAves">-</div></div><div class="kpi-note">Base diaria para consumo y producción esperada.</div></div>

    <div class="panel kpi"><div><div class="kpi-label">Stock del día</div><div class="kpi-value" id="kpiStockDia">-</div></div><div class="kpi-note" id="kpiStockNota">Stock reconstruido; pendiente de validar contra SAP.</div></div>

    <div class="panel kpi"><div><div class="kpi-label">Consumo del día</div><div class="kpi-value" id="kpiConsumoDia">-</div></div><div class="kpi-note">Consumo neto de alimento registrado en la fecha seleccionada.</div></div>

    <div class="panel kpi"><div><div class="kpi-label">Entradas / reabastos del día</div><div class="kpi-value" id="kpiEntradasDia">-</div></div><div class="kpi-note">Entradas de alimento registradas en la fecha seleccionada.</div></div>

    <div class="panel kpi"><div><div class="kpi-label">Consumo acumulado</div><div class="kpi-value" id="kpiConsumo">-</div></div><div class="kpi-note">Kilogramos registrados durante el periodo.</div></div>
    <div class="panel kpi"><div><div class="kpi-label">Producción acumulada</div><div class="kpi-value" id="kpiProduccion">-</div></div><div class="kpi-note">Kilogramos netos de huevo.</div></div>
    <div class="panel kpi"><div><div class="kpi-label">Mortalidad acumulada</div><div class="kpi-value" id="kpiMortalidad">-</div></div><div class="kpi-note">Aves registradas durante el periodo.</div></div>
    <div class="panel kpi"><div><div class="kpi-label">ICA de la semana actual</div><div class="kpi-value" id="kpiIca">-</div></div><div class="kpi-note" id="kpiIcaStd">Estándar: -</div></div>
    <div class="panel kpi"><div><div class="kpi-label">Estado ICA</div><div class="status" id="kpiEstado">-</div></div><div class="kpi-note" id="kpiEdad">-</div></div>
  </section>

  <section class="panel toolbar toolbar-calendar">
    <strong>Exploración temporal</strong>
    <div class="calendar-mode">
      <label><input type="radio" name="calendarMode" value="range" checked> Rango</label>
      <label><input type="radio" name="calendarMode" value="single"> Día</label>
    </div>
    <div id="calendarRangeFields" class="calendar-fields">
      <label>Desde <input id="dateFrom" type="date"></label>
      <label>Hasta <input id="dateTo" type="date"></label>
    </div>
    <div id="calendarSingleFields" class="calendar-fields hidden">
      <label>Día <input id="singleDate" type="date"></label>
    </div>
    <div class="calendar-actions">
      <button id="applyCalendarBtn">Aplicar</button>
      <button id="allPeriodBtn">Todo</button>
      <button id="last30Btn">30 días</button>
      <button id="last90Btn">90 días</button>
      <button id="currentPhaseBtn">Fase actual</button>
    </div>
    <button id="prevDay">◀ Día</button>
    <button id="playPause" class="play-button">▶ Reproducir</button>
    <button id="nextDay">Día ▶</button>
    <input class="date-slider" id="dateSlider" type="range" min="0" max="0" value="0" step="1">
    <span class="date-pill" id="datePill">-</span>
  </section>

  <section class="charts">
    <article class="panel chart-card" style="grid-column:1/-1;">
      <div class="chart-title">Línea del tiempo horizontal del periodo</div>
      <div class="chart-subtitle">Vista ejecutiva con bloques de fase y únicamente movimientos SAP o hitos no recurrentes. El detalle diario de consumo, producción y mortalidad permanece en sus gráficas y en el validador técnico.</div>
      <div class="timeline-tools"><button id="toggleTimelineBtn" class="timeline-expand">Compactar / expandir</button></div>
      <div class="h-timeline-wrap"><div id="notionTimeline" class="h-timeline"></div></div>
      <div class="gantt-legend">
        <span class="gantt-chip"><b>▰</b>Fase</span>
        <span class="gantt-chip"><b>↓</b>Entrada / reabasto</span>
                <span class="gantt-chip"><b>⇄</b>Traspaso 301/311</span>
        <span class="gantt-chip"><b>⚙</b>Ajustes 511/512 / WI</span>
        <span class="gantt-chip"><b>⇢</b>Logística WL / 641 / 643</span>
        <span class="gantt-chip"><b>▲</b>Merma 551/552</span>
        <span class="gantt-chip"><b>◆</b>Primera producción</span>
                      </div>
      <div class="insight" id="timelineInsight">La línea del tiempo se reproduce por fecha y sigue corriendo aunque hagas scroll en la página.</div>
      <div class="event-section">
        <div class="chart-title" style="font-size:18px;margin-top:8px;">Eventos y evolución del periodo</div>
        <div class="chart-subtitle">Las tarjetas se activan conforme avanza la fecha seleccionada o la reproducción automática.</div>
        <div id="eventStrip" class="event-strip"></div>
      </div>
    </article>

    <article class="panel chart-card half">
      <div class="chart-title">Producción diaria</div>
      <div class="chart-subtitle">Producción real registrada día por día. La comparación contra política se presenta semanalmente.</div>
      <div class="chart-shell tall"><canvas id="productionChart"></canvas></div>
      <div class="insight" id="productionInsight">-</div>
    </article>

    <article class="panel chart-card half">
      <div class="chart-title">Consumo diario</div>
      <div class="chart-subtitle">Consumo real registrado día por día. La comparación contra política se presenta semanalmente.</div>
      <div class="chart-shell tall"><canvas id="consumptionChart"></canvas></div>
      <div class="insight" id="consumptionInsight">-</div>
    </article>

    <article class="panel chart-card half">
      <div class="chart-title">Stock de alimento y movimientos diarios</div>
      <div class="chart-subtitle">Evolución del stock reconstruido junto con entradas, traspasos, logística, ajustes, mermas y consumo del día.</div>
      <div class="chart-shell tall"><canvas id="stockChart"></canvas></div>
      <div class="chart-zoom-note">Doble clic sobre la gráfica para activar o desactivar el zoom independiente.</div>
      <div class="insight" id="stockInsight">-</div>
    </article>

    <article class="panel chart-card half">
      <div class="chart-title">Desempeño semanal frente al estándar</div>
      <div class="chart-subtitle">Consumo y producción reales acumulados por semana frente a sus valores estándar. La semana en curso se acumula solo hasta el día seleccionado.</div>
      <div class="chart-shell tall"><canvas id="productionConsumptionChart"></canvas></div>
      <div class="insight" id="productionConsumptionInsight">-</div>
    </article>

    <article class="panel chart-card" style="grid-column:1/-1;">
      <div class="chart-title">Almacén compartido: stock global y consumo por fase de cada caseta</div>
      <div class="chart-subtitle">La primera gráfica muestra el stock y los movimientos globales del almacén. Debajo, cada caseta conserva su propia área apilada por fase sobre el mismo eje diario, sin mezclar ciclos ni forzar fechas de inicio comunes.</div>

      <div class="warehouse-global-card">
        <div class="caseta-phase-title">Stock global, entradas y movimientos del almacén compartido</div>
        <div class="caseta-phase-note">El stock pertenece al almacén común; no se asigna artificialmente a una caseta.</div>
        <div class="chart-shell"><canvas id="warehouseGlobalChart"></canvas></div>
      </div>

      <div class="warehouse-phase-grid">
        <div class="caseta-phase-card" id="phaseCasetaCard0">
          <div class="caseta-phase-title" id="phaseCasetaTitle0">Caseta 1</div>
          <div class="caseta-phase-note">Consumo diario apilado por fase.</div>
          <div class="chart-shell"><canvas id="phaseCasetaChart0"></canvas></div>
        </div>
        <div class="caseta-phase-card" id="phaseCasetaCard1">
          <div class="caseta-phase-title" id="phaseCasetaTitle1">Caseta 2</div>
          <div class="caseta-phase-note">Consumo diario apilado por fase.</div>
          <div class="chart-shell"><canvas id="phaseCasetaChart1"></canvas></div>
        </div>
        <div class="caseta-phase-card" id="phaseCasetaCard2">
          <div class="caseta-phase-title" id="phaseCasetaTitle2">Caseta 3</div>
          <div class="caseta-phase-note">Consumo diario apilado por fase.</div>
          <div class="chart-shell"><canvas id="phaseCasetaChart2"></canvas></div>
        </div>
      </div>

      <div class="phase-kpis" id="phaseKpis"></div>
      <div class="insight" id="phaseAreaInsight">Las fases se separan cuantitativamente cuando la base contiene el detalle por material; las transiciones sin desglose se conservan como categoría auditable.</div>
    </article>

    <article class="panel chart-card narrow" id="scatterCard">
      <div class="chart-title">Relación consumo–producción</div>
      <div class="chart-subtitle">Cada punto representa un día. La línea muestra la tendencia lineal y el indicador R² resume la fuerza de la relación.</div>
      <div class="chart-shell tall"><canvas id="scatterChart"></canvas></div>
      <div class="insight" id="scatterInsight">-</div>
    </article>

    <article class="panel chart-card half" id="icaCard">
      <div class="chart-title">ICA semanal por edad</div>
      <div class="chart-subtitle">Comparación del ICA real semanal contra el valor esperado para la misma semana de edad.</div>
      <div class="chart-shell"><canvas id="icaChart"></canvas></div>
      <div class="insight" id="icaInsight">-</div>
    </article>

    <article class="panel chart-card half">
      <div class="chart-title">Evolución de aves y mortalidad</div>
      <div class="chart-subtitle">Aves disponibles y mortalidad acumulada a lo largo del periodo productivo.</div>
      <div class="chart-shell"><canvas id="birdsChart"></canvas></div>
      <div class="insight" id="birdsInsight">-</div>
    </article>

    <article class="panel chart-card half">
      <div class="chart-title">Composición de movimientos de alimento</div>
      <div class="chart-subtitle">Distribución acumulada hasta la fecha seleccionada. Ayuda a explicar entradas, consumo, traspasos, ajustes, logística y mermas.</div>
      <div class="movement-grid">
        <div class="chart-shell"><canvas id="movementChart"></canvas></div>
        <div>
          <div class="movement-summary">
            <div class="movement-mini"><span>Entradas</span><strong id="mvEntradas">-</strong></div>
            <div class="movement-mini"><span>Consumo</span><strong id="mvConsumo">-</strong></div>
            <div class="movement-mini"><span>Traspasos</span><strong id="mvTraspasos">-</strong></div>
            <div class="movement-mini"><span>Ajustes</span><strong id="mvAjustes">-</strong></div>
            <div class="movement-mini"><span>Logística</span><strong id="mvLogistica">-</strong></div>
            <div class="movement-mini"><span>Mermas</span><strong id="mvMermas">-</strong></div>
          </div>
          <div class="insight" id="movementInsight">La composición se actualiza conforme avanza la reproducción.</div>
        </div>
      </div>
    </article>
  </section>

  <details class="panel table-card">
    <summary class="chart-title" style="cursor:pointer;">Resumen semanal ejecutivo</summary>
    <div class="chart-subtitle">Lectura rápida por semana de edad para validación con operación.</div>
    <div class="table-wrap">
      <table>
        <thead><tr>
          <th>Semana</th><th>Periodo de fechas</th><th>Consumo real kg</th><th>Consumo esperado kg</th>
          <th>Producción real kg</th><th>Producción esperada kg</th><th>ICA real</th><th>ICA esperado</th><th>Estado</th>
        </tr></thead>
        <tbody id="weeklyTable"></tbody>
      </table>
    </div>
  </details>

  <details class="panel table-card" id="validatorDetails">
    <summary class="chart-title" style="cursor:pointer;">Validador técnico de movimientos</summary>
    <div class="chart-subtitle">Panel de auditoría por fecha. Conserva códigos, eventos, cantidades e impacto operativo sin saturar la vista ejecutiva.</div>

    <div class="validator-tabs">
      <button class="validator-tab active" data-validator-tab="daily">Día seleccionado</button>
      <button class="validator-tab" data-validator-tab="history">Histórico hasta la fecha</button>
      <button class="validator-tab" data-validator-tab="stock">Conciliación de stock</button>
    </div>

    <div class="validator-panel active" id="validator-daily">
      <div class="table-wrap">
        <table class="validator-table">
          <thead><tr>
            <th>Fecha</th><th>Fase</th><th>Movimiento</th><th>Evento</th>
            <th>Entrada kg</th><th>Consumo kg</th><th>Traspasos kg</th>
            <th>Ajustes kg</th><th>Logística kg</th><th>Merma kg</th>
            <th>Stock kg</th><th>Descripción</th>
          </tr></thead>
          <tbody id="validatorDailyBody"></tbody>
        </table>
      </div>
    </div>

    <div class="validator-panel" id="validator-history">
      <div class="table-wrap">
        <table class="validator-table">
          <thead><tr>
            <th>Fecha</th><th>Fase</th><th>Movimiento</th><th>Evento</th>
            <th>Entrada kg</th><th>Consumo kg</th><th>Traspasos kg</th>
            <th>Ajustes kg</th><th>Logística kg</th><th>Merma kg</th>
            <th>Stock kg</th><th>Descripción</th>
          </tr></thead>
          <tbody id="validatorHistoryBody"></tbody>
        </table>
      </div>
    </div>

    <div class="validator-panel" id="validator-stock">
      <div class="table-wrap">
        <table class="validator-table">
          <thead><tr>
            <th>Fecha</th><th>Stock anterior kg</th><th>Entradas kg</th>
            <th>Consumo kg</th><th>Otros movimientos kg</th>
            <th>Stock calculado kg</th><th>Stock reconstruido kg</th><th>Diferencia kg</th><th>Validación</th>
          </tr></thead>
          <tbody id="validatorStockBody"></tbody>
        </table>
      </div>
    </div>
  </details>

  <section class="panel footer">Actualizado: <span id="generatedAt"></span></section>
</div>

<script>
const PAYLOAD = __PAYLOAD_JSON__;
const COLORS = {
  greenLight:'#88BD54', greenDark:'#266041', blueLight:'#00B2E3',
  blueDark:'#1A428A', red:'#DC0814', yellow:'#FDC600', white:'#FFFFFF',
  paleBlue:'#DDF5FB', paleGreen:'#EAF5DF'
};

const state = { mode:'global', periodId:null, data:null, index:0, currentWeek:null, charts:{}, playing:false, timer:null, speedMs:420, events:[], visibleStart:0, visibleEnd:null };
const el = id => document.getElementById(id);

function fmt(value, decimals=0){
  if(value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return Number(value).toLocaleString('es-MX',{minimumFractionDigits:decimals,maximumFractionDigits:decimals});
}
function fmtAuto(value){
  if(value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  const n = Math.abs(Number(value));
  return fmt(value, n >= 100 ? 0 : n >= 10 ? 1 : 2);
}
function destroyCharts(){
  Object.values(state.charts).forEach(value => {
    // Algunas entradas son arreglos de gráficas, por ejemplo phaseCasetas.
    if(Array.isArray(value)){
      value.forEach(chart => {
        if(chart && typeof chart.destroy === 'function'){
          chart.destroy();
        }
      });
      return;
    }

    if(value && typeof value.destroy === 'function'){
      value.destroy();
    }
  });

  state.charts = {};
}

Chart.defaults.font.family = 'Montserrat, Arial, sans-serif';
Chart.defaults.color = COLORS.blueDark;
Chart.defaults.borderColor = COLORS.paleBlue;
if(window.ChartZoom){ Chart.register(window.ChartZoom); }

const linkedCursorPlugin = {
  id:'linkedCursor',
  afterDatasetsDraw(chart){
    if(!state.data || chart.config.type === 'scatter') return;
    const scale = chart.scales.x;
    if(!scale) return;
    let x;
    if(scale.type === 'linear') x = scale.getPixelForValue(state.index);
    else x = scale.getPixelForValue(state.index);
    if(!Number.isFinite(x)) return;
    const {top,bottom} = chart.chartArea;
    const ctx = chart.ctx;
    ctx.save();
    ctx.beginPath();
    ctx.moveTo(x,top);
    ctx.lineTo(x,bottom);
    ctx.lineWidth = 2;
    ctx.strokeStyle = COLORS.red;
    ctx.setLineDash([6,5]);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = COLORS.red;
    ctx.beginPath();
    ctx.arc(x,top+7,5,0,Math.PI*2);
    ctx.fill();
    ctx.restore();
  }
};

Chart.register(linkedCursorPlugin);

const phaseBandPlugin = {
  id:'phaseBandPlugin',
  beforeDatasetsDraw(chart){
    if(chart.canvas.id !== 'timelineChart' || !state.data) return;

    const rows = state.data.daily;
    const visibleEnd = Math.min(state.index, rows.length - 1);
    if(visibleEnd < 0) return;

    const {ctx, chartArea, scales} = chart;
    const xScale = scales.x;
    const phasePalette = [
      'rgba(136,189,84,.14)',
      'rgba(0,178,227,.10)',
      'rgba(253,198,0,.13)',
      'rgba(38,96,65,.10)',
      'rgba(26,66,138,.08)'
    ];

    const segments = [];
    let start = 0;
    let current = String(rows[0]?.fase || 'Sin fase').trim() || 'Sin fase';

    for(let i=1; i<=visibleEnd; i++){
      const phase = String(rows[i]?.fase || current || 'Sin fase').trim() || current;
      if(phase !== current){
        segments.push({start,end:i-1,label:current});
        start = i;
        current = phase;
      }
    }
    segments.push({start,end:visibleEnd,label:current});

    ctx.save();
    segments.forEach((seg,idx)=>{
      const left = xScale.getPixelForValue(seg.start);
      const rightValue = Math.min(visibleEnd, seg.end + 1);
      const right = xScale.getPixelForValue(rightValue);
      const width = Math.max(2,right-left);

      ctx.fillStyle = phasePalette[idx % phasePalette.length];
      ctx.fillRect(left, chartArea.top, width, chartArea.bottom-chartArea.top);

      if(width > 54){
        ctx.fillStyle = COLORS.blueDark;
        ctx.font = '700 10px Montserrat, Arial, sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        ctx.fillText(seg.label || 'Sin fase', left + width/2, chartArea.top + 4);
      }
    });
    ctx.restore();
  }
};

function eventIcon(title){
  const t = String(title || '').toLowerCase();
  if(t.includes('entrada')) return '↓';
  if(t.includes('consumo')) return '●';
  if(t.includes('traspaso')) return '⇄';
  if(t.includes('ajuste')) return '⚙';
  if(t.includes('logíst') || t.includes('logist')) return '⇢';
  if(t.includes('merma')) return '▲';
  if(t.includes('producción') || t.includes('produccion')) return '◆';
  if(t.includes('mortalidad')) return '✚';
  if(t.includes('fase')) return '◇';
  if(t.includes('inicio')) return '◎';
  if(t.includes('fin') || t.includes('corte')) return '■';
  return '●';
}

const eventLabelPlugin = {
  id:'eventLabelPlugin',
  afterDatasetsDraw(chart){
    if(chart.canvas.id !== 'timelineChart') return;

    const {ctx,chartArea} = chart;
    let visibleCounter = 0;

    chart.data.datasets.forEach((dataset,datasetIndex)=>{
      if(dataset.type !== 'scatter' || dataset.hidden) return;
      const meta = chart.getDatasetMeta(datasetIndex);
      const point = meta.data?.[0];
      if(!point) return;

      const raw = dataset.data?.[0] || {};
      const x = point.x;
      const eventIndex = Number(dataset.eventIndex ?? raw.x ?? -1);
      if(eventIndex > state.index) return;

      const row = visibleCounter % 3;
      visibleCounter += 1;
      const y = chartArea.top + 20 + row * 27;
      const title = dataset.label || raw.eventLabel || 'Movimiento';
      const icon = eventIcon(title);

      ctx.save();

      ctx.strokeStyle = dataset.borderColor || COLORS.blueLight;
      ctx.lineWidth = 1;
      ctx.setLineDash([3,3]);
      ctx.beginPath();
      ctx.moveTo(x, y+16);
      ctx.lineTo(x, chartArea.bottom);
      ctx.stroke();
      ctx.setLineDash([]);

      const label = `${icon} ${title}`;
      ctx.font = '700 9px Montserrat, Arial, sans-serif';
      const labelWidth = Math.min(150, ctx.measureText(label).width + 12);
      const boxX = Math.max(
        chartArea.left,
        Math.min(x-labelWidth/2, chartArea.right-labelWidth)
      );

      ctx.fillStyle = 'rgba(255,255,255,.94)';
      ctx.strokeStyle = dataset.borderColor || COLORS.blueLight;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(boxX,y,labelWidth,18,7);
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = COLORS.blueDark;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(label,boxX+labelWidth/2,y+9);

      ctx.restore();
    });
  }
};

Chart.register(phaseBandPlugin,eventLabelPlugin);


function commonOptions(){
  return {
    responsive:true,
    maintainAspectRatio:false,
    interaction:{mode:'nearest',intersect:false},
    animation:{duration:300},
    plugins:{
      legend:{position:'bottom',labels:{usePointStyle:true,boxWidth:9,padding:16}},
      tooltip:{backgroundColor:COLORS.blueDark,titleColor:COLORS.white,bodyColor:COLORS.white,padding:10},
      zoom:{
        pan:{enabled:false,mode:'x'},
        zoom:{wheel:{enabled:false},pinch:{enabled:false},drag:{enabled:false},mode:'x'},
        limits:{x:{min:'original',max:'original'}}
      }
    },
    scales:{
      x:{grid:{color:COLORS.paleBlue},ticks:{minRotation:0,maxRotation:90,autoSkip:true,maxTicksLimit:10}},
      y:{grid:{color:COLORS.paleBlue},beginAtZero:true}
    }
  };
}



function toggleChartZoom(chart){
  if(!chart) return;
  if(typeof chart.resetZoom !== 'function'){
    alert('El complemento de zoom no cargó. Verifica conexión a internet y vuelve a ejecutar la celda.');
    return;
  }
  chart._zoomEnabled = !chart._zoomEnabled;
  const opts = chart.options.plugins?.zoom;
  if(!opts) return;
  opts.pan.enabled = chart._zoomEnabled;
  opts.pan.mode = 'x';
  opts.zoom.wheel.enabled = chart._zoomEnabled;
  opts.zoom.pinch.enabled = chart._zoomEnabled;
  opts.zoom.drag = {enabled:chart._zoomEnabled,backgroundColor:'rgba(220,0,20,.12)',borderColor:COLORS.red,borderWidth:1};
  const card = chart.canvas.closest('.chart-card');
  if(card) card.classList.toggle('zoomable-active', chart._zoomEnabled);
  chart.canvas.style.cursor = chart._zoomEnabled ? 'crosshair' : 'default';
  if(!chart._zoomEnabled && typeof chart.resetZoom === 'function') chart.resetZoom();
  chart.update('none');
}

function attachDoubleClickZoom(chart){
  if(!chart || !chart.canvas) return;
  chart.canvas.title = 'Doble clic para activar el zoom. Después usa la rueda para acercar y arrastra para desplazarte.';
  if(chart.canvas.dataset.zoomBound === '1') return;
  chart.canvas.dataset.zoomBound = '1';
  chart.canvas.addEventListener('dblclick', (ev)=>{ev.preventDefault(); toggleChartZoom(chart);});
}

function normalizeToLane(values, laneCenter, amplitude){
  const valid = values.filter(v => v !== null && v !== undefined && !Number.isNaN(Number(v))).map(Number);
  if(!valid.length) return values.map(()=>laneCenter);
  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const span = Math.abs(max-min) < 1e-9 ? 1 : max-min;
  return values.map(v => {
    if(v === null || v === undefined || Number.isNaN(Number(v))) return null;
    return laneCenter - amplitude/2 + ((Number(v)-min)/span)*amplitude;
  });
}

function buildTimelineEvents(d){
  const events = [];
  if(!d.length) return events;

  const laneMap = {
    'Inicio / cierre':6,
    'Entradas de alimento':5,
    'Traspasos':4,
    'Ajustes / mermas':3,
    'Logística':2,
    'Hitos productivos':1
  };

  const pushEvent = (index,lane,title,description,color,style,value='',codes='') => {
    if(index < 0 || index >= d.length) return;
    events.push({
      x:index,
      y:laneMap[lane],
      lane,
      label:title,
      title,
      description,
      color,
      style,
      value,
      codes,
      date:d[index].fecha_label
    });
  };


  if(state.mode === 'global' && Array.isArray(state.data.timeline_events)){
    const colorByType = {
      inicio_ciclo: COLORS.blueDark,
      primera_produccion: COLORS.greenDark,
      cambio_fase: COLORS.yellow,
      fin_ciclo: COLORS.blueLight
    };
    const laneByType = {
      inicio_ciclo: 'Inicio / cierre',
      primera_produccion: 'Hitos productivos',
      cambio_fase: 'Hitos productivos',
      fin_ciclo: 'Inicio / cierre'
    };

    state.data.timeline_events.forEach(event=>{
      const index = d.findIndex(row => row.fecha === event.fecha);
      if(index < 0) return;
      pushEvent(
        index,
        laneByType[event.tipo] || 'Hitos productivos',
        event.titulo || event.tipo,
        event.descripcion || '',
        colorByType[event.tipo] || COLORS.blueDark,
        event.tipo === 'cambio_fase' ? 'rect' : 'rectRot',
        event.caseta ? `Caseta ${event.caseta}` : '',
        [event.lote ? `Lote ${event.lote}` : '', event.orden ? `Orden ${event.orden}` : '']
          .filter(Boolean).join(' · ')
      );
    });
  }

  // El inicio genérico solo aplica al detalle de un ciclo.
  if(state.mode !== 'global'){
    pushEvent(
      0,'Inicio / cierre','Inicio de parvada',
      `Inicio del ciclo con ${fmtAuto(d[0].aves)} aves disponibles.`,
      COLORS.blueDark,'rectRot',`${fmtAuto(d[0].aves)} aves`,
      d[0].movimientos_adicionales || d[0].movimientos_operativos || '20019 · 101 WE'
    );
  }

  let firstProductionAdded = false;
  d.forEach((r,i)=>{
    if(Number(r.entrada_alimento || 0) !== 0){
      const esPrimerAbastecimiento =
        state.mode === 'global' &&
        !d.slice(0,i).some(
          row => Number(row.entrada_alimento || 0) > 0
        );

      pushEvent(
        i,
        'Entradas de alimento',
        esPrimerAbastecimiento
          ? 'Inicio operativo / primer abastecimiento'
          : 'Entrada / reabasto de alimento',
        esPrimerAbastecimiento
          ? `Primer abastecimiento del periodo global: ${fmtAuto(r.entrada_alimento)} kg.`
          : `Entrada neta registrada: ${fmtAuto(r.entrada_alimento)} kg.`,
        COLORS.greenDark,
        'rect',
        `${fmtAuto(r.entrada_alimento)} kg`,
        r.movimientos_resumen || '101 WE'
      );
    }

    if(Number(r.traspasos_internos || 0) !== 0){
      pushEvent(
        i,'Traspasos','Traspaso interno de alimento',
        `Movimiento interno neto: ${fmtAuto(r.traspasos_internos)} kg.`,
        COLORS.yellow,'rectRot',`${fmtAuto(r.traspasos_internos)} kg`,
        '301 / 311'
      );
    }

    const ajustes = Number(r.ajustes_inventario || 0) + Number(r.ajustes_511_512 || 0);
    if(Math.abs(ajustes) > 1e-9){
      pushEvent(
        i,'Ajustes / mermas','Ajuste de inventario',
        `Ajuste neto registrado: ${fmtAuto(ajustes)} kg.`,
        COLORS.blueDark,'rect',`${fmtAuto(ajustes)} kg`,
        r.movimientos_resumen || '511 / 512 / WI'
      );
    }

    if(Math.abs(Number(r.mermas_551_552 || 0)) > 1e-9){
      pushEvent(
        i,'Ajustes / mermas','Merma de alimento',
        `Merma neta registrada: ${fmtAuto(r.mermas_551_552)} kg.`,
        COLORS.red,'triangle',`${fmtAuto(r.mermas_551_552)} kg`,
        '551 / 552'
      );
    }

    const logistica = Number(r.movimientos_logisticos || 0) + Number(r.traslados_641_643 || 0);
    if(Math.abs(logistica) > 1e-9){
      pushEvent(
        i,'Logística','Movimiento logístico / tránsito',
        `Movimiento logístico neto: ${fmtAuto(logistica)} kg.`,
        COLORS.blueLight,'triangle',`${fmtAuto(logistica)} kg`,
        r.movimientos_resumen || '641 / 643 / WL'
      );
    }

    // Solo el primer día de producción se conserva como hito; no se etiqueta
    // la producción diaria recurrente.
    if(!firstProductionAdded && Number(r.produccion_real || 0) > 0){
      firstProductionAdded = true;
      pushEvent(
        i,'Hitos productivos','Primera producción registrada',
        `Primer día con producción neta: ${fmtAuto(r.produccion_real)} kg.`,
        COLORS.greenLight,'star',`${fmtAuto(r.produccion_real)} kg`,
        r.movimientos_resumen || '101 / 531'
      );
    }
  });

  pushEvent(
    d.length-1,'Inicio / cierre','Corte de información',
    state.mode === 'global'
      ? `Última fecha disponible de la vista global.`
      : `Última fecha disponible del ciclo seleccionado.`,
    COLORS.blueLight,'rectRot',d[d.length-1].fecha_label,'Corte analítico'
  );

  events.sort((a,b)=>a.x-b.x || b.y-a.y);
  return events;
}


function revealSeries(values, endIndex){
  return values.map((value,index)=>index <= endIndex ? value : null);
}

function currentWeekPosition(){
  if(!state.data || !state.data.daily.length) return -1;
  const currentWeek = Number(state.data.daily[state.index].semana);
  let last = -1;
  state.data.weekly.forEach((row,index)=>{
    if(Number(row.semana) <= currentWeek) last = index;
  });
  return last;
}


function buildWeeklyProgress(endIndex=state.index){
  if(!state.data || !Array.isArray(state.data.daily)) return [];

  const end = Math.min(
    Math.max(0,endIndex),
    state.data.daily.length - 1,
    state.visibleEnd ?? state.data.daily.length - 1
  );
  const start = Math.max(0,state.visibleStart ?? 0);

  const rows = state.data.daily.slice(start,end+1);
  const grouped = new Map();

  rows.forEach(row=>{
    const week = Number(row.semana);
    if(!Number.isFinite(week)) return;

    if(!grouped.has(week)){
      grouped.set(week,{
        semana:week,
        fecha_inicio:row.fecha_label,
        fecha_fin:row.fecha_label,
        consumo_real:0,
        consumo_estandar:0,
        produccion_real:0,
        produccion_estandar:0,
        mortalidad_real:0,
        aves_sum:0,
        aves_count:0,
        dias_observados:0
      });
    }

    const bucket = grouped.get(week);
    bucket.fecha_fin = row.fecha_label;
    bucket.consumo_real += Number(row.consumo_real || 0);
    bucket.consumo_estandar += Number(row.consumo_estandar || 0);
    bucket.produccion_real += Number(row.produccion_real || 0);
    bucket.produccion_estandar += Number(row.produccion_estandar || 0);
    bucket.mortalidad_real += Number(row.mortalidad_dia || 0);

    const aves = Number(row.aves);
    if(Number.isFinite(aves)){
      bucket.aves_sum += aves;
      bucket.aves_count += 1;
    }
    bucket.dias_observados += 1;
  });

  return [...grouped.values()]
    .sort((a,b)=>a.semana-b.semana)
    .map(bucket=>{
      const policyRow = (state.data.weekly || []).find(
        row=>Number(row.semana)===Number(bucket.semana)
      );

      const produccionMinima = 0.000001;
      const icaReal = bucket.produccion_real > produccionMinima
        ? bucket.consumo_real / bucket.produccion_real
        : null;

      let icaEstandar = null;
      if(bucket.produccion_estandar > produccionMinima){
        icaEstandar = bucket.consumo_estandar / bucket.produccion_estandar;
      }else if(policyRow && policyRow.ica_estandar !== null){
        icaEstandar = Number(policyRow.ica_estandar);
      }

      return {
        ...bucket,
        etiqueta:`Sem ${bucket.semana}`,
        aves_promedio:bucket.aves_count
          ? bucket.aves_sum / bucket.aves_count
          : null,
        ica_real:Number.isFinite(icaReal) ? icaReal : null,
        ica_estandar:Number.isFinite(icaEstandar) ? icaEstandar : null,
        estado_ica:icaReal === null
          ? 'Preproducción / ICA no evaluable'
          : (
              icaEstandar === null
                ? 'ICA calculado; estándar no disponible'
                : (
                    icaReal <= icaEstandar
                      ? 'ICA igual o mejor que estándar'
                      : 'ICA por encima del estándar'
                  )
            )
      };
    });
}

function currentWeeklySnapshot(){
  const weekly = buildWeeklyProgress(state.index);
  if(!weekly.length) return null;
  return weekly[weekly.length-1];
}

function linearRegression(points){
  if(!points || points.length < 2) return {line:[],r2:null};
  const xs = points.map(p=>Number(p.x));
  const ys = points.map(p=>Number(p.y));
  const n = xs.length;
  const sx = xs.reduce((a,b)=>a+b,0);
  const sy = ys.reduce((a,b)=>a+b,0);
  const sxx = xs.reduce((a,b)=>a+b*b,0);
  const sxy = xs.reduce((a,b,i)=>a+b*ys[i],0);
  const den = n*sxx-sx*sx;
  if(Math.abs(den)<1e-9) return {line:[],r2:null};
  const slope=(n*sxy-sx*sy)/den;
  const intercept=(sy-slope*sx)/n;
  const meanY=sy/n;
  const ssTot=ys.reduce((a,y)=>a+(y-meanY)**2,0);
  const ssRes=ys.reduce((a,y,i)=>a+(y-(intercept+slope*xs[i]))**2,0);
  const r2=ssTot>0?1-ssRes/ssTot:null;
  const minX=Math.min(...xs), maxX=Math.max(...xs);
  return {line:[{x:minX,y:intercept+slope*minX},{x:maxX,y:intercept+slope*maxX}],r2};
}

function updateProgressiveCharts(){
  const d = state.data.daily;
  const end = state.index;


  if(state.charts.production){
    state.charts.production.data.datasets[0].data =
      revealSeries(d.map(r=>r.produccion_real),end);
    state.charts.production.update('none');
  }

  if(state.charts.consumption){
    state.charts.consumption.data.datasets[0].data =
      revealSeries(d.map(r=>r.consumo_real),end);
    state.charts.consumption.update('none');
  }

  if(state.charts.stock){
    state.charts.stock.data.datasets[0].data =
      revealSeries(d.map(row => row.stock), end);

    state.charts.stock.data.datasets[1].data =
      revealSeries(d.map(row => row.entrada_alimento), end);

    state.charts.stock.data.datasets[2].data =
      revealSeries(d.map(row => row.traspasos_internos), end);

    state.charts.stock.data.datasets[3].data =
      revealSeries(
        d.map(row =>
          Number(row.ajustes_inventario || 0) +
          Number(row.ajustes_511_512 || 0)
        ),
        end
      );

    state.charts.stock.data.datasets[4].data =
      revealSeries(
        d.map(row =>
          Number(row.movimientos_logisticos || 0) +
          Number(row.traslados_641_643 || 0)
        ),
        end
      );

    state.charts.stock.data.datasets[5].data =
      revealSeries(
        d.map(row => -Math.abs(Number(row.mermas_551_552 || 0))),
        end
      );

    state.charts.stock.data.datasets[6].data =
      revealSeries(
        d.map(row => -Math.abs(Number(row.consumo_real || 0))),
        end
      );

    state.charts.stock.update('none');

    const currentRow = d[end];
    if(currentRow){
      const ajustes =
        Number(currentRow.ajustes_inventario || 0) +
        Number(currentRow.ajustes_511_512 || 0);

      const logistica =
        Number(currentRow.movimientos_logisticos || 0) +
        Number(currentRow.traslados_641_643 || 0);

      el('stockInsight').textContent =
        `Stock al cierre: ${fmtAuto(currentRow.stock)} kg. ` +
        `Entradas: ${fmtAuto(currentRow.entrada_alimento)} kg; ` +
        `consumo: ${fmtAuto(currentRow.consumo_real)} kg; ` +
        `traspasos: ${fmtAuto(currentRow.traspasos_internos)} kg; ` +
        `ajustes: ${fmtAuto(ajustes)} kg; ` +
        `logística: ${fmtAuto(logistica)} kg; ` +
        `mermas: ${fmtAuto(Math.abs(Number(currentRow.mermas_551_552 || 0)))} kg.`;
    }
  }

  if(state.charts.birds){
    state.charts.birds.data.datasets[0].data = revealSeries(d.map(r=>r.aves),end);
    state.charts.birds.data.datasets[1].data = revealSeries(d.map(r=>r.mortalidad_acum),end);
    state.charts.birds.update('none');
  }

  if(state.charts.ica){
    const weekly = buildWeeklyProgress(end);
    state.charts.ica.data.labels = weekly.map(row=>row.etiqueta);
    state.charts.ica.data.datasets[0].data = weekly.map(row=>row.ica_real);
    state.charts.ica.data.datasets[1].data = weekly.map(row=>row.ica_estandar);
    state.charts.ica.update('none');
  }

  if(state.charts.movements){
    const totals = movementTotals(end);
    state.charts.movements.data.datasets[0].data = [
      totals.entradas,totals.consumo,totals.traspasos,
      totals.ajustes,totals.logistica,totals.mermas
    ];
    state.charts.movements.update('none');
    updateMovementCards(totals);
  }

  if(state.charts.productionConsumption){
    const weekly = buildWeeklyProgress(end);

    state.charts.productionConsumption.data.labels =
      weekly.map(row=>row.etiqueta);

    state.charts.productionConsumption.data.datasets[0].data =
      weekly.map(row=>row.produccion_real);
    state.charts.productionConsumption.data.datasets[1].data =
      weekly.map(row=>row.produccion_estandar);
    state.charts.productionConsumption.data.datasets[2].data =
      weekly.map(row=>row.consumo_real);
    state.charts.productionConsumption.data.datasets[3].data =
      weekly.map(row=>row.consumo_estandar);

    state.charts.productionConsumption.update('none');

    const current = weekly.length ? weekly[weekly.length-1] : null;
    el('productionConsumptionInsight').textContent = current
      ? `Semana ${current.semana}, ${current.dias_observados} día(s) acumulado(s): ` +
        `consumo ${fmtAuto(current.consumo_real)} vs. ${fmtAuto(current.consumo_estandar)} kg estándar; ` +
        `producción ${fmtAuto(current.produccion_real)} vs. ${fmtAuto(current.produccion_estandar)} kg estándar.`
      : 'No hay información semanal disponible para la fecha seleccionada.';
  }

  if(state.charts.warehouseGlobal || state.charts.phaseCasetas?.length){
    updateWarehousePhaseCharts(end);
  }

  if(state.charts.scatter){
    const points = state.data.scatter.filter(p=>{
      const idx = d.findIndex(r=>r.fecha_label===p.fecha || r.fecha===p.fecha);
      return idx >= state.visibleStart && idx <= Math.min(end,state.visibleEnd);
    });
    const reg = linearRegression(points);
    state.charts.scatter.data.datasets[0].data = points;
    state.charts.scatter.data.datasets[1].data = reg.line;
    state.charts.scatter.update('none');
    el('scatterInsight').textContent = reg.r2 === null
      ? 'Aún no hay suficientes observaciones para calcular una relación lineal.'
      : `Con los datos visibles hasta la fecha seleccionada, R² = ${fmt(reg.r2,3)}.`;
  }
}

function renderNotionTimeline(){
  const container = el('notionTimeline');
  const start = state.visibleStart;
  const end = Math.min(state.index, state.visibleEnd);
  const rows = state.data.daily.slice(start, end + 1);
  const events = state.events.filter(ev => ev.x >= start && ev.x <= end);
  const total = Math.max(1, end - start);
  const pxPerDay = total > 300 ? 7 : total > 180 ? 10 : total > 90 ? 16 : 25;
  const width = Math.max(1100, total * pxPerDay + 180);
  const laneY = {
    'Inicio / cierre':76,
    'Entradas de alimento':126,
    'Traspasos':222,
    'Ajustes / mermas':274,
    'Logística':326,
    'Hitos productivos':178
  };
  const trunkY = 190;
  const leftPad = 82;
  const laneNames = [
    ['Inicio / cierre',laneY['Inicio / cierre']],
    ['Reabastos',laneY['Entradas de alimento']],
    ['Hitos',laneY['Hitos productivos']],
    ['Traspasos',laneY['Traspasos']],
    ['Ajustes / mermas',laneY['Ajustes / mermas']],
    ['Logística',laneY['Logística']]
  ];
  const pos = idx => leftPad + (idx - start) * pxPerDay;
  const phasePalette = [COLORS.greenLight,COLORS.blueLight,COLORS.yellow,COLORS.greenDark,COLORS.blueDark];

  // En detalle de ciclo se muestran bandas de fase.
  // En vista global, los cambios de fase aparecen como hitos por caseta.
  const phaseSegments = [];
  if(state.mode !== 'global'){
    let segStart = start;
    let lastPhase = rows[0] ? (String(rows[0].fase||'Sin fase').trim()||'Sin fase') : 'Sin fase';
    rows.forEach((row,offset)=>{
      const raw = String(row.fase || '').trim();
      const phase = raw || lastPhase || 'Sin fase';
      const absolute = start + offset;
      if(phase !== lastPhase){
        phaseSegments.push({phase:lastPhase,start:segStart,end:absolute-1});
        segStart = absolute;
        lastPhase = phase;
      }
    });
    if(rows.length) phaseSegments.push({phase:lastPhase,start:segStart,end:end});
  }

  const phaseColorMap = {};
  [...new Set(phaseSegments.map(s=>s.phase))].forEach((phase,i)=>{
    phaseColorMap[phase] = phasePalette[i % phasePalette.length];
  });

  const counts = {};
  const eventHtml = events.map(ev=>{
    const key = `${ev.x}_${ev.lane}`;
    counts[key] = (counts[key] || 0) + 1;
    const cluster = counts[key] - 1;
    const x = pos(ev.x);
    const baseY = laneY[ev.lane] ?? trunkY;
    const top = baseY + cluster * 20;
    const connectorTop = Math.min(trunkY, top + 18);
    const connectorHeight = Math.max(14, Math.abs(trunkY - top) - 2);
    const icon = eventIcon(ev.title);
    const meta = [ev.date, ev.value, ev.codes].filter(Boolean).join(' · ');
    return `
      <div class="h-connector" style="left:${x}px;top:${connectorTop}px;height:${connectorHeight}px;color:${ev.color};"></div>
      <div class="h-event ${ev.x===state.index?'current':''}" data-index="${ev.x}" title="${ev.title} | ${meta} | ${ev.description}" style="left:${x-45}px;top:${top}px;border-left-color:${ev.color};">
        <div class="h-event-icon" style="color:${ev.color}">${icon}</div>
        <div class="h-event-title">${icon} ${ev.title}</div>
        <div class="h-event-meta">${meta}</div>
      </div>`;
  }).join('');

  const phaseHtml = phaseSegments.map(seg=>{
    const x = pos(seg.start);
    const w = Math.max(48, (seg.end - seg.start + 1) * pxPerDay - 2);
    const color = phaseColorMap[seg.phase] || COLORS.greenLight;
    const startDate = state.data.daily[seg.start]?.fecha_label || '';
    const endDate = state.data.daily[seg.end]?.fecha_label || '';
    return `<div class="h-phase-band" title="${seg.phase}: ${startDate} a ${endDate}" style="left:${x}px;width:${w}px;background:${color}33;border-color:${color};">
      <span>${seg.phase}</span><small>${startDate} → ${endDate}</small>
    </div>`;
  }).join('');

  const gridStep = Math.max(7, Math.round(total / 9));
  const gridHtml = [];
  for(let i=start;i<=end;i+=gridStep){
    const x = pos(i);
    const label = state.data.daily[i]?.fecha_label || '';
    gridHtml.push(`<div class="h-day-line" style="left:${x}px"></div><div class="h-day-label" style="left:${x}px">${label}</div>`);
  }
  const currentX = pos(state.index);

  container.style.width = `${width}px`;
  container.style.minHeight = '390px';
  container.innerHTML = `
    ${laneNames.map(([name,y])=>`<div class="h-lane-label" style="top:${y}px">${name}</div>`).join('')}
    <div class="h-trunk" style="top:${trunkY}px"></div>
    ${gridHtml.join('')}
    ${phaseHtml}
    <div class="h-current-line" style="left:${currentX}px"></div>
    ${eventHtml}
  `;

  container.querySelectorAll('.h-event').forEach(node=>{
    node.addEventListener('click',()=>updateDay(Number(node.dataset.index), true));
  });
  const wrap = container.parentElement;
  if(wrap){
    const desired = Math.max(0, currentX - wrap.clientWidth * 0.45);
    wrap.scrollTo({left:desired, behavior: state.playing ? 'auto' : 'smooth'});
  }

  const visiblePhase = String(state.data.daily[state.index]?.fase || 'Sin fase').trim() || 'Sin fase';
  el('timelineInsight').textContent = `Línea ejecutiva limpia. Fase visible: ${visiblePhase}. Solo se etiquetan inicio/cierre, reabastos, traspasos, ajustes, mermas, logística y primera producción. El consumo, la producción y la mortalidad diaria permanecen en sus gráficas y en el validador técnico.`;
}


function createProductionChart(){
  const d = state.data.daily;
  const labels = d.map(r => r.fecha_label);
  const options = commonOptions();
  options.scales.y = {beginAtZero:true,grid:{color:COLORS.paleBlue},title:{display:true,text:'Producción diaria kg'}};
  state.charts.production = new Chart(el('productionChart'),{
    type:'line',
    data:{labels,datasets:[
      {
        label:'Producción real diaria',
        data:revealSeries(d.map(r=>r.produccion_real),state.index),
        borderColor:COLORS.blueLight,
        backgroundColor:'rgba(0,178,227,.12)',
        fill:true,
        tension:.25,
        pointRadius:2
      }
    ]},options
  });
  attachDoubleClickZoom(state.charts.production);
}

function createConsumptionChart(){
  const d = state.data.daily;
  const labels = d.map(r => r.fecha_label);
  const options = commonOptions();
  options.scales.y = {beginAtZero:true,grid:{color:COLORS.paleBlue},title:{display:true,text:'Consumo diario kg'}};
  state.charts.consumption = new Chart(el('consumptionChart'),{
    type:'line',
    data:{labels,datasets:[
      {
        label:'Consumo real diario',
        data:revealSeries(d.map(r=>r.consumo_real),state.index),
        borderColor:COLORS.blueDark,
        backgroundColor:'rgba(31,69,143,.10)',
        fill:true,
        tension:.20,
        pointRadius:0,
        borderWidth:2
      }
    ]},options
  });
  attachDoubleClickZoom(state.charts.consumption);
}

function createStockChart(){
  const d = state.data.daily;
  const labels = d.map(r => r.fecha_label);
  const options = commonOptions();
  options.interaction = {mode:'index',intersect:false};
  options.scales.y = {position:'left',grid:{color:COLORS.paleBlue},title:{display:true,text:'Stock kg'}};
  options.scales.yMov = {position:'right',grid:{display:false},title:{display:true,text:'Movimientos kg'},stacked:false};
  state.charts.stock = new Chart(el('stockChart'),{
    data:{labels,datasets:[
      {type:'line',label:'Stock de alimento',yAxisID:'y',data:revealSeries(d.map(r=>r.stock),state.index),borderColor:COLORS.blueLight,backgroundColor:'rgba(0,178,227,.12)',fill:true,tension:.18,pointRadius:0,borderWidth:2.2,order:0},
      {type:'bar',label:'Entradas / reabastos',yAxisID:'yMov',data:revealSeries(d.map(r=>r.entrada_alimento),state.index),backgroundColor:'rgba(35,117,61,.65)',borderColor:COLORS.greenDark,borderWidth:1,order:1},
      {type:'bar',label:'Traspasos internos',yAxisID:'yMov',data:revealSeries(d.map(r=>r.traspasos_internos),state.index),backgroundColor:'rgba(240,193,0,.55)',borderColor:COLORS.yellow,borderWidth:1,order:1},
      {type:'bar',label:'Ajustes y 511/512',yAxisID:'yMov',data:revealSeries(d.map(r=>(Number(r.ajustes_inventario||0)+Number(r.ajustes_511_512||0))),state.index),backgroundColor:'rgba(31,69,143,.45)',borderColor:COLORS.blueDark,borderWidth:1,order:1},
      {type:'bar',label:'Logística WL / 641 / 643',yAxisID:'yMov',data:revealSeries(d.map(r=>(Number(r.movimientos_logisticos||0)+Number(r.traslados_641_643||0))),state.index),backgroundColor:'rgba(0,178,227,.45)',borderColor:COLORS.blueLight,borderWidth:1,order:1},
      {type:'bar',label:'Mermas 551/552',yAxisID:'yMov',data:revealSeries(d.map(r=>-Math.abs(Number(r.mermas_551_552||0))),state.index),backgroundColor:'rgba(220,0,20,.55)',borderColor:COLORS.red,borderWidth:1,order:1},
      {type:'bar',label:'Consumo del día',yAxisID:'yMov',data:revealSeries(d.map(r=>-Math.abs(Number(r.consumo_real||0))),state.index),backgroundColor:'rgba(31,69,143,.18)',borderColor:COLORS.blueDark,borderWidth:1,order:1}
    ]},
    options
  });
  attachDoubleClickZoom(state.charts.stock);
}

function createScatterChart(){
  const stats = state.data.regression_stats;
  const options = commonOptions();
  options.scales.x = {type:'linear',position:'bottom',beginAtZero:true,grid:{color:COLORS.paleBlue},title:{display:true,text:'Consumo diario kg'}};
  options.scales.y = {beginAtZero:true,grid:{color:COLORS.paleBlue},title:{display:true,text:'Producción diaria kg'}};
  options.plugins.tooltip.callbacks = {
    label:(ctx)=>{
      const raw = ctx.raw;
      return raw.fecha ? `${raw.fecha}: ${fmtAuto(raw.x)} kg consumo, ${fmtAuto(raw.y)} kg producción` : `Tendencia: ${fmtAuto(raw.y)} kg`;
    }
  };

  state.charts.scatter = new Chart(el('scatterChart'),{
    type:'scatter',
    data:{datasets:[
      {label:'Días observados',data:[],backgroundColor:COLORS.blueLight,borderColor:COLORS.blueDark,pointRadius:5,pointHoverRadius:7},
      {label:'Tendencia lineal',data:[],type:'line',borderColor:COLORS.red,borderWidth:2,pointRadius:0,fill:false}
    ]},options
  });

  const r2 = stats.r2;
  el('scatterInsight').textContent = r2 === null
    ? 'No hay suficientes observaciones para calcular una relación lineal confiable.'
    : `La relación lineal presenta R² = ${fmt(r2,3)}. Un valor cercano a 1 indica una asociación más consistente entre consumo y producción.`;
  attachDoubleClickZoom(state.charts.scatter);
}

function createIcaChart(){
  const w = buildWeeklyProgress(state.index);
  const options = commonOptions();
  options.scales.y.title = {display:true,text:'ICA semanal'};
  state.charts.ica = new Chart(el('icaChart'),{
    type:'line',
    data:{labels:w.map(r=>r.etiqueta),datasets:[
      {
        label:'ICA real semanal',
        data:w.map(r=>r.ica_real),
        borderColor:COLORS.red,
        backgroundColor:COLORS.red,
        tension:.2,
        pointRadius:4,
        spanGaps:true
      },
      {
        label:'ICA estándar semanal',
        data:w.map(r=>r.ica_estandar),
        borderColor:COLORS.greenDark,
        backgroundColor:COLORS.greenDark,
        borderDash:[6,4],
        tension:.2,
        pointRadius:3,
        spanGaps:true
      }
    ]},options
  });
  attachDoubleClickZoom(state.charts.ica);
}

function createBirdsChart(){
  const d = state.data.daily;
  const options = commonOptions();
  options.scales.y = {position:'left',beginAtZero:false,grid:{color:COLORS.paleBlue},title:{display:true,text:'Aves disponibles'}};
  options.scales.y1 = {position:'right',beginAtZero:true,grid:{drawOnChartArea:false},title:{display:true,text:'Mortalidad acumulada'}};
  state.charts.birds = new Chart(el('birdsChart'),{
    type:'line',
    data:{labels:d.map(r=>r.fecha_label),datasets:[
      {label:'Aves disponibles',data:revealSeries(d.map(r=>r.aves),state.index),borderColor:COLORS.blueDark,backgroundColor:COLORS.paleBlue,tension:.15,pointRadius:1,yAxisID:'y'},
      {label:'Mortalidad acumulada',data:revealSeries(d.map(r=>r.mortalidad_acum),state.index),borderColor:COLORS.red,backgroundColor:COLORS.red,tension:.15,pointRadius:1,yAxisID:'y1'}
    ]},options
  });
  attachDoubleClickZoom(state.charts.birds);
}

function movementTotals(endIndex){
  const rows = state.data.daily.slice(state.visibleStart,Math.min(endIndex,state.visibleEnd)+1);
  const sumAbs = key => rows.reduce((acc,r)=>{
    const value = Number(r[key]);
    return acc + (Number.isFinite(value) ? Math.abs(value) : 0);
  },0);

  return {
    entradas:sumAbs('entrada_alimento'),
    consumo:sumAbs('consumo_real'),
    traspasos:sumAbs('traspasos_internos'),
    ajustes:sumAbs('ajustes_inventario') + sumAbs('ajustes_511_512'),
    logistica:sumAbs('movimientos_logisticos') + sumAbs('traslados_641_643'),
    mermas:sumAbs('mermas_551_552')
  };
}

function updateMovementCards(totals){
  el('mvEntradas').textContent = `${fmtAuto(totals.entradas)} kg`;
  el('mvConsumo').textContent = `${fmtAuto(totals.consumo)} kg`;
  el('mvTraspasos').textContent = `${fmtAuto(totals.traspasos)} kg`;
  el('mvAjustes').textContent = `${fmtAuto(totals.ajustes)} kg`;
  el('mvLogistica').textContent = `${fmtAuto(totals.logistica)} kg`;
  el('mvMermas').textContent = `${fmtAuto(totals.mermas)} kg`;

  const sorted = Object.entries(totals).sort((a,b)=>b[1]-a[1]);
  const leader = sorted[0];
  el('movementInsight').textContent = leader && leader[1] > 0
    ? `Hasta la fecha seleccionada, el mayor volumen corresponde a ${leader[0]} con ${fmtAuto(leader[1])} kg.`
    : 'Aún no hay movimientos acumulados para la fecha seleccionada.';
}


function createProductionConsumptionChart(){
  const weekly = buildWeeklyProgress(state.index);
  const options = commonOptions();

  options.interaction = {mode:'index',intersect:false};
  options.scales.y = {
    position:'left',
    beginAtZero:true,
    grid:{color:COLORS.paleBlue},
    title:{display:true,text:'Producción semanal kg'}
  };
  options.scales.y1 = {
    position:'right',
    beginAtZero:true,
    grid:{drawOnChartArea:false},
    title:{display:true,text:'Consumo semanal kg'}
  };

  state.charts.productionConsumption = new Chart(
    el('productionConsumptionChart'),
    {
      type:'line',
      data:{
        labels:weekly.map(row=>row.etiqueta),
        datasets:[
          {
            label:'Producción real semanal',
            data:weekly.map(row=>row.produccion_real),
            borderColor:COLORS.blueLight,
            backgroundColor:'rgba(0,178,227,.12)',
            fill:true,
            tension:.25,
            pointRadius:3,
            yAxisID:'y'
          },
          {
            label:'Producción estándar semanal',
            data:weekly.map(row=>row.produccion_estandar),
            borderColor:COLORS.blueDark,
            backgroundColor:COLORS.blueDark,
            borderDash:[7,5],
            tension:.20,
            pointRadius:2,
            yAxisID:'y'
          },
          {
            label:'Consumo real semanal',
            data:weekly.map(row=>row.consumo_real),
            borderColor:COLORS.greenDark,
            backgroundColor:'rgba(38,96,65,.10)',
            fill:false,
            tension:.20,
            pointRadius:3,
            yAxisID:'y1'
          },
          {
            label:'Consumo estándar semanal',
            data:weekly.map(row=>row.consumo_estandar),
            borderColor:COLORS.greenLight,
            backgroundColor:COLORS.greenLight,
            borderDash:[7,5],
            tension:.20,
            pointRadius:2,
            yAxisID:'y1'
          }
        ]
      },
      options
    }
  );
  attachDoubleClickZoom(state.charts.productionConsumption);
}

function sharedWarehouseBuckets(endIndex){
  const daily = PAYLOAD.shared_store?.daily || [];
  if(!state.data?.daily?.length || !daily.length) return [];

  const biologicalStart =
    state.data.daily[state.visibleStart]?.fecha;

  const endDate =
    state.data.daily[Math.min(endIndex,state.visibleEnd)]?.fecha;

  if(!biologicalStart || !endDate) return [];

  // Incluir el último abastecimiento 101 WE anterior o igual al inicio
  // biológico. En 2026 esto permite incluir el 04-feb antes del 07-feb.
  const previousEntries = daily.filter(
    row =>
      row.fecha <= biologicalStart &&
      Number(row.entradas || 0) > 0
  );

  const operationalStart = previousEntries.length
    ? previousEntries[previousEntries.length - 1].fecha
    : biologicalStart;

  return daily.filter(
    row =>
      row.fecha >= operationalStart &&
      row.fecha <= endDate
  );
}

function updateWarehouseKpis(buckets,casetas){
  const c = el('phaseKpis');
  const totals = Object.fromEntries(casetas.map(caseta=>[caseta,0]));
  buckets.forEach(row=>casetas.forEach(caseta=>{
    totals[caseta] += Number(row.consumo_por_caseta?.[caseta]||0);
  }));
  const totalAll = Object.values(totals).reduce((a,b)=>a+b,0);
  const last = buckets.length ? buckets[buckets.length-1] : null;
  const selectedCaseta = String(state.data?.meta?.caseta||'');

  const cards = casetas.map(caseta=>{
    const value = totals[caseta]||0;
    const pct = totalAll>0 ? value/totalAll*100 : 0;
    const selected = caseta===selectedCaseta ? ' · seleccionada' : '';
    return `<div class="phase-kpi"><span>Caseta ${caseta}${selected}</span><strong>${fmtAuto(value)} kg</strong><span>${fmt(pct,1)}% del consumo visible del almacén</span></div>`;
  });
  cards.push(`<div class="phase-kpi"><span>Stock global al cierre visible</span><strong>${last ? fmtAuto(last.stock) : '-'} kg</strong><span>Pendiente de validar contra SAP MB5B</span></div>`);
  c.innerHTML = cards.join('');

  const selectedValue = totals[selectedCaseta]||0;
  const otherValue = Math.max(0,totalAll-selectedValue);
  const splitMode = PAYLOAD.shared_store?.phase_split_mode || '';
  const modeNote = splitMode==='columnas_por_material'
    ? 'Las fases se calcularon con columnas específicas por material.'
    : 'Las transiciones sin desglose cuantitativo se muestran como “Transición / sin desglose”.';
  el('phaseAreaInsight').textContent = last
    ? `En el rango visible, la caseta ${selectedCaseta||'-'} consumió ${fmtAuto(selectedValue)} kg y las otras casetas ${fmtAuto(otherValue)} kg. El stock global reconstruido cerró en ${fmtAuto(last.stock)} kg. ${modeNote}`
    : 'No hay datos del almacén compartido dentro del rango visible.';
}

function phaseColor(phase){
  const map = {
    'Fase 1':COLORS.blueDark,
    'Fase 2':COLORS.blueLight,
    'Fase 3':COLORS.greenDark,
    'Fase 4':COLORS.red,
    'Fase 5':COLORS.yellow,
    'Transición / sin desglose':'#8B6BB1'
  };
  return map[phase] || COLORS.greenLight;
}

function createPhaseDataset(buckets,caseta,phase){
  const color = phaseColor(phase);
  return {
    type:'line',
    label:phase,
    data:buckets.map(row=>Number(row.consumo_por_caseta_fase?.[caseta]?.[phase]||0)),
    borderColor:color,
    backgroundColor:color+'AA',
    fill:true,
    stack:`caseta_${caseta}`,
    pointRadius:0,
    pointHoverRadius:4,
    tension:.16,
    borderWidth:1.2,
    yAxisID:'y',
    phase,
    caseta
  };
}

function warehouseGlobalOptions(){
  return {
    responsive:true,
    maintainAspectRatio:false,
    interaction:{mode:'index',intersect:false},
    animation:{duration:220},
    plugins:{
      legend:{position:'bottom',labels:{usePointStyle:true,boxWidth:8,font:{size:9}}},
      tooltip:{
        callbacks:{
          label(ctx){return `${ctx.dataset.label}: ${fmtAuto(ctx.parsed.y)} kg`;}
        }
      },
      zoom:{pan:{enabled:false,mode:'x'},zoom:{wheel:{enabled:false},pinch:{enabled:false},drag:{enabled:false},mode:'x'},limits:{x:{min:'original',max:'original'}}}
    },
    scales:{
      x:{grid:{color:COLORS.paleBlue},ticks:{minRotation:0,maxRotation:90,autoSkip:true,maxTicksLimit:12}},
      y:{beginAtZero:true,grid:{color:COLORS.paleBlue},title:{display:true,text:'Stock global (kg)'}},
      y1:{position:'right',beginAtZero:true,grid:{drawOnChartArea:false},title:{display:true,text:'Movimientos semanales (kg)'}}
    }
  };
}

function casetaPhaseOptions(caseta,buckets){
  return {
    responsive:true,
    maintainAspectRatio:false,
    interaction:{mode:'index',intersect:false},
    animation:{duration:220},
    plugins:{
      legend:{position:'bottom',labels:{usePointStyle:true,boxWidth:7,font:{size:8},filter:item=>!String(item.text).includes('Transición') || item.hidden===false}},
      tooltip:{
        callbacks:{
          title(items){
            const row=buckets[items?.[0]?.dataIndex];
            return row ? `Semana ${row.fecha_inicio} a ${row.fecha_fin}` : '';
          },
          label(ctx){
            return `${ctx.dataset.label}: ${fmtAuto(ctx.parsed.y)} kg`;
          },
          footer(items){
            if(!items?.length) return '';
            const row=buckets[items[0].dataIndex];
            const phases=PAYLOAD.shared_store?.phases||[];
            const total=phases.reduce((acc,phase)=>acc+Number(row?.consumo_por_caseta_fase?.[caseta]?.[phase]||0),0);
            return `Total caseta ${caseta}: ${fmtAuto(total)} kg`;
          }
        }
      },
      zoom:{pan:{enabled:false,mode:'x'},zoom:{wheel:{enabled:false},pinch:{enabled:false},drag:{enabled:false},mode:'x'},limits:{x:{min:'original',max:'original'}}}
    },
    scales:{
      x:{stacked:true,grid:{color:COLORS.paleBlue},ticks:{minRotation:0,maxRotation:90,autoSkip:true,maxTicksLimit:9}},
      y:{stacked:true,beginAtZero:true,grid:{color:COLORS.paleBlue},title:{display:true,text:'Consumo diario (kg)'}}
    }
  };
}

function createWarehousePhaseCharts(){
  const buckets = sharedWarehouseBuckets(state.index);
  const casetas = (PAYLOAD.shared_store?.casetas || []).slice(0,3);
  const phases = PAYLOAD.shared_store?.phases || ['Fase 1','Fase 2','Fase 3','Fase 4','Fase 5','Transición / sin desglose'];
  const labels = buckets.map(row=>row.etiqueta);

  state.charts.warehouseGlobal = new Chart(el('warehouseGlobalChart'),{
    type:'line',
    data:{
      labels,
      datasets:[
        {type:'line',label:'Stock global almacén',data:buckets.map(b=>b.stock),borderColor:COLORS.red,backgroundColor:COLORS.red,fill:false,pointRadius:2,pointHoverRadius:5,tension:.12,borderWidth:2.5,yAxisID:'y',order:0},
        {type:'bar',label:'Entradas / reabastos',data:buckets.map(b=>Number(b.entradas||0)),backgroundColor:COLORS.blueLight+'66',borderColor:COLORS.blueLight,borderWidth:1,yAxisID:'y1',order:3},
        {type:'line',label:'Traspasos',data:buckets.map(b=>Number(b.traspasos||0)),borderColor:COLORS.yellow,backgroundColor:COLORS.yellow,fill:false,pointRadius:2,tension:.1,borderWidth:1.5,yAxisID:'y1'},
        {type:'line',label:'Ajustes / mermas',data:buckets.map(b=>Number(b.ajustes||0)+Number(b.mermas||0)),borderColor:COLORS.blueDark,backgroundColor:COLORS.blueDark,fill:false,pointRadius:2,tension:.1,borderWidth:1.5,yAxisID:'y1'}
      ]
    },
    options:warehouseGlobalOptions()
  });
  attachDoubleClickZoom(state.charts.warehouseGlobal);

  state.charts.phaseCasetas = [];
  for(let i=0;i<3;i++){
    const card=el(`phaseCasetaCard${i}`);
    const title=el(`phaseCasetaTitle${i}`);
    const canvas=el(`phaseCasetaChart${i}`);
    const caseta=casetas[i];
    if(!caseta){
      if(card) card.classList.add('hidden');
      continue;
    }
    if(card) card.classList.remove('hidden');
    if(title) title.textContent=`Caseta ${caseta} · consumo semanal por fase`;
    const chart = new Chart(canvas,{
      type:'line',
      data:{labels,datasets:phases.map(phase=>createPhaseDataset(buckets,caseta,phase))},
      options:casetaPhaseOptions(caseta,buckets)
    });
    state.charts.phaseCasetas.push(chart);
    attachDoubleClickZoom(chart);
  }
  updateWarehouseKpis(buckets,casetas);
}

function updateWarehousePhaseCharts(endIndex){
  const buckets = sharedWarehouseBuckets(endIndex);
  const casetas = (PAYLOAD.shared_store?.casetas || []).slice(0,3);
  const phases = PAYLOAD.shared_store?.phases || [];
  const labels = buckets.map(row=>row.etiqueta);

  if(state.charts.warehouseGlobal){
    const chart=state.charts.warehouseGlobal;
    chart.data.labels=labels;
    chart.data.datasets[0].data=buckets.map(b=>b.stock);
    chart.data.datasets[1].data=buckets.map(b=>Number(b.entradas||0));
    chart.data.datasets[2].data=buckets.map(b=>Number(b.traspasos||0));
    chart.data.datasets[3].data=buckets.map(b=>Number(b.ajustes||0)+Number(b.mermas||0));
    chart.update('none');
  }

  (state.charts.phaseCasetas||[]).forEach((chart,i)=>{
    const caseta=casetas[i];
    if(!caseta) return;
    chart.data.labels=labels;
    chart.data.datasets=phases.map(phase=>createPhaseDataset(buckets,caseta,phase));
    // Actualizar referencia del tooltip al nuevo arreglo.
    chart.options=casetaPhaseOptions(caseta,buckets);
    chart.update('none');
  });
  updateWarehouseKpis(buckets,casetas);
}


function validatorDescription(r){
  const pieces = [
    r.movimientos_resumen,
    r.movimientos_adicionales,
    r.movimientos_operativos
  ].filter(v=>v && String(v).trim() && !['nan','none','<na>'].includes(String(v).trim().toLowerCase()));

  return [...new Set(pieces)].join(' · ') || 'Sin descripción adicional';
}

function validatorRowHtml(r){
  const ajustes = Math.abs(Number(r.ajustes_inventario || 0)) + Math.abs(Number(r.ajustes_511_512 || 0));
  const logistica = Math.abs(Number(r.movimientos_logisticos || 0)) + Math.abs(Number(r.traslados_641_643 || 0));

  return `<tr>
    <td>${r.fecha_label}</td>
    <td>${r.fase || '-'}</td>
    <td>${r.movimientos_resumen || '-'}</td>
    <td>${r.movimientos_adicionales || '-'}</td>
    <td>${fmtAuto(r.entrada_alimento)}</td>
    <td>${fmtAuto(r.consumo_real)}</td>
    <td>${fmtAuto(r.traspasos_internos)}</td>
    <td>${fmtAuto(ajustes)}</td>
    <td>${fmtAuto(logistica)}</td>
    <td>${fmtAuto(r.mermas_551_552)}</td>
    <td>${fmtAuto(r.stock)}</td>
    <td class="validator-description">${validatorDescription(r)}</td>
  </tr>`;
}

function stockValidationRows(endIndex){
  const rows = state.data.daily.slice(state.visibleStart,Math.min(endIndex,state.visibleEnd)+1);
  return rows.map((r,i)=>{
    const previousStock = i > 0 ? Number(rows[i-1].stock || 0) : 0;
    const entries = Number(r.entrada_alimento || 0);
    const consumption = Number(r.consumo_real || 0);
    const other =
      Number(r.traspasos_internos || 0) +
      Number(r.ajustes_inventario || 0) +
      Number(r.movimientos_logisticos || 0) +
      Number(r.traslados_641_643 || 0) +
      Number(r.ajustes_511_512 || 0) -
      Math.abs(Number(r.mermas_551_552 || 0));

    const calculated = i === 0
      ? Number(r.stock || 0)
      : previousStock + entries - consumption + other;

    const reconstructed = Number(r.stock || 0);
    const difference = reconstructed - calculated;

    return {
      fecha:r.fecha_label,
      previousStock,
      entries,
      consumption,
      other,
      calculated,
      reconstructed,
      difference
    };
  });
}

function renderValidator(){
  const current = state.data.daily[state.index];
  el('validatorDailyBody').innerHTML = validatorRowHtml(current);

  const historyRows = state.data.daily
    .slice(0,state.index+1)
    .filter(r =>
      Number(r.entrada_alimento || 0) !== 0 ||
      Number(r.consumo_real || 0) !== 0 ||
      Number(r.traspasos_internos || 0) !== 0 ||
      Number(r.ajustes_inventario || 0) !== 0 ||
      Number(r.movimientos_logisticos || 0) !== 0 ||
      Number(r.traslados_641_643 || 0) !== 0 ||
      Number(r.ajustes_511_512 || 0) !== 0 ||
      Number(r.mermas_551_552 || 0) !== 0 ||
      Number(r.produccion_real || 0) !== 0 ||
      Number(r.mortalidad_dia || 0) !== 0
    )
    .slice(-250);

  el('validatorHistoryBody').innerHTML = historyRows.map(validatorRowHtml).join('');

  const stockRows = stockValidationRows(state.index).slice(-250);
  el('validatorStockBody').innerHTML = stockRows.map(r=>{
    const ok = Math.abs(r.difference) < .01;
    return `<tr>
      <td>${r.fecha}</td>
      <td>${fmtAuto(r.previousStock)}</td>
      <td>${fmtAuto(r.entries)}</td>
      <td>${fmtAuto(r.consumption)}</td>
      <td>${fmtAuto(r.other)}</td>
      <td>${fmtAuto(r.calculated)}</td>
      <td>${fmtAuto(r.reconstructed)}</td>
      <td>${fmtAuto(r.difference)}</td>
      <td><span class="validator-status">${ok?'Conciliado':'Revisar'}</span></td>
    </tr>`;
  }).join('');
}

function setupValidatorTabs(){
  document.querySelectorAll('.validator-tab').forEach(button=>{
    button.addEventListener('click',()=>{
      document.querySelectorAll('.validator-tab').forEach(b=>b.classList.remove('active'));
      document.querySelectorAll('.validator-panel').forEach(p=>p.classList.remove('active'));
      button.classList.add('active');
      el(`validator-${button.dataset.validatorTab}`).classList.add('active');
    });
  });
}

function createMovementChart(){
  const totals = movementTotals(state.index);
  updateMovementCards(totals);

  state.charts.movements = new Chart(el('movementChart'),{
    type:'doughnut',
    data:{
      labels:['Entradas','Consumo','Traspasos','Ajustes','Logística','Mermas'],
      datasets:[{
        data:[
          totals.entradas,totals.consumo,totals.traspasos,
          totals.ajustes,totals.logistica,totals.mermas
        ],
        backgroundColor:[
          COLORS.blueLight,COLORS.greenDark,COLORS.yellow,
          COLORS.blueDark,COLORS.greenLight,COLORS.red
        ],
        borderColor:COLORS.white,
        borderWidth:3,
        hoverOffset:6
      }]
    },
    options:{
      responsive:true,
      maintainAspectRatio:false,
      cutout:'64%',
      animation:{duration:250},
      plugins:{
        legend:{position:'bottom',labels:{usePointStyle:true,boxWidth:8,padding:10}},
        tooltip:{
          backgroundColor:COLORS.blueDark,
          titleColor:COLORS.white,
          bodyColor:COLORS.white,
          callbacks:{
            label(ctx){
              const total = ctx.dataset.data.reduce((a,b)=>a+Number(b||0),0);
              const value = Number(ctx.raw||0);
              const pct = total>0 ? value/total*100 : 0;
              return `${ctx.label}: ${fmtAuto(value)} kg (${fmt(pct,1)}%)`;
            }
          }
        }
      }
    }
  });
}

function renderEventCards(){
  const strip = el('eventStrip');
  if(!strip) return;
  const events = state.events || [];
  strip.innerHTML = events.map((ev,i)=>{
    const future = ev.x > state.index;
    const current = ev.x === state.index;
    const movementClass = ev.title === 'Movimientos registrados' ? 'movement' : '';
    return `<article class="event-card ${movementClass} ${future?'future':''} ${current?'current':''}" data-event-index="${i}" style="border-top-color:${ev.color}">
      <div class="event-date">${ev.date}</div>
      <div class="event-title">${ev.title}</div>
      <div class="event-desc">${ev.description}</div>
      ${ev.value?`<div class="event-value">${ev.value}</div>`:''}
    </article>`;
  }).join('');

  strip.querySelectorAll('.event-card').forEach((card,i)=>{
    card.addEventListener('click',()=>{
      updateDay(events[i].x,true);
    });
  });

  const activeCards = [...strip.querySelectorAll('.event-card:not(.future)')];
  if(activeCards.length){
    const target = activeCards[activeCards.length-1];
    const desiredLeft = target.offsetLeft - strip.clientWidth / 2 + target.clientWidth / 2;
    strip.scrollTo({
      left:Math.max(0,desiredLeft),
      behavior:state.playing ? 'auto' : 'smooth'
    });
  }
}

function renderTable(){
  const weekly = buildWeeklyProgress(state.index);
  el('weeklyTable').innerHTML = weekly.map(r=>`
    <tr>
      <td>Semana ${r.semana}</td>
      <td>${r.fecha_inicio} — ${r.fecha_fin} (${r.dias_observados} día(s))</td>
      <td>${fmtAuto(r.consumo_real)}</td>
      <td>${fmtAuto(r.consumo_estandar)}</td>
      <td>${fmtAuto(r.produccion_real)}</td>
      <td>${fmtAuto(r.produccion_estandar)}</td>
      <td>${fmtAuto(r.ica_real)}</td>
      <td>${fmtAuto(r.ica_estandar)}</td>
      <td>${r.estado_ica}</td>
    </tr>`).join('');
}

function updateDay(index,scrollEvent=false){
  state.index = Math.max(0,Math.min(index,state.data.daily.length-1));
  const r = state.data.daily[state.index];
  state.currentWeek = Number(r.semana);
  const weekSnapshot = currentWeeklySnapshot();
  el('dateSlider').value = state.index;
  el('datePill').textContent = `${r.fecha_label} | Semana ${r.semana}, día ${r.dia_semana}`;
  el('kpiAves').textContent = fmt(r.aves,0);

  const previousRow = state.index > 0 ? state.data.daily[state.index-1] : null;
  const stockCurrent = Number(r.stock || 0);
  const stockPrevious = previousRow ? Number(previousRow.stock || 0) : null;
  const stockVariation = stockPrevious === null ? null : stockCurrent - stockPrevious;

  el('kpiStockDia').textContent = `${fmtAuto(stockCurrent)} kg`;
  el('kpiConsumoDia').textContent = `${fmtAuto(r.consumo_real)} kg`;
  el('kpiEntradasDia').textContent = `${fmtAuto(r.entrada_alimento)} kg`;

  el('kpiStockNota').textContent = stockVariation === null
    ? 'Stock reconstruido del primer día; pendiente de validar contra SAP.'
    : `Variación vs. día anterior: ${stockVariation >= 0 ? '+' : ''}${fmtAuto(stockVariation)} kg. Pendiente de validar contra SAP.`;

  el('kpiConsumo').textContent = `${fmt(r.consumo_acum,0)} kg`;
  el('kpiProduccion').textContent = `${fmtAuto(r.produccion_acum)} kg`;
  el('kpiMortalidad').textContent = fmt(r.mortalidad_acum,0);
  const weeklyIca = weekSnapshot?.ica_real ?? null;
  const weeklyIcaStd = weekSnapshot?.ica_estandar ?? null;
  const weeklyStatus = weekSnapshot?.estado_ica || 'Sin semana disponible';

  el('kpiIca').textContent = fmtAuto(weeklyIca);
  el('kpiIcaStd').textContent =
    `Estándar semanal: ${fmtAuto(weeklyIcaStd)}`;
  el('kpiEstado').textContent = weeklyStatus;
  el('kpiEdad').textContent =
    `Semana ${r.semana}, día ${r.dia_semana} · ${weekSnapshot?.dias_observados || 0} día(s) acumulado(s)`;

  el('productionInsight').textContent =
    `Producción del día: ${fmtAuto(r.produccion_real)} kg. ` +
    `La comparación contra estándar se realiza en la gráfica semanal.`;

  el('consumptionInsight').textContent =
    `Consumo del día: ${fmtAuto(r.consumo_real)} kg. ` +
    `La comparación contra estándar se realiza en la gráfica semanal.`;

  const initialBirds = state.data.daily[0].aves ?? 0;
  const currentBirds = r.aves ?? 0;
  const lossPct = initialBirds > 0 ? (initialBirds-currentBirds)/initialBirds*100 : null;
  el('birdsInsight').textContent = lossPct === null
    ? 'No fue posible calcular la variación de aves disponibles.'
    : `Las aves disponibles han variado ${fmt(Math.abs(lossPct),2)}% respecto al inicio del periodo.`;

  el('icaInsight').textContent = weeklyIca === null
    ? `Semana ${r.semana}: ICA no evaluable con ${weekSnapshot?.dias_observados || 0} día(s) acumulado(s).`
    : `Semana ${r.semana}: ICA real ${fmtAuto(weeklyIca)} frente a ${fmtAuto(weeklyIcaStd)} estándar. ${weeklyStatus}.`;

  el('stockInsight').textContent = `Stock al cierre: ${fmtAuto(r.stock)} kg. Entradas: ${fmtAuto(r.entrada_alimento)} kg; traspasos: ${fmtAuto(r.traspasos_internos)} kg; ajustes: ${fmtAuto(Number(r.ajustes_inventario||0)+Number(r.ajustes_511_512||0))} kg; mermas: ${fmtAuto(Math.abs(Number(r.mermas_551_552||0)))} kg.`;

  updateProgressiveCharts();
  renderTable();
  renderNotionTimeline();
  renderValidator();
  renderEventCards();
}

function applyVisibleRangeToCharts(){
  const min = state.visibleStart;
  const max = state.visibleEnd;

  // Las escalas X son categóricas y usan etiquetas de fecha.
  // Por eso min/max deben recibir las etiquetas, no índices numéricos.
  const minLabel = state.data.daily[min]?.fecha_label;
  const maxLabel = state.data.daily[max]?.fecha_label;

  ['production','consumption','stock','birds'].forEach(name=>{
    const chart = state.charts[name];
    if(chart && chart.options.scales?.x){
      if(typeof chart.resetZoom === 'function'){
        chart.resetZoom('none');
      }

      chart.options.scales.x.min = minLabel;
      chart.options.scales.x.max = maxLabel;
      chart.resize();
      chart.update('none');
    }
  });

  if(state.charts.productionConsumption){
    const weekly = buildWeeklyProgress(state.index);
    const minWeek = Number(state.data.daily[min]?.semana);
    const maxWeek = Number(state.data.daily[Math.min(max,state.index)]?.semana);
    const labels = weekly
      .filter(row=>row.semana>=minWeek && row.semana<=maxWeek)
      .map(row=>row.etiqueta);

    if(typeof state.charts.productionConsumption.resetZoom === 'function'){
      state.charts.productionConsumption.resetZoom('none');
    }

    state.charts.productionConsumption.options.scales.x.min =
      labels.length ? labels[0] : undefined;
    state.charts.productionConsumption.options.scales.x.max =
      labels.length ? labels[labels.length-1] : undefined;
    state.charts.productionConsumption.resize();
    state.charts.productionConsumption.update('none');
  }

  if(state.charts.ica){
    const minWeek = Number(state.data.daily[min]?.semana);
    const maxWeek = Number(state.data.daily[max]?.semana);
    const weekly = state.data.weekly;

    let minIdx = weekly.findIndex(row => Number(row.semana) >= minWeek);
    if(minIdx < 0) minIdx = 0;

    let maxIdx = minIdx;
    weekly.forEach((row,index)=>{
      if(Number(row.semana) <= maxWeek){
        maxIdx = index;
      }
    });

    const minWeekLabel = weekly[minIdx]?.etiqueta;
    const maxWeekLabel = weekly[maxIdx]?.etiqueta;

    if(typeof state.charts.ica.resetZoom === 'function'){
      state.charts.ica.resetZoom('none');
    }

    state.charts.ica.options.scales.x.min = minWeekLabel;
    state.charts.ica.options.scales.x.max = maxWeekLabel;
    state.charts.ica.resize();
    state.charts.ica.update('none');
  }

  if(state.charts.warehouseGlobal || state.charts.phaseCasetas?.length){
    updateWarehousePhaseCharts(Math.min(state.index,state.visibleEnd));
  }
}
function nearestIndexFromDate(value){if(!value)return 0;const target=new Date(`${value}T12:00:00`).getTime();let best=0,dist=Infinity;state.data.daily.forEach((r,i)=>{const d=new Date(`${r.fecha}T12:00:00`).getTime(),delta=Math.abs(d-target);if(delta<dist){dist=delta;best=i;}});return best;}
function setCalendarRange(start,end){state.visibleStart=Math.max(0,start);state.visibleEnd=Math.min(state.data.daily.length-1,end);el('dateFrom').value=state.data.daily[state.visibleStart].fecha;el('dateTo').value=state.data.daily[state.visibleEnd].fecha;updateDay(state.visibleEnd);applyVisibleRangeToCharts();}
function applyCalendarSelection(){const mode=document.querySelector('input[name="calendarMode"]:checked')?.value||'range';if(mode==='single'){const idx=nearestIndexFromDate(el('singleDate').value);state.visibleStart=Math.max(0,idx-15);state.visibleEnd=Math.min(state.data.daily.length-1,idx+15);updateDay(idx);}else{const a=nearestIndexFromDate(el('dateFrom').value),b=nearestIndexFromDate(el('dateTo').value);state.visibleStart=Math.min(a,b);state.visibleEnd=Math.max(a,b);updateDay(state.visibleEnd);}applyVisibleRangeToCharts();}
function setupCalendarControls(){document.querySelectorAll('input[name="calendarMode"]').forEach(r=>r.addEventListener('change',()=>{const single=r.value==='single'&&r.checked;el('calendarSingleFields').classList.toggle('hidden',!single);el('calendarRangeFields').classList.toggle('hidden',single);}));el('applyCalendarBtn').addEventListener('click',applyCalendarSelection);el('allPeriodBtn').addEventListener('click',()=>setCalendarRange(0,state.data.daily.length-1));el('last30Btn').addEventListener('click',()=>setCalendarRange(Math.max(0,state.index-29),state.index));el('last90Btn').addEventListener('click',()=>setCalendarRange(Math.max(0,state.index-89),state.index));el('currentPhaseBtn').addEventListener('click',()=>{const phase=String(state.data.daily[state.index].fase||'').trim();const ids=state.data.daily.map((r,i)=>String(r.fase||'').trim()===phase?i:null).filter(v=>v!==null);if(ids.length)setCalendarRange(Math.min(...ids),Math.max(...ids));});el('toggleTimelineBtn').addEventListener('click',()=>el('notionTimeline').classList.toggle('timeline-compact'));}

function renderPeriod(periodId){
  state.periodId = periodId;
  state.mode = periodId === '__GLOBAL__' ? 'global' : 'cycle';
  state.data = state.mode === 'global'
    ? PAYLOAD.global
    : PAYLOAD.periods[periodId];

  // Abrir la vista en la última fecha disponible.
  state.index = Math.max(0,state.data.daily.length-1);
  state.visibleStart = 0;
  state.visibleEnd = Math.max(0,state.data.daily.length-1);
  destroyCharts();

  const m = state.data.meta;
  el('metaCentro').textContent = m.centro || '-';
  el('metaCaseta').textContent = m.caseta || '-';
  el('metaEstado').textContent = m.estado || '-';
  el('metaLote').textContent = m.lote || '-';
  el('metaOrden').textContent = m.orden || '-';
  el('metaInicio').textContent = m.fecha_inicio || '-';
  el('standardSource').textContent = state.mode === 'global'
    ? `Vista global · Fuente almacén: ${m.warehouse_source || state.data.warehouse_source || '-'}`
    : `Estándar: ${m.fuente_estandar || '-'}`;

  const globalMode = state.mode === 'global';
  el('icaCard')?.classList.toggle('hidden', globalMode);
  el('scatterCard')?.classList.toggle('hidden', globalMode);
  el('currentPhaseBtn').disabled = globalMode;
  el('currentPhaseBtn').title = globalMode
    ? 'Disponible al seleccionar un ciclo'
    : 'Mostrar la fase actual';

  el('dateSlider').max = Math.max(0,state.data.daily.length-1);
  const firstDate=state.data.daily[0].fecha,lastDate=state.data.daily[state.data.daily.length-1].fecha;
  ['dateFrom','dateTo','singleDate'].forEach(id=>{el(id).min=firstDate;el(id).max=lastDate;});
  el('dateFrom').value=firstDate;
  el('dateTo').value=lastDate;
  el('singleDate').value=lastDate;
  state.events = buildTimelineEvents(state.data.daily);
  renderNotionTimeline();
  createProductionChart();
  createConsumptionChart();
  createStockChart();
  createProductionConsumptionChart();
  createWarehousePhaseCharts();
  if(state.mode !== 'global'){
    createScatterChart();
    createIcaChart();
  }
  createBirdsChart();
  createMovementChart();
  renderTable();
  renderValidator();
  updateDay(state.index);
  applyVisibleRangeToCharts();
}

function updatePlayButton(){
  const button = el('playPause');
  if(!button) return;
  button.textContent = state.playing ? '⏸ Pausar' : '▶ Reproducir';
  button.classList.toggle('active',state.playing);
}

function stopPlayback(){
  state.playing = false;
  if(state.timer){ clearInterval(state.timer); state.timer = null; }
  updatePlayButton();
}

function startPlayback(){
  if(!state.data || !state.data.daily.length) return;
  if(state.index >= state.data.daily.length-1) updateDay(0);
  state.playing = true;
  updatePlayButton();
  state.timer = setInterval(()=>{
    if(state.index >= state.data.daily.length-1){ stopPlayback(); return; }
    updateDay(state.index+1);
  },state.speedMs);
}

function togglePlayback(){
  if(state.playing) stopPlayback(); else startPlayback();
}

function setup(){
  // La reproducción es independiente del desplazamiento de la página.
  // El usuario puede bajar, subir o usar gestos táctiles sin detener el avance.
  const select = el('periodSelect');

  const globalOption = document.createElement('option');
  globalOption.value = '__GLOBAL__';
  globalOption.textContent = 'Vista global del centro · almacén, casetas y ciclos';
  select.appendChild(globalOption);

  PAYLOAD.period_ids.forEach(id=>{
    const m = PAYLOAD.periods[id].meta;
    const option = document.createElement('option');
    option.value = id;
    option.textContent = `${id} | Caseta ${m.caseta || '-'} | Lote ${m.lote || '-'}`;
    select.appendChild(option);
  });

  select.addEventListener('change',e=>{ stopPlayback(); renderPeriod(e.target.value); });
  el('dateSlider').addEventListener('input',e=>updateDay(Number(e.target.value)));
  el('prevDay').addEventListener('click',()=>updateDay(state.index-1));
  el('nextDay').addEventListener('click',()=>updateDay(state.index+1));
  el('playPause').addEventListener('click',togglePlayback);
  el('generatedAt').textContent = PAYLOAD.generated_at;
  setupValidatorTabs();
  setupCalendarControls();

  if(PAYLOAD.global && PAYLOAD.global.daily?.length){
    select.value = '__GLOBAL__';
    renderPeriod('__GLOBAL__');
  }else if(PAYLOAD.period_ids.length){
    select.value = PAYLOAD.period_ids[0];
    renderPeriod(PAYLOAD.period_ids[0]);
  }
}
setup();
</script>
</body>
</html>'''

html_content = html_template.replace(
    "__PAYLOAD_JSON__",
    json.dumps(payload, ensure_ascii=False, allow_nan=False),
)

HTML_OUTPUT_PATH.write_text(html_content, encoding="utf-8")

display(HTML(
    f"<div style='font-family:Arial;padding:8px 0;color:#1A428A;font-weight:700'>"
    f"Dashboard generado: {HTML_OUTPUT_PATH.name}</div>"
))
display(IFrame(src=str(HTML_OUTPUT_PATH), width="100%", height=ALTURA_IFRAME))
