# ============================================================
# CELDA 6 — Línea diaria por ciclo: aves, consumo por orden,
# fases de alimento, producción, contexto SAP, edad e ICA
# ============================================================

import re
import numpy as np
import pandas as pd

# ------------------------------------------------------------
# 0. Validaciones y compatibilidad con celdas anteriores
# ------------------------------------------------------------

if "cycles_scope" not in globals():
    raise ValueError("No existe cycles_scope. Ejecuta primero la Celda 5.")

if "kardex" not in globals():
    raise ValueError("No existe kardex. Ejecuta primero las celdas de carga.")

if "config" not in globals():
    raise ValueError("No existe config. Ejecuta primero la celda de configuración.")

if "show_md" not in globals():
    def show_md(text):
        from IPython.display import Markdown, display
        display(Markdown(text))

if "save_table" not in globals():
    def save_table(df, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(path, index=False, encoding="utf-8-sig")
        return path

def existing_columns_local(df, columns):
    return [col for col in columns if col in df.columns]

if "existing_columns" not in globals():
    existing_columns = existing_columns_local

BIRD_MATERIAL = globals().get("BIRD_MATERIAL", "20019")

# Política corporativa de edad de entrada.
# La fecha de entrada biológica de aves corresponde a semana 16, día 0.
EDAD_INICIAL_SEMANA_POLITICA = 16
EDAD_INICIAL_DIA_POLITICA = 0

# ------------------------------------------------------------
# 0.1 Compatibilidad de fechas de ciclos
# ------------------------------------------------------------

if cycles_scope.empty:
    show_md(
        """
## Línea diaria por ciclo

No hay ciclos dentro del scope actual. Revisa los filtros de la configuración.
"""
    )

    linea_diaria_ciclos = pd.DataFrame()
    hitos_productivos_ciclos = pd.DataFrame()
    resumen_linea_diaria_ciclos = pd.DataFrame()

else:
    cycles_scope = cycles_scope.copy()

    for col in [
        "fecha_inicio_ciclo",
        "fecha_fin_operativa",
        "fecha_fin_ciclo",
        "fecha_fin_tecnica",
        "fecha_corte_analisis",
        "fecha_fin_analisis",
    ]:
        if col in cycles_scope.columns:
            cycles_scope[col] = pd.to_datetime(cycles_scope[col], errors="coerce")

    if "fecha_corte_analisis" not in cycles_scope.columns:
        if "fecha_fin_analisis" in cycles_scope.columns:
            cycles_scope["fecha_corte_analisis"] = cycles_scope["fecha_fin_analisis"]
        elif "fecha_fin_operativa" in cycles_scope.columns:
            cycles_scope["fecha_corte_analisis"] = cycles_scope["fecha_fin_operativa"]
        else:
            cycles_scope["fecha_corte_analisis"] = pd.NaT

        if "fecha_fin_tecnica" in cycles_scope.columns:
            cycles_scope["fecha_corte_analisis"] = cycles_scope["fecha_corte_analisis"].fillna(
                cycles_scope["fecha_fin_tecnica"]
            )

        cycles_scope["fecha_corte_analisis"] = cycles_scope["fecha_corte_analisis"].fillna(
            kardex["fecha"].max()
        )

    if "fecha_fin_ciclo" not in cycles_scope.columns:
        if "fecha_fin_operativa" in cycles_scope.columns:
            cycles_scope["fecha_fin_ciclo"] = cycles_scope["fecha_fin_operativa"]
        else:
            cycles_scope["fecha_fin_ciclo"] = pd.NaT

    if "estado_ciclo_negocio" not in cycles_scope.columns:
        cycles_scope["estado_ciclo_negocio"] = np.where(
            cycles_scope["fecha_fin_ciclo"].notna(),
            "cerrado",
            "abierto_en_proceso",
        )

    if "motivo_corte_analisis" not in cycles_scope.columns:
        cycles_scope["motivo_corte_analisis"] = np.where(
            cycles_scope["fecha_fin_ciclo"].notna(),
            "corte_por_fin_real_ciclo",
            "corte_por_ultima_fecha_disponible_ciclo_abierto",
        )

    show_md(
        f"""
## Construcción de línea diaria

Se construirán líneas diarias para **{len(cycles_scope):,} ciclos**.

Regla de esta celda:

- Aves: se reconstruyen por `centro + caseta + lote de aves + material 20019`.
- Inicio biológico: primer `101 WE` del material 20019 por caseta/lote.
- Edad inicial por política: **semana 16, día 0**.
- Consumo de alimento de la parvada: se reconstruye por `orden_operativa + materiales 10007-10011`.
- Fases de alimento: se detectan por material consumido.
- Producción: se reconstruye por `orden_operativa + materiales de huevo/subproducto`.
- ICA: se calcula solo con consumo de la orden y producción de la orden.
- `WI`, `WL`, `641`, `643`, `301`, `511`, `551` quedan como contexto del ciclo.
- El stock real/reconstruido del almacén 1100 se agregará después en la Celda 6A.
"""
    )


# ------------------------------------------------------------
# 1. Funciones auxiliares
# ------------------------------------------------------------

def get_global_dict(name, default):
    return globals().get(name, default)


def normalize_material_list_or_dict(value):
    if isinstance(value, dict):
        return [str(x) for x in value.keys()]
    if isinstance(value, (list, tuple, set)):
        return [str(x) for x in value]
    return []


def safe_column(df, column, default_value=pd.NA):
    if column in df.columns:
        return df[column]
    return pd.Series(default_value, index=df.index)


def safe_numeric(series):
    return pd.to_numeric(series, errors="coerce")


def text_upper(series):
    return series.astype("string").str.upper().fillna("")


def compact_unique(series, max_values=12):
    values = (
        series.dropna()
        .astype(str)
        .replace("<NA>", pd.NA)
        .dropna()
        .drop_duplicates()
        .head(max_values)
        .tolist()
    )
    return ", ".join(values)


def safe_min_date(df, mask, column="fecha"):
    if df.empty or column not in df.columns:
        return pd.NaT

    values = df.loc[mask, column].dropna()

    if values.empty:
        return pd.NaT

    return values.min()


def safe_max_date(df, mask, column="fecha"):
    if df.empty or column not in df.columns:
        return pd.NaT

    values = df.loc[mask, column].dropna()

    if values.empty:
        return pd.NaT

    return values.max()


def normalize_label(value):
    value = str(value).lower().strip()
    value = value.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    value = value.replace("ñ", "n")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value


def choose_quantity_kg(df, fallback_to_abs=True):
    if df.empty:
        return pd.Series(dtype="float64")

    qty_ump = safe_numeric(safe_column(df, "cantidad_ump", np.nan))
    qty_ume = safe_numeric(safe_column(df, "cantidad_um_entrada", np.nan))
    qty_abs = safe_numeric(safe_column(df, "cantidad_abs", np.nan))

    unit_ump = text_upper(safe_column(df, "unidad_medida_paralela", ""))
    unit_ume = text_upper(safe_column(df, "unidad_medida_entrada", ""))

    qty = pd.Series(np.nan, index=df.index, dtype="float64")

    mask_ump_kg = unit_ump.str.contains("KG", na=False) & qty_ump.notna()
    qty.loc[mask_ump_kg] = qty_ump.loc[mask_ump_kg].abs()

    mask_ume_kg = qty.isna() & unit_ume.str.contains("KG", na=False) & qty_ume.notna()
    qty.loc[mask_ume_kg] = qty_ume.loc[mask_ume_kg].abs()

    if fallback_to_abs:
        mask_fallback_abs = qty.isna() & qty_abs.notna()
        qty.loc[mask_fallback_abs] = qty_abs.loc[mask_fallback_abs].abs()

    return qty.fillna(0.0)


def ensure_numeric_columns(df, columns, default_value=0.0):
    for col in columns:
        if col not in df.columns:
            df[col] = default_value
        else:
            df[col] = safe_numeric(df[col]).fillna(default_value)
    return df


def ensure_text_columns(df, columns, default_value=""):
    for col in columns:
        if col not in df.columns:
            df[col] = default_value
        else:
            df[col] = df[col].fillna(default_value)
    return df


def make_daily_base(cycle_row):
    start_date = pd.to_datetime(cycle_row["fecha_inicio_ciclo"])
    cut_date = pd.to_datetime(cycle_row["fecha_corte_analisis"])

    if pd.isna(start_date) or pd.isna(cut_date):
        return pd.DataFrame()

    if cut_date < start_date:
        return pd.DataFrame()

    dates = pd.date_range(start_date, cut_date, freq="D")

    base = pd.DataFrame({"fecha": dates})

    base["cycle_id"] = cycle_row["cycle_id"]
    base["centro"] = cycle_row["centro"]
    base["almacen_aves"] = cycle_row["almacen"]
    base["lote_aves"] = cycle_row["lote"]
    base["orden_operativa"] = cycle_row.get("orden_operativa", pd.NA)

    base["fecha_inicio_ciclo"] = cycle_row["fecha_inicio_ciclo"]
    base["fecha_fin_ciclo"] = cycle_row.get("fecha_fin_ciclo", pd.NaT)
    base["fecha_corte_analisis"] = cycle_row.get("fecha_corte_analisis", pd.NaT)
    base["motivo_corte_analisis"] = cycle_row.get("motivo_corte_analisis", "")
    base["estado_ciclo_negocio"] = cycle_row.get("estado_ciclo_negocio", "")
    base["tipo_fin_ciclo"] = cycle_row.get("tipo_fin_ciclo", "")
    base["estado_cierre_balance"] = cycle_row.get("estado_cierre_balance", "")
    base["estado_validacion_cierre"] = cycle_row.get("estado_validacion_cierre", "")

    base["entrada_neta_aves_ciclo"] = cycle_row.get("entrada_neta_aves", np.nan)
    base["fecha_primera_orden"] = cycle_row.get("fecha_primera_orden", pd.NaT)

    base["dias_desde_inicio"] = (base["fecha"] - start_date).dt.days

    # Edad biológica por política:
    # fecha de entrada de aves = semana 16, día 0.
    base["edad_dias_total"] = (
        EDAD_INICIAL_SEMANA_POLITICA * 7
        + EDAD_INICIAL_DIA_POLITICA
        + base["dias_desde_inicio"]
    )

    base["edad_semana"] = (base["edad_dias_total"] // 7).astype(int)
    base["edad_dia_semana"] = (base["edad_dias_total"] % 7).astype(int)

    return base


# ------------------------------------------------------------
# 2. Diccionarios de materiales
# ------------------------------------------------------------

feed_materials_value = get_global_dict(
    "FEED_MATERIALS",
    {
        "10007": "Fase 1",
        "10008": "Fase 2",
        "10009": "Fase 3",
        "10010": "Fase 4",
        "10011": "Fase 5",
    },
)

egg_materials_value = get_global_dict(
    "EGG_MATERIALS",
    {
        "50012": "Huevo normal",
        "50008": "Huevo jumbo",
        "50009": "Huevo picado",
        "50010": "Huevo roto",
        "50011": "Huevo sucio",
        "50129": "Huevo clasificado",
        "50150": "Huevo libre de jaula",
    },
)

FEED_MATERIAL_LIST = normalize_material_list_or_dict(feed_materials_value)
EGG_MATERIAL_LIST = normalize_material_list_or_dict(egg_materials_value)

if isinstance(feed_materials_value, dict):
    FEED_PHASE_MAP = {str(k): str(v) for k, v in feed_materials_value.items()}
else:
    FEED_PHASE_MAP = {
        "10007": "Fase 1",
        "10008": "Fase 2",
        "10009": "Fase 3",
        "10010": "Fase 4",
        "10011": "Fase 5",
    }

if isinstance(egg_materials_value, dict):
    EGG_TYPE_MAP = {str(k): str(v) for k, v in egg_materials_value.items()}
else:
    EGG_TYPE_MAP = {
        "50012": "Huevo normal",
        "50008": "Huevo jumbo",
        "50009": "Huevo picado",
        "50010": "Huevo roto",
        "50011": "Huevo sucio",
        "50129": "Huevo clasificado",
        "50150": "Huevo libre de jaula",
    }

FEED_PHASE_COLUMNS = {
    material: f"consumo_kg_{normalize_label(phase)}"
    for material, phase in FEED_PHASE_MAP.items()
}


# ------------------------------------------------------------
# 3. Agregación diaria de aves
# ------------------------------------------------------------

def aggregate_birds_daily(cycle_row, df):
    start_date = pd.to_datetime(cycle_row["fecha_inicio_ciclo"])
    cut_date = pd.to_datetime(cycle_row["fecha_corte_analisis"])

    temp = df.loc[
        df["centro"].eq(cycle_row["centro"])
        & df["almacen"].eq(cycle_row["almacen"])
        & df["lote"].eq(cycle_row["lote"])
        & df["material"].eq(BIRD_MATERIAL)
        & df["fecha"].ge(start_date)
        & df["fecha"].le(cut_date)
    ].copy()

    if temp.empty:
        return pd.DataFrame({"fecha": pd.date_range(start_date, cut_date, freq="D")})

    mov = text_upper(temp["clase_movimiento"])
    evt = text_upper(temp["clase_transaccion_evento"])
    qty = safe_numeric(temp["cantidad_abs"]).fillna(0).abs()

    temp["entrada_aves_dia"] = np.where(mov.eq("101") & evt.eq("WE"), qty, 0.0)
    temp["anulacion_entrada_aves_dia"] = np.where(mov.eq("102") & evt.eq("WE"), qty, 0.0)

    temp["mortalidad_aves_dia"] = np.where(mov.eq("261") & evt.eq("WR"), qty, 0.0)
    temp["reversa_mortalidad_aves_dia"] = np.where(mov.eq("262") & evt.eq("WR"), qty, 0.0)

    temp["salida_aves_dia"] = np.where(mov.eq("261") & evt.eq("WA"), qty, 0.0)

    temp["merma_551_dia"] = np.where(mov.eq("551"), qty, 0.0)
    temp["reversa_merma_552_dia"] = np.where(mov.eq("552"), qty, 0.0)

    temp["ajuste_511_dia_contexto"] = np.where(mov.eq("511"), qty, 0.0)
    temp["reversa_ajuste_512_dia_contexto"] = np.where(mov.eq("512"), qty, 0.0)

    daily = (
        temp.groupby("fecha", dropna=False)
        .agg(
            entrada_aves_dia=("entrada_aves_dia", "sum"),
            anulacion_entrada_aves_dia=("anulacion_entrada_aves_dia", "sum"),
            mortalidad_aves_dia=("mortalidad_aves_dia", "sum"),
            reversa_mortalidad_aves_dia=("reversa_mortalidad_aves_dia", "sum"),
            salida_aves_dia=("salida_aves_dia", "sum"),
            merma_551_dia=("merma_551_dia", "sum"),
            reversa_merma_552_dia=("reversa_merma_552_dia", "sum"),
            ajuste_511_dia_contexto=("ajuste_511_dia_contexto", "sum"),
            reversa_ajuste_512_dia_contexto=("reversa_ajuste_512_dia_contexto", "sum"),
            movimientos_aves_dia=("material", "size"),
            documentos_aves_dia=("documento_material", compact_unique),
            movimientos_aves_resumen=("clase_movimiento", compact_unique),
            eventos_aves_resumen=("clase_transaccion_evento", compact_unique),
        )
        .reset_index()
    )

    daily["entrada_neta_aves_dia"] = (
        daily["entrada_aves_dia"] - daily["anulacion_entrada_aves_dia"]
    )

    daily["mortalidad_neta_aves_dia"] = (
        daily["mortalidad_aves_dia"] - daily["reversa_mortalidad_aves_dia"]
    )

    daily["merma_neta_551_552_dia"] = (
        daily["merma_551_dia"] - daily["reversa_merma_552_dia"]
    )

    daily["ajuste_511_neto_contexto_dia"] = (
        daily["ajuste_511_dia_contexto"] - daily["reversa_ajuste_512_dia_contexto"]
    )

    return daily


# ------------------------------------------------------------
# 4. Agregación diaria de alimento consumido por orden
# ------------------------------------------------------------

def aggregate_feed_daily(cycle_row, df):
    start_date = pd.to_datetime(cycle_row["fecha_inicio_ciclo"])
    cut_date = pd.to_datetime(cycle_row["fecha_corte_analisis"])
    order_id = cycle_row.get("orden_operativa", pd.NA)

    if pd.isna(order_id):
        return pd.DataFrame({"fecha": pd.date_range(start_date, cut_date, freq="D")})

    temp = df.loc[
        df["centro"].eq(cycle_row["centro"])
        & df["orden"].eq(str(order_id))
        & df["material"].isin(FEED_MATERIAL_LIST)
        & df["fecha"].ge(start_date)
        & df["fecha"].le(cut_date)
    ].copy()

    if temp.empty:
        return pd.DataFrame({"fecha": pd.date_range(start_date, cut_date, freq="D")})

    mov = text_upper(temp["clase_movimiento"])
    evt = text_upper(temp["clase_transaccion_evento"])

    temp["cantidad_kg_base"] = choose_quantity_kg(temp, fallback_to_abs=True)

    mask_consumo = mov.eq("261") & evt.eq("WA")
    mask_reversa_consumo = mov.eq("262") & evt.eq("WA")

    temp["consumo_alimento_kg_dia"] = np.where(mask_consumo, temp["cantidad_kg_base"], 0.0)
    temp["reversa_consumo_alimento_kg_dia"] = np.where(mask_reversa_consumo, temp["cantidad_kg_base"], 0.0)

    temp["consumo_neto_alimento_kg_dia"] = (
        temp["consumo_alimento_kg_dia"] - temp["reversa_consumo_alimento_kg_dia"]
    )

    temp["consumo_orden_alimento_kg_dia"] = temp["consumo_neto_alimento_kg_dia"]

    temp["fase_alimento"] = temp["material"].map(FEED_PHASE_MAP).fillna(temp["material"])
    temp["fase_col"] = temp["fase_alimento"].map(lambda x: f"consumo_kg_{normalize_label(x)}")

    temp["movimiento_alimento_para_ica"] = np.where(
        mask_consumo | mask_reversa_consumo,
        "si_ica",
        "no_ica_contexto_orden",
    )

    daily = (
        temp.groupby("fecha", dropna=False)
        .agg(
            consumo_alimento_kg_dia=("consumo_alimento_kg_dia", "sum"),
            reversa_consumo_alimento_kg_dia=("reversa_consumo_alimento_kg_dia", "sum"),
            consumo_neto_alimento_kg_dia=("consumo_neto_alimento_kg_dia", "sum"),
            consumo_orden_alimento_kg_dia=("consumo_orden_alimento_kg_dia", "sum"),
            movimientos_alimento_dia=("material", "size"),
            materiales_alimento_dia=("material", compact_unique),
            fases_alimento_dia=("fase_alimento", compact_unique),
            almacenes_alimento_dia=("almacen", compact_unique),
            lotes_alimento_dia=("lote", compact_unique),
            documentos_alimento_dia=("documento_material", compact_unique),
            movimientos_alimento_resumen=("clase_movimiento", compact_unique),
            eventos_alimento_resumen=("clase_transaccion_evento", compact_unique),
        )
        .reset_index()
    )

    phase_daily = (
        temp.groupby(["fecha", "fase_col"], dropna=False)["consumo_neto_alimento_kg_dia"]
        .sum()
        .reset_index()
    )

    if not phase_daily.empty:
        phase_pivot = phase_daily.pivot_table(
            index="fecha",
            columns="fase_col",
            values="consumo_neto_alimento_kg_dia",
            aggfunc="sum",
            fill_value=0.0,
        ).reset_index()

        daily = daily.merge(phase_pivot, on="fecha", how="left")

    for material, col in FEED_PHASE_COLUMNS.items():
        if col not in daily.columns:
            daily[col] = 0.0

    return daily


# ------------------------------------------------------------
# 5. Agregación diaria de producción por orden
# ------------------------------------------------------------

def aggregate_production_daily(cycle_row, df):
    start_date = pd.to_datetime(cycle_row["fecha_inicio_ciclo"])
    cut_date = pd.to_datetime(cycle_row["fecha_corte_analisis"])
    order_id = cycle_row.get("orden_operativa", pd.NA)

    if pd.isna(order_id):
        return pd.DataFrame({"fecha": pd.date_range(start_date, cut_date, freq="D")})

    temp = df.loc[
        df["centro"].eq(cycle_row["centro"])
        & df["orden"].eq(str(order_id))
        & df["material"].isin(EGG_MATERIAL_LIST)
        & df["fecha"].ge(start_date)
        & df["fecha"].le(cut_date)
    ].copy()

    if temp.empty:
        return pd.DataFrame({"fecha": pd.date_range(start_date, cut_date, freq="D")})

    mov = text_upper(temp["clase_movimiento"])
    evt = text_upper(temp["clase_transaccion_evento"])

    temp["cantidad_kg_base"] = choose_quantity_kg(temp, fallback_to_abs=True)

    mask_produccion_huevo_normal = mov.eq("101") & evt.eq("WF")
    mask_reversa_huevo_normal = mov.eq("102") & evt.eq("WF")

    mask_produccion_subproducto = mov.eq("531") & evt.eq("WA")
    mask_reversa_subproducto = mov.eq("532") & evt.eq("WA")

    mask_produccion = mask_produccion_huevo_normal | mask_produccion_subproducto
    mask_reversa = mask_reversa_huevo_normal | mask_reversa_subproducto

    temp["produccion_huevo_kg_dia"] = np.where(mask_produccion, temp["cantidad_kg_base"], 0.0)
    temp["reversa_produccion_huevo_kg_dia"] = np.where(mask_reversa, temp["cantidad_kg_base"], 0.0)

    temp["produccion_neta_huevo_kg_dia"] = (
        temp["produccion_huevo_kg_dia"] - temp["reversa_produccion_huevo_kg_dia"]
    )

    temp["tipo_huevo"] = temp["material"].map(EGG_TYPE_MAP).fillna(temp["material"])

    daily = (
        temp.groupby("fecha", dropna=False)
        .agg(
            produccion_huevo_kg_dia=("produccion_huevo_kg_dia", "sum"),
            reversa_produccion_huevo_kg_dia=("reversa_produccion_huevo_kg_dia", "sum"),
            produccion_neta_huevo_kg_dia=("produccion_neta_huevo_kg_dia", "sum"),
            movimientos_produccion_dia=("material", "size"),
            materiales_produccion_dia=("material", compact_unique),
            tipos_huevo_dia=("tipo_huevo", compact_unique),
            almacenes_produccion_dia=("almacen", compact_unique),
            lotes_produccion_dia=("lote", compact_unique),
            documentos_produccion_dia=("documento_material", compact_unique),
            movimientos_produccion_resumen=("clase_movimiento", compact_unique),
            eventos_produccion_resumen=("clase_transaccion_evento", compact_unique),
        )
        .reset_index()
    )

    egg_type_daily = (
        temp.groupby(["fecha", "tipo_huevo"], dropna=False)["produccion_neta_huevo_kg_dia"]
        .sum()
        .reset_index()
    )

    if not egg_type_daily.empty:
        egg_type_daily["tipo_huevo_col"] = egg_type_daily["tipo_huevo"].map(
            lambda x: f"produccion_kg_{normalize_label(x)}"
        )

        egg_pivot = egg_type_daily.pivot_table(
            index="fecha",
            columns="tipo_huevo_col",
            values="produccion_neta_huevo_kg_dia",
            aggfunc="sum",
            fill_value=0.0,
        ).reset_index()

        daily = daily.merge(egg_pivot, on="fecha", how="left")

    return daily


# ------------------------------------------------------------
# 6. Agregación diaria de contexto SAP del ciclo
# ------------------------------------------------------------

def aggregate_sap_context_daily(cycle_row, df):
    start_date = pd.to_datetime(cycle_row["fecha_inicio_ciclo"])
    cut_date = pd.to_datetime(cycle_row["fecha_corte_analisis"])
    order_id = cycle_row.get("orden_operativa", pd.NA)

    mask_date_center = (
        df["centro"].eq(cycle_row["centro"])
        & df["fecha"].ge(start_date)
        & df["fecha"].le(cut_date)
    )

    if pd.notna(order_id):
        mask_same_order = df["orden"].eq(str(order_id))
    else:
        mask_same_order = pd.Series(False, index=df.index)

    mask_same_bird_lot = (
        df["almacen"].eq(cycle_row["almacen"])
        & df["lote"].eq(cycle_row["lote"])
        & df["material"].eq(BIRD_MATERIAL)
    )

    temp = df.loc[
        mask_date_center
        & (mask_same_order | mask_same_bird_lot)
    ].copy()

    if temp.empty:
        return pd.DataFrame({"fecha": pd.date_range(start_date, cut_date, freq="D")})

    mov = text_upper(temp["clase_movimiento"])
    evt = text_upper(temp["clase_transaccion_evento"])

    temp["cantidad_contexto_abs"] = safe_numeric(safe_column(temp, "cantidad_abs", 0)).fillna(0).abs()
    temp["cantidad_contexto_kg"] = choose_quantity_kg(temp, fallback_to_abs=False)

    temp["texto_movimiento_contexto"] = safe_column(
        temp,
        "texto_clase_movimiento",
        "",
    ).astype("string").fillna("")

    mask_we = evt.eq("WE")
    mask_wa = evt.eq("WA")
    mask_wr = evt.eq("WR")
    mask_wf = evt.eq("WF")
    mask_wl = evt.eq("WL")
    mask_wi = evt.eq("WI")

    mask_301 = mov.eq("301")
    mask_311 = mov.eq("311")
    mask_641 = mov.eq("641")
    mask_643 = mov.eq("643")
    mask_511 = mov.eq("511")
    mask_512 = mov.eq("512")
    mask_551 = mov.eq("551")
    mask_552 = mov.eq("552")
    mask_701 = mov.eq("701")
    mask_702 = mov.eq("702")

    mask_contexto = (
        mask_we
        | mask_wa
        | mask_wr
        | mask_wf
        | mask_wl
        | mask_wi
        | mask_301
        | mask_311
        | mask_641
        | mask_643
        | mask_511
        | mask_512
        | mask_551
        | mask_552
        | mask_701
        | mask_702
    )

    temp = temp.loc[mask_contexto].copy()

    if temp.empty:
        return pd.DataFrame({"fecha": pd.date_range(start_date, cut_date, freq="D")})

    mov = text_upper(temp["clase_movimiento"])
    evt = text_upper(temp["clase_transaccion_evento"])

    temp["contexto_we_abs_dia"] = np.where(evt.eq("WE"), temp["cantidad_contexto_abs"], 0.0)
    temp["contexto_wa_abs_dia"] = np.where(evt.eq("WA"), temp["cantidad_contexto_abs"], 0.0)
    temp["contexto_wr_abs_dia"] = np.where(evt.eq("WR"), temp["cantidad_contexto_abs"], 0.0)
    temp["contexto_wf_abs_dia"] = np.where(evt.eq("WF"), temp["cantidad_contexto_abs"], 0.0)
    temp["contexto_wl_abs_dia"] = np.where(evt.eq("WL"), temp["cantidad_contexto_abs"], 0.0)
    temp["contexto_wi_abs_dia"] = np.where(evt.eq("WI"), temp["cantidad_contexto_abs"], 0.0)

    temp["contexto_we_kg_dia"] = np.where(evt.eq("WE"), temp["cantidad_contexto_kg"], 0.0)
    temp["contexto_wa_kg_dia"] = np.where(evt.eq("WA"), temp["cantidad_contexto_kg"], 0.0)
    temp["contexto_wf_kg_dia"] = np.where(evt.eq("WF"), temp["cantidad_contexto_kg"], 0.0)
    temp["contexto_wl_kg_dia"] = np.where(evt.eq("WL"), temp["cantidad_contexto_kg"], 0.0)
    temp["contexto_wi_kg_dia"] = np.where(evt.eq("WI"), temp["cantidad_contexto_kg"], 0.0)

    temp["contexto_301_kg_dia"] = np.where(mov.eq("301"), temp["cantidad_contexto_kg"], 0.0)
    temp["contexto_311_kg_dia"] = np.where(mov.eq("311"), temp["cantidad_contexto_kg"], 0.0)
    temp["contexto_641_wl_kg_dia"] = np.where(mov.eq("641") & evt.eq("WL"), temp["cantidad_contexto_kg"], 0.0)
    temp["contexto_643_wl_kg_dia"] = np.where(mov.eq("643") & evt.eq("WL"), temp["cantidad_contexto_kg"], 0.0)

    temp["contexto_511_abs_dia"] = np.where(mov.eq("511"), temp["cantidad_contexto_abs"], 0.0)
    temp["contexto_512_abs_dia"] = np.where(mov.eq("512"), temp["cantidad_contexto_abs"], 0.0)
    temp["contexto_551_abs_dia"] = np.where(mov.eq("551"), temp["cantidad_contexto_abs"], 0.0)
    temp["contexto_552_abs_dia"] = np.where(mov.eq("552"), temp["cantidad_contexto_abs"], 0.0)
    temp["contexto_701_abs_dia"] = np.where(mov.eq("701"), temp["cantidad_contexto_abs"], 0.0)
    temp["contexto_702_abs_dia"] = np.where(mov.eq("702"), temp["cantidad_contexto_abs"], 0.0)

    temp["es_we"] = evt.eq("WE").astype(int)
    temp["es_wa"] = evt.eq("WA").astype(int)
    temp["es_wr"] = evt.eq("WR").astype(int)
    temp["es_wf"] = evt.eq("WF").astype(int)
    temp["es_wl"] = evt.eq("WL").astype(int)
    temp["es_wi"] = evt.eq("WI").astype(int)

    temp["es_301"] = mov.eq("301").astype(int)
    temp["es_311"] = mov.eq("311").astype(int)
    temp["es_641"] = mov.eq("641").astype(int)
    temp["es_643"] = mov.eq("643").astype(int)
    temp["es_511"] = mov.eq("511").astype(int)
    temp["es_551"] = mov.eq("551").astype(int)
    temp["es_701_702"] = mov.isin(["701", "702"]).astype(int)

    daily = (
        temp.groupby("fecha", dropna=False)
        .agg(
            movimientos_contexto_sap_dia=("material", "size"),
            movimientos_we_contexto_dia=("es_we", "sum"),
            movimientos_wa_contexto_dia=("es_wa", "sum"),
            movimientos_wr_contexto_dia=("es_wr", "sum"),
            movimientos_wf_contexto_dia=("es_wf", "sum"),
            movimientos_wl_contexto_dia=("es_wl", "sum"),
            movimientos_wi_contexto_dia=("es_wi", "sum"),
            movimientos_301_contexto_dia=("es_301", "sum"),
            movimientos_311_contexto_dia=("es_311", "sum"),
            movimientos_641_contexto_dia=("es_641", "sum"),
            movimientos_643_contexto_dia=("es_643", "sum"),
            movimientos_511_contexto_dia=("es_511", "sum"),
            movimientos_551_contexto_dia=("es_551", "sum"),
            movimientos_701_702_contexto_dia=("es_701_702", "sum"),

            contexto_we_abs_dia=("contexto_we_abs_dia", "sum"),
            contexto_wa_abs_dia=("contexto_wa_abs_dia", "sum"),
            contexto_wr_abs_dia=("contexto_wr_abs_dia", "sum"),
            contexto_wf_abs_dia=("contexto_wf_abs_dia", "sum"),
            contexto_wl_abs_dia=("contexto_wl_abs_dia", "sum"),
            contexto_wi_abs_dia=("contexto_wi_abs_dia", "sum"),

            contexto_we_kg_dia=("contexto_we_kg_dia", "sum"),
            contexto_wa_kg_dia=("contexto_wa_kg_dia", "sum"),
            contexto_wf_kg_dia=("contexto_wf_kg_dia", "sum"),
            contexto_wl_kg_dia=("contexto_wl_kg_dia", "sum"),
            contexto_wi_kg_dia=("contexto_wi_kg_dia", "sum"),
            contexto_301_kg_dia=("contexto_301_kg_dia", "sum"),
            contexto_311_kg_dia=("contexto_311_kg_dia", "sum"),
            contexto_641_wl_kg_dia=("contexto_641_wl_kg_dia", "sum"),
            contexto_643_wl_kg_dia=("contexto_643_wl_kg_dia", "sum"),

            contexto_511_abs_dia=("contexto_511_abs_dia", "sum"),
            contexto_512_abs_dia=("contexto_512_abs_dia", "sum"),
            contexto_551_abs_dia=("contexto_551_abs_dia", "sum"),
            contexto_552_abs_dia=("contexto_552_abs_dia", "sum"),
            contexto_701_abs_dia=("contexto_701_abs_dia", "sum"),
            contexto_702_abs_dia=("contexto_702_abs_dia", "sum"),

            materiales_contexto_sap_dia=("material", compact_unique),
            almacenes_contexto_sap_dia=("almacen", compact_unique),
            lotes_contexto_sap_dia=("lote", compact_unique),
            ordenes_contexto_sap_dia=("orden", compact_unique),
            eventos_contexto_sap_dia=("clase_transaccion_evento", compact_unique),
            movimientos_contexto_sap_resumen=("clase_movimiento", compact_unique),
            textos_movimiento_contexto_sap=("texto_movimiento_contexto", compact_unique),
            documentos_contexto_sap_dia=("documento_material", compact_unique),
        )
        .reset_index()
    )

    return daily


# ------------------------------------------------------------
# 7. Construcción de línea diaria por ciclo
# ------------------------------------------------------------

daily_lines = []
hitos_records = []

if not cycles_scope.empty:

    for _, cycle in cycles_scope.iterrows():
        base = make_daily_base(cycle)

        if base.empty:
            continue

        birds_daily = aggregate_birds_daily(cycle, kardex)
        feed_daily = aggregate_feed_daily(cycle, kardex)
        production_daily = aggregate_production_daily(cycle, kardex)
        context_daily = aggregate_sap_context_daily(cycle, kardex)

        line = base.merge(birds_daily, on="fecha", how="left")
        line = line.merge(feed_daily, on="fecha", how="left")
        line = line.merge(production_daily, on="fecha", how="left")
        line = line.merge(context_daily, on="fecha", how="left")

        numeric_required = [
            "entrada_aves_dia",
            "anulacion_entrada_aves_dia",
            "entrada_neta_aves_dia",
            "mortalidad_aves_dia",
            "reversa_mortalidad_aves_dia",
            "mortalidad_neta_aves_dia",
            "salida_aves_dia",
            "merma_551_dia",
            "reversa_merma_552_dia",
            "merma_neta_551_552_dia",
            "ajuste_511_dia_contexto",
            "reversa_ajuste_512_dia_contexto",
            "ajuste_511_neto_contexto_dia",
            "movimientos_aves_dia",

            "consumo_alimento_kg_dia",
            "reversa_consumo_alimento_kg_dia",
            "consumo_neto_alimento_kg_dia",
            "consumo_orden_alimento_kg_dia",
            "movimientos_alimento_dia",

            "produccion_huevo_kg_dia",
            "reversa_produccion_huevo_kg_dia",
            "produccion_neta_huevo_kg_dia",
            "movimientos_produccion_dia",

            "movimientos_contexto_sap_dia",
            "movimientos_we_contexto_dia",
            "movimientos_wa_contexto_dia",
            "movimientos_wr_contexto_dia",
            "movimientos_wf_contexto_dia",
            "movimientos_wl_contexto_dia",
            "movimientos_wi_contexto_dia",
            "movimientos_301_contexto_dia",
            "movimientos_311_contexto_dia",
            "movimientos_641_contexto_dia",
            "movimientos_643_contexto_dia",
            "movimientos_511_contexto_dia",
            "movimientos_551_contexto_dia",
            "movimientos_701_702_contexto_dia",

            "contexto_we_abs_dia",
            "contexto_wa_abs_dia",
            "contexto_wr_abs_dia",
            "contexto_wf_abs_dia",
            "contexto_wl_abs_dia",
            "contexto_wi_abs_dia",

            "contexto_we_kg_dia",
            "contexto_wa_kg_dia",
            "contexto_wf_kg_dia",
            "contexto_wl_kg_dia",
            "contexto_wi_kg_dia",
            "contexto_301_kg_dia",
            "contexto_311_kg_dia",
            "contexto_641_wl_kg_dia",
            "contexto_643_wl_kg_dia",

            "contexto_511_abs_dia",
            "contexto_512_abs_dia",
            "contexto_551_abs_dia",
            "contexto_552_abs_dia",
            "contexto_701_abs_dia",
            "contexto_702_abs_dia",
        ]

        for col in line.columns:
            if col.startswith("consumo_kg_") or col.startswith("produccion_kg_"):
                numeric_required.append(col)

        for material, col in FEED_PHASE_COLUMNS.items():
            if col not in numeric_required:
                numeric_required.append(col)

        text_required = [
            "documentos_aves_dia",
            "movimientos_aves_resumen",
            "eventos_aves_resumen",

            "materiales_alimento_dia",
            "fases_alimento_dia",
            "almacenes_alimento_dia",
            "lotes_alimento_dia",
            "documentos_alimento_dia",
            "movimientos_alimento_resumen",
            "eventos_alimento_resumen",

            "materiales_produccion_dia",
            "tipos_huevo_dia",
            "almacenes_produccion_dia",
            "lotes_produccion_dia",
            "documentos_produccion_dia",
            "movimientos_produccion_resumen",
            "eventos_produccion_resumen",

            "materiales_contexto_sap_dia",
            "almacenes_contexto_sap_dia",
            "lotes_contexto_sap_dia",
            "ordenes_contexto_sap_dia",
            "eventos_contexto_sap_dia",
            "movimientos_contexto_sap_resumen",
            "textos_movimiento_contexto_sap",
            "documentos_contexto_sap_dia",
        ]

        line = ensure_numeric_columns(line, numeric_required, default_value=0.0)
        line = ensure_text_columns(line, text_required, default_value="")

        line = line.sort_values("fecha").reset_index(drop=True)

        # ----------------------------------------------------
        # Saldos y acumulados de aves
        # ----------------------------------------------------

        line["saldo_aves_operativo"] = (
            line["entrada_neta_aves_dia"].cumsum()
            - line["mortalidad_neta_aves_dia"].cumsum()
            - line["salida_aves_dia"].cumsum()
            - line["merma_neta_551_552_dia"].cumsum()
        )

        line["saldo_aves_con_511_contexto"] = (
            line["saldo_aves_operativo"]
            + line["ajuste_511_neto_contexto_dia"].cumsum()
        )

        line["mortalidad_neta_aves_acum"] = line["mortalidad_neta_aves_dia"].cumsum()
        line["merma_neta_551_552_acum"] = line["merma_neta_551_552_dia"].cumsum()
        line["salida_aves_acum"] = line["salida_aves_dia"].cumsum()
        line["ajuste_511_neto_contexto_acum"] = line["ajuste_511_neto_contexto_dia"].cumsum()

        # ----------------------------------------------------
        # Acumulados de consumo, producción e ICA
        # ----------------------------------------------------

        line["consumo_alimento_kg_acum"] = line["consumo_neto_alimento_kg_dia"].cumsum()
        line["consumo_orden_alimento_kg_acum"] = line["consumo_orden_alimento_kg_dia"].cumsum()

        line["produccion_huevo_kg_acum"] = line["produccion_neta_huevo_kg_dia"].cumsum()

        line["ica_diario"] = np.where(
            line["produccion_neta_huevo_kg_dia"].gt(0),
            line["consumo_neto_alimento_kg_dia"] / line["produccion_neta_huevo_kg_dia"],
            np.nan,
        )

        line["ica_acumulado"] = np.where(
            line["produccion_huevo_kg_acum"].gt(0),
            line["consumo_alimento_kg_acum"] / line["produccion_huevo_kg_acum"],
            np.nan,
        )

        # ----------------------------------------------------
        # Acumulados por fase consumida por la orden
        # ----------------------------------------------------

        for material, phase_col in FEED_PHASE_COLUMNS.items():
            acum_col = f"{phase_col}_acum"
            line[acum_col] = line[phase_col].cumsum()

        phase_cols_present = [col for col in FEED_PHASE_COLUMNS.values() if col in line.columns]

        if phase_cols_present:
            line["fase_alimento_predominante_dia"] = ""

            for idx, row in line[phase_cols_present].iterrows():
                values = row.fillna(0.0)
                if values.sum() > 0:
                    max_col = values.idxmax()
                    phase_name = max_col.replace("consumo_kg_", "").replace("_", " ").title()
                    line.loc[idx, "fase_alimento_predominante_dia"] = phase_name
        else:
            line["fase_alimento_predominante_dia"] = ""

        # ----------------------------------------------------
        # Acumulados de contexto
        # ----------------------------------------------------

        line["contexto_wl_kg_acum"] = line["contexto_wl_kg_dia"].cumsum()
        line["contexto_wi_kg_acum"] = line["contexto_wi_kg_dia"].cumsum()
        line["contexto_301_kg_acum"] = line["contexto_301_kg_dia"].cumsum()
        line["contexto_311_kg_acum"] = line["contexto_311_kg_dia"].cumsum()
        line["contexto_641_wl_kg_acum"] = line["contexto_641_wl_kg_dia"].cumsum()
        line["contexto_643_wl_kg_acum"] = line["contexto_643_wl_kg_dia"].cumsum()

        # ----------------------------------------------------
        # Flags diarios
        # ----------------------------------------------------

        line["tiene_consumo_dia"] = line["consumo_neto_alimento_kg_dia"].gt(0)
        line["tiene_produccion_dia"] = line["produccion_neta_huevo_kg_dia"].gt(0)
        line["tiene_mortalidad_dia"] = line["mortalidad_neta_aves_dia"].gt(0)
        line["tiene_merma_551_dia"] = line["merma_neta_551_552_dia"].ne(0)
        line["tiene_ajuste_511_dia"] = line["ajuste_511_neto_contexto_dia"].ne(0)
        line["tiene_salida_aves_dia"] = line["salida_aves_dia"].gt(0)

        line["tiene_contexto_wl_dia"] = line["movimientos_wl_contexto_dia"].gt(0)
        line["tiene_contexto_wi_dia"] = line["movimientos_wi_contexto_dia"].gt(0)
        line["tiene_contexto_301_dia"] = line["movimientos_301_contexto_dia"].gt(0)
        line["tiene_contexto_311_dia"] = line["movimientos_311_contexto_dia"].gt(0)
        line["tiene_contexto_641_dia"] = line["movimientos_641_contexto_dia"].gt(0)
        line["tiene_contexto_sap_dia"] = line["movimientos_contexto_sap_dia"].gt(0)

        # ----------------------------------------------------
        # Hitos
        # ----------------------------------------------------

        primera_fecha_consumo = safe_min_date(line, line["tiene_consumo_dia"])
        primera_fecha_produccion = safe_min_date(line, line["tiene_produccion_dia"])
        primera_fecha_mortalidad = safe_min_date(line, line["tiene_mortalidad_dia"])
        primera_fecha_merma_551 = safe_min_date(line, line["tiene_merma_551_dia"])
        primera_fecha_salida_aves = safe_min_date(line, line["tiene_salida_aves_dia"])

        ultima_fecha_consumo = safe_max_date(line, line["tiene_consumo_dia"])
        ultima_fecha_produccion = safe_max_date(line, line["tiene_produccion_dia"])

        line["primera_fecha_consumo"] = primera_fecha_consumo
        line["primera_fecha_produccion"] = primera_fecha_produccion
        line["primera_fecha_mortalidad"] = primera_fecha_mortalidad
        line["primera_fecha_merma_551"] = primera_fecha_merma_551
        line["primera_fecha_salida_aves"] = primera_fecha_salida_aves

        if pd.notna(primera_fecha_produccion):
            line["etapa_productiva"] = np.where(
                line["fecha"].lt(primera_fecha_produccion),
                "pre_produccion",
                "produccion",
            )
        else:
            line["etapa_productiva"] = "sin_produccion_detectada"

        if pd.notna(cycle.get("fecha_fin_ciclo", pd.NaT)):
            line["estatus_dia_ciclo"] = np.where(
                line["fecha"].le(pd.to_datetime(cycle.get("fecha_fin_ciclo"))),
                "dentro_ciclo_cerrado",
                "fuera_ciclo",
            )
        else:
            line["estatus_dia_ciclo"] = "dentro_ciclo_abierto_en_proceso"

        # ----------------------------------------------------
        # Resumen por ciclo
        # ----------------------------------------------------

        saldo_final_operativo = line["saldo_aves_operativo"].iloc[-1]
        saldo_final_con_511 = line["saldo_aves_con_511_contexto"].iloc[-1]

        total_consumo = line["consumo_neto_alimento_kg_dia"].sum()
        total_produccion = line["produccion_neta_huevo_kg_dia"].sum()

        ica_final = np.nan

        if total_produccion > 0:
            ica_final = total_consumo / total_produccion

        phase_totals = {}
        phase_first_dates = {}

        for material, phase_col in FEED_PHASE_COLUMNS.items():
            phase_name = FEED_PHASE_MAP.get(material, material)
            total_col = f"total_consumo_{normalize_label(phase_name)}_kg"
            first_date_col = f"primera_fecha_consumo_{normalize_label(phase_name)}"

            phase_totals[total_col] = line[phase_col].sum()
            phase_first_dates[first_date_col] = safe_min_date(line, line[phase_col].gt(0))

        hitos_record = {
            "cycle_id": cycle["cycle_id"],
            "centro": cycle["centro"],
            "almacen_aves": cycle["almacen"],
            "lote_aves": cycle["lote"],
            "orden_operativa": cycle.get("orden_operativa", pd.NA),
            "estado_ciclo_negocio": cycle.get("estado_ciclo_negocio", ""),
            "fecha_inicio_ciclo": cycle.get("fecha_inicio_ciclo", pd.NaT),
            "fecha_fin_ciclo": cycle.get("fecha_fin_ciclo", pd.NaT),
            "fecha_corte_analisis": cycle.get("fecha_corte_analisis", pd.NaT),
            "motivo_corte_analisis": cycle.get("motivo_corte_analisis", ""),
            "dias_linea_diaria": len(line),

            "entrada_neta_aves_ciclo": cycle.get("entrada_neta_aves", np.nan),

            "primera_fecha_consumo": primera_fecha_consumo,
            "primera_fecha_produccion": primera_fecha_produccion,
            "primera_fecha_mortalidad": primera_fecha_mortalidad,
            "primera_fecha_merma_551": primera_fecha_merma_551,
            "primera_fecha_salida_aves": primera_fecha_salida_aves,

            "ultima_fecha_consumo": ultima_fecha_consumo,
            "ultima_fecha_produccion": ultima_fecha_produccion,

            "dias_hasta_primer_consumo": (
                primera_fecha_consumo - pd.to_datetime(cycle.get("fecha_inicio_ciclo"))
            ).days if pd.notna(primera_fecha_consumo) else np.nan,

            "dias_hasta_primera_produccion": (
                primera_fecha_produccion - pd.to_datetime(cycle.get("fecha_inicio_ciclo"))
            ).days if pd.notna(primera_fecha_produccion) else np.nan,

            "total_consumo_alimento_kg": total_consumo,
            "total_produccion_huevo_kg": total_produccion,
            "ica_acumulado_final": ica_final,

            "mortalidad_neta_total": line["mortalidad_neta_aves_dia"].sum(),
            "merma_neta_551_552_total": line["merma_neta_551_552_dia"].sum(),
            "salida_aves_total": line["salida_aves_dia"].sum(),
            "ajuste_511_neto_contexto_total": line["ajuste_511_neto_contexto_dia"].sum(),

            "saldo_final_operativo": saldo_final_operativo,
            "saldo_final_con_511_contexto": saldo_final_con_511,

            "contexto_we_abs_total": line["contexto_we_abs_dia"].sum(),
            "contexto_wa_abs_total": line["contexto_wa_abs_dia"].sum(),
            "contexto_wf_abs_total": line["contexto_wf_abs_dia"].sum(),
            "contexto_wl_abs_total": line["contexto_wl_abs_dia"].sum(),
            "contexto_wi_abs_total": line["contexto_wi_abs_dia"].sum(),

            "contexto_wl_kg_total": line["contexto_wl_kg_dia"].sum(),
            "contexto_wi_kg_total": line["contexto_wi_kg_dia"].sum(),
            "contexto_301_kg_total": line["contexto_301_kg_dia"].sum(),
            "contexto_311_kg_total": line["contexto_311_kg_dia"].sum(),
            "contexto_641_wl_kg_total": line["contexto_641_wl_kg_dia"].sum(),
            "contexto_643_wl_kg_total": line["contexto_643_wl_kg_dia"].sum(),

            "dias_con_consumo": int(line["tiene_consumo_dia"].sum()),
            "dias_con_produccion": int(line["tiene_produccion_dia"].sum()),
            "dias_con_mortalidad": int(line["tiene_mortalidad_dia"].sum()),
            "dias_con_merma_551": int(line["tiene_merma_551_dia"].sum()),
            "dias_con_ajuste_511": int(line["tiene_ajuste_511_dia"].sum()),
            "dias_con_salida_aves": int(line["tiene_salida_aves_dia"].sum()),

            "dias_con_contexto_wl": int(line["tiene_contexto_wl_dia"].sum()),
            "dias_con_contexto_wi": int(line["tiene_contexto_wi_dia"].sum()),
            "dias_con_contexto_301": int(line["tiene_contexto_301_dia"].sum()),
            "dias_con_contexto_311": int(line["tiene_contexto_311_dia"].sum()),
            "dias_con_contexto_641": int(line["tiene_contexto_641_dia"].sum()),
            "dias_con_contexto_sap": int(line["tiene_contexto_sap_dia"].sum()),
        }

        hitos_record.update(phase_totals)
        hitos_record.update(phase_first_dates)

        hitos_records.append(hitos_record)

        daily_lines.append(line)


# ------------------------------------------------------------
# 8. Consolidar resultados
# ------------------------------------------------------------

if len(daily_lines) > 0:
    linea_diaria_ciclos = pd.concat(daily_lines, ignore_index=True)
else:
    linea_diaria_ciclos = pd.DataFrame()

hitos_productivos_ciclos = pd.DataFrame(hitos_records)

if not linea_diaria_ciclos.empty:
    agg_dict = {
        "fecha_inicio": ("fecha", "min"),
        "fecha_corte": ("fecha", "max"),
        "dias": ("fecha", "size"),

        "consumo_total_kg": ("consumo_neto_alimento_kg_dia", "sum"),
        "produccion_total_kg": ("produccion_neta_huevo_kg_dia", "sum"),
        "mortalidad_total": ("mortalidad_neta_aves_dia", "sum"),
        "merma_551_total": ("merma_neta_551_552_dia", "sum"),
        "salida_aves_total": ("salida_aves_dia", "sum"),
        "ajuste_511_total": ("ajuste_511_neto_contexto_dia", "sum"),

        "saldo_final_operativo": ("saldo_aves_operativo", "last"),
        "saldo_final_con_511": ("saldo_aves_con_511_contexto", "last"),
        "ica_acumulado_final": ("ica_acumulado", "last"),

        "contexto_wl_kg_total": ("contexto_wl_kg_dia", "sum"),
        "contexto_wi_kg_total": ("contexto_wi_kg_dia", "sum"),
        "contexto_301_kg_total": ("contexto_301_kg_dia", "sum"),
        "contexto_311_kg_total": ("contexto_311_kg_dia", "sum"),
        "contexto_641_wl_kg_total": ("contexto_641_wl_kg_dia", "sum"),
        "contexto_643_wl_kg_total": ("contexto_643_wl_kg_dia", "sum"),
        "contexto_511_abs_total": ("contexto_511_abs_dia", "sum"),
        "contexto_551_abs_total": ("contexto_551_abs_dia", "sum"),

        "dias_con_contexto_wl": ("tiene_contexto_wl_dia", "sum"),
        "dias_con_contexto_wi": ("tiene_contexto_wi_dia", "sum"),
        "dias_con_contexto_301": ("tiene_contexto_301_dia", "sum"),
        "dias_con_contexto_311": ("tiene_contexto_311_dia", "sum"),
        "dias_con_contexto_641": ("tiene_contexto_641_dia", "sum"),

        "edad_semana_inicio": ("edad_semana", "min"),
        "edad_semana_fin": ("edad_semana", "max"),
    }

    for material, phase_col in FEED_PHASE_COLUMNS.items():
        phase_name = FEED_PHASE_MAP.get(material, material)
        agg_dict[f"consumo_total_{normalize_label(phase_name)}_kg"] = (phase_col, "sum")

    resumen_linea_diaria_ciclos = (
        linea_diaria_ciclos.groupby(
            [
                "cycle_id",
                "centro",
                "almacen_aves",
                "lote_aves",
                "orden_operativa",
                "estado_ciclo_negocio",
            ],
            dropna=False,
        )
        .agg(**agg_dict)
        .reset_index()
    )
else:
    resumen_linea_diaria_ciclos = pd.DataFrame()


# ------------------------------------------------------------
# 9. Guardar tablas
# ------------------------------------------------------------

save_table(linea_diaria_ciclos, config.tables_dir / "02_linea_diaria_ciclos.csv")
save_table(hitos_productivos_ciclos, config.tables_dir / "02_hitos_productivos_ciclos.csv")
save_table(resumen_linea_diaria_ciclos, config.tables_dir / "02_resumen_linea_diaria_ciclos.csv")


# ------------------------------------------------------------
# 10. Mostrar resultados
# ------------------------------------------------------------

show_md(
    f"""
## Resultado Celda 6

Se construyó la línea diaria de ciclos.

- Filas diarias generadas: **{len(linea_diaria_ciclos):,}**
- Ciclos procesados: **{len(hitos_productivos_ciclos):,}**
- Tabla principal: `02_linea_diaria_ciclos.csv`
- Tabla de hitos: `02_hitos_productivos_ciclos.csv`
- Tabla resumen: `02_resumen_linea_diaria_ciclos.csv`

Lectura:

- Consumo para ICA: `261 WA - 262 WA` de alimento, filtrado por la orden operativa.
- Fases de alimento: se detectan por material `10007-10011`.
- Producción para ICA: `101 WF` huevo normal y `531 WA` subproductos, menos reversas.
- `WI`, `WL`, `301`, `311`, `641`, `643`, `511`, `551` quedan como contexto operativo del ciclo.
- El stock del almacén 1100 se agregará después en la Celda 6A.
"""
)

show_md("## Hitos productivos por ciclo")

display_columns_hitos = existing_columns(
    hitos_productivos_ciclos,
    [
        "cycle_id",
        "almacen_aves",
        "lote_aves",
        "orden_operativa",
        "estado_ciclo_negocio",
        "fecha_inicio_ciclo",
        "fecha_fin_ciclo",
        "fecha_corte_analisis",
        "motivo_corte_analisis",
        "dias_linea_diaria",
        "entrada_neta_aves_ciclo",

        "primera_fecha_consumo",
        "primera_fecha_consumo_fase_1",
        "primera_fecha_consumo_fase_2",
        "primera_fecha_consumo_fase_3",
        "primera_fecha_consumo_fase_4",
        "primera_fecha_consumo_fase_5",
        "primera_fecha_produccion",
        "primera_fecha_mortalidad",
        "primera_fecha_salida_aves",

        "total_consumo_alimento_kg",
        "total_consumo_fase_1_kg",
        "total_consumo_fase_2_kg",
        "total_consumo_fase_3_kg",
        "total_consumo_fase_4_kg",
        "total_consumo_fase_5_kg",
        "total_produccion_huevo_kg",
        "ica_acumulado_final",

        "mortalidad_neta_total",
        "merma_neta_551_552_total",
        "salida_aves_total",
        "ajuste_511_neto_contexto_total",

        "saldo_final_operativo",
        "saldo_final_con_511_contexto",

        "contexto_wl_kg_total",
        "contexto_wi_kg_total",
        "contexto_301_kg_total",
        "contexto_311_kg_total",
        "contexto_641_wl_kg_total",
        "contexto_643_wl_kg_total",

        "dias_con_consumo",
        "dias_con_produccion",
        "dias_con_mortalidad",
        "dias_con_merma_551",
        "dias_con_ajuste_511",
        "dias_con_salida_aves",
        "dias_con_contexto_wl",
        "dias_con_contexto_wi",
        "dias_con_contexto_301",
        "dias_con_contexto_311",
        "dias_con_contexto_641",
        "dias_con_contexto_sap",
    ],
)

display(hitos_productivos_ciclos[display_columns_hitos])

show_md("## Resumen por ciclo")

display_columns_resumen = existing_columns(
    resumen_linea_diaria_ciclos,
    [
        "cycle_id",
        "almacen_aves",
        "lote_aves",
        "orden_operativa",
        "estado_ciclo_negocio",
        "fecha_inicio",
        "fecha_corte",
        "dias",
        "edad_semana_inicio",
        "edad_semana_fin",

        "consumo_total_kg",
        "consumo_total_fase_1_kg",
        "consumo_total_fase_2_kg",
        "consumo_total_fase_3_kg",
        "consumo_total_fase_4_kg",
        "consumo_total_fase_5_kg",
        "produccion_total_kg",
        "ica_acumulado_final",

        "mortalidad_total",
        "merma_551_total",
        "salida_aves_total",
        "ajuste_511_total",

        "saldo_final_operativo",
        "saldo_final_con_511",

        "contexto_wl_kg_total",
        "contexto_wi_kg_total",
        "contexto_301_kg_total",
        "contexto_311_kg_total",
        "contexto_641_wl_kg_total",
        "contexto_643_wl_kg_total",
        "contexto_511_abs_total",
        "contexto_551_abs_total",
        "dias_con_contexto_wl",
        "dias_con_contexto_wi",
        "dias_con_contexto_301",
        "dias_con_contexto_311",
        "dias_con_contexto_641",
    ],
)

display(resumen_linea_diaria_ciclos[display_columns_resumen])

show_md("## Vista previa de la línea diaria")

display_columns_linea = existing_columns(
    linea_diaria_ciclos,
    [
        "fecha",
        "cycle_id",
        "almacen_aves",
        "lote_aves",
        "orden_operativa",
        "estado_ciclo_negocio",
        "edad_semana",
        "edad_dia_semana",

        "entrada_neta_aves_dia",
        "mortalidad_neta_aves_dia",
        "merma_neta_551_552_dia",
        "salida_aves_dia",
        "ajuste_511_neto_contexto_dia",
        "saldo_aves_operativo",
        "saldo_aves_con_511_contexto",

        "consumo_neto_alimento_kg_dia",
        "consumo_orden_alimento_kg_dia",
        "materiales_alimento_dia",
        "fases_alimento_dia",
        "fase_alimento_predominante_dia",
        "consumo_kg_fase_1",
        "consumo_kg_fase_2",
        "consumo_kg_fase_3",
        "consumo_kg_fase_4",
        "consumo_kg_fase_5",

        "produccion_neta_huevo_kg_dia",
        "ica_diario",
        "ica_acumulado",

        "movimientos_wl_contexto_dia",
        "movimientos_wi_contexto_dia",
        "movimientos_301_contexto_dia",
        "movimientos_311_contexto_dia",
        "movimientos_641_contexto_dia",
        "contexto_wl_kg_dia",
        "contexto_wi_kg_dia",
        "contexto_301_kg_dia",
        "contexto_311_kg_dia",
        "contexto_641_wl_kg_dia",
        "materiales_contexto_sap_dia",
        "movimientos_contexto_sap_resumen",
        "eventos_contexto_sap_dia",

        "etapa_productiva",
        "estatus_dia_ciclo",
    ],
)

display(linea_diaria_ciclos[display_columns_linea].head(120))