# ============================================================
# CELDA 6A — Reconstrucción de stock de alimento del almacén 1100
# ============================================================
# Objetivo:
# - Usar MB5B como stock inicial real al día anterior del primer ciclo.
# - Usar MB51/kardex para reconstruir movimientos diarios de alimento.
# - Crear stock diario por fase/material del almacén 1100.
# - Unir ese stock a linea_diaria_ciclos.
#
# Regla:
# - Stock alimento = centro + almacén 1100 + material/fase + todos los movimientos de inventario.
# - Consumo parvada = orden_operativa + material/fase + 261/262.
# - ICA sigue usando solo consumo de la orden y producción de la orden.
# ============================================================

from pathlib import Path
import re
import numpy as np
import pandas as pd

# ------------------------------------------------------------
# 0. Validaciones base
# ------------------------------------------------------------

if "kardex" not in globals():
    raise ValueError("No existe kardex. Ejecuta primero las celdas de carga.")

if "cycles_scope" not in globals():
    raise ValueError("No existe cycles_scope. Ejecuta primero la Celda 5.")

if "linea_diaria_ciclos" not in globals():
    raise ValueError("No existe linea_diaria_ciclos. Ejecuta primero la Celda 6.")

if linea_diaria_ciclos.empty:
    raise ValueError("linea_diaria_ciclos está vacío. Revisa la Celda 6.")

# ------------------------------------------------------------
# 1. Configuración de alimento y fecha ancla
# ------------------------------------------------------------

ALIMENTO_CENTRO = str(getattr(config, "center_id", "0000"))
ALIMENTO_ALMACEN = "1100"

FEED_MATERIALS_STOCK = {
    "10007": "Fase 1",
    "10008": "Fase 2",
    "10009": "Fase 3",
    "10010": "Fase 4",
    "10011": "Fase 5",
}

FEED_MATERIAL_LIST_STOCK = list(FEED_MATERIALS_STOCK.keys())

fecha_inicio_mas_antigua_parvada = pd.to_datetime(
    cycles_scope["fecha_inicio_ciclo"],
    errors="coerce",
).min()

# ------------------------------------------------------------
# Regla de inicio operativo del alimento
# ------------------------------------------------------------
# El inicio biológico sigue siendo el 101 WE del material 20019.
# Para el almacén de alimento, la historia debe comenzar desde la primera
# entrada 101 WE relevante, aunque ocurra antes de la entrada de las aves.

kardex_fechas_6a = pd.to_datetime(kardex["fecha"], errors="coerce")
kardex_mov_6a = kardex["clase_movimiento"].astype("string").str.upper().fillna("")
kardex_evt_6a = kardex["clase_transaccion_evento"].astype("string").str.upper().fillna("")

mask_entrada_alimento_101_we_6a = (
    kardex["centro"].astype("string").eq(ALIMENTO_CENTRO)
    & kardex["almacen"].astype("string").eq(ALIMENTO_ALMACEN)
    & kardex["material"].astype("string").isin(FEED_MATERIAL_LIST_STOCK)
    & kardex_mov_6a.eq("101")
    & kardex_evt_6a.eq("WE")
    & kardex_fechas_6a.notna()
)

entradas_alimento_101_we_6a = kardex.loc[
    mask_entrada_alimento_101_we_6a
].copy()

entradas_alimento_101_we_6a["fecha"] = pd.to_datetime(
    entradas_alimento_101_we_6a["fecha"],
    errors="coerce",
)

# Para no traer movimientos históricos sin relación con el scope,
# se toma la última entrada 101 WE existente antes o en la fecha del
# primer inicio biológico. Si no existe, se inicia en la fecha de aves.
entradas_previas_primer_ciclo_6a = entradas_alimento_101_we_6a.loc[
    entradas_alimento_101_we_6a["fecha"].le(fecha_inicio_mas_antigua_parvada)
].copy()

if not entradas_previas_primer_ciclo_6a.empty:
    fecha_primera_entrada_alimento_scope = (
        entradas_previas_primer_ciclo_6a["fecha"].max()
    )
else:
    fecha_primera_entrada_alimento_scope = fecha_inicio_mas_antigua_parvada

fecha_inicio_movimientos_alimento = min(
    fecha_inicio_mas_antigua_parvada,
    fecha_primera_entrada_alimento_scope,
)

# MB5B representa el saldo al cierre del día anterior.
fecha_ancla_stock_alimento = (
    fecha_inicio_movimientos_alimento - pd.Timedelta(days=1)
)

fecha_fin_movimientos_alimento = pd.to_datetime(
    cycles_scope["fecha_corte_analisis"],
    errors="coerce",
).max()

if pd.isna(fecha_fin_movimientos_alimento):
    fecha_fin_movimientos_alimento = pd.to_datetime(
        kardex["fecha"],
        errors="coerce",
    ).max()

# Si tienes el archivo MB5B en data/raw, pon aquí el nombre.
# Si no existe o falla la lectura, la celda usará el stock manual.
MB5B_STOCK_FILE = Path(getattr(config, "raw_dir", Path("."))) / "EXPORT_20260616_121341.xlsx"
USAR_MB5B_EXCEL_SI_EXISTE = True

# Como ya validaste que MB5B al 06/07/2024 dio cero para alimento,
# dejamos el stock manual en cero como respaldo.
STOCK_INICIAL_MANUAL_KG = {
    "10007": 0.0,
    "10008": 0.0,
    "10009": 0.0,
    "10010": 0.0,
    "10011": 0.0,
}

show_md(
    f"""
## Celda 6A — Reconstrucción de stock de alimento

Fecha ancla de stock inicial: **{fecha_ancla_stock_alimento.date()}**

Primera entrada `101 WE` de alimento usada para iniciar la reconstrucción:
**{fecha_inicio_movimientos_alimento.date()}**

Se reconstruirá el stock del alimento para:

- Centro: **{ALIMENTO_CENTRO}**
- Almacén alimento: **{ALIMENTO_ALMACEN}**
- Materiales/fases: **10007 a 10011**
- Desde movimientos MB51: **{fecha_inicio_movimientos_alimento.date()}** a **{fecha_fin_movimientos_alimento.date()}**

Lectura:

- MB5B da el stock inicial real.
- MB51 da entradas, consumos, reversas, ajustes y traspasos.
- El stock reconstruido es del almacén 1100 completo, no de una sola orden.
"""
)

# ------------------------------------------------------------
# 2. Funciones auxiliares
# ------------------------------------------------------------

def normalize_label_6a(value):
    value = str(value).lower().strip()
    value = value.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    value = value.replace("ñ", "n")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value


def clean_key_6a(value):
    if pd.isna(value):
        return pd.NA

    text = str(value).strip()

    if text.endswith(".0"):
        text = text[:-2]

    text = text.replace(",", "").strip()

    if text == "" or text.lower() in ["nan", "none", "<na>"]:
        return pd.NA

    return text


def parse_sap_number_6a(value):
    if pd.isna(value):
        return np.nan

    if isinstance(value, (int, float, np.integer, np.floating)):
        return float(value)

    text = str(value).strip()

    if text == "" or text.lower() in ["nan", "none", "<na>"]:
        return np.nan

    negative = False

    if text.endswith("-"):
        negative = True
        text = text[:-1]

    if text.startswith("-"):
        negative = True
        text = text[1:]

    text = text.replace(",", "")
    text = text.replace(" ", "")

    try:
        number = float(text)
    except Exception:
        return np.nan

    if negative:
        number = -number

    return number


def safe_col_6a(df, column, default_value=pd.NA):
    if column in df.columns:
        return df[column]
    return pd.Series(default_value, index=df.index)


def safe_num_6a(series):
    return pd.to_numeric(series, errors="coerce")


def text_upper_6a(series):
    return series.astype("string").str.upper().fillna("")


def compact_unique_6a(series, max_values=15):
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


def choose_quantity_kg_signed_6a(df):
    qty_ump = safe_num_6a(safe_col_6a(df, "cantidad_ump", np.nan))
    qty_ume = safe_num_6a(safe_col_6a(df, "cantidad_um_entrada", np.nan))
    qty_abs = safe_num_6a(safe_col_6a(df, "cantidad_abs", np.nan))

    unit_ump = text_upper_6a(safe_col_6a(df, "unidad_medida_paralela", ""))
    unit_ume = text_upper_6a(safe_col_6a(df, "unidad_medida_entrada", ""))

    qty = pd.Series(np.nan, index=df.index, dtype="float64")

    mask_ump_kg = unit_ump.str.contains("KG", na=False) & qty_ump.notna()
    qty.loc[mask_ump_kg] = qty_ump.loc[mask_ump_kg]

    mask_ume_kg = qty.isna() & unit_ume.str.contains("KG", na=False) & qty_ume.notna()
    qty.loc[mask_ume_kg] = qty_ume.loc[mask_ume_kg]

    mask_fallback = qty.isna() & qty_abs.notna()
    qty.loc[mask_fallback] = qty_abs.loc[mask_fallback]

    return qty.fillna(0.0)


def choose_quantity_kg_abs_6a(df):
    qty = choose_quantity_kg_signed_6a(df)
    return qty.abs()


def normalize_columns_6a(columns):
    normalized = []

    for col in columns:
        text = str(col).strip().lower()
        text = text.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
        text = text.replace("ñ", "n")
        text = re.sub(r"[^a-z0-9]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_")
        normalized.append(text)

    return normalized


def find_first_col_6a(df, candidates, contains_any=None):
    for candidate in candidates:
        if candidate in df.columns:
            return candidate

    if contains_any:
        for col in df.columns:
            col_text = str(col).lower()
            if any(token in col_text for token in contains_any):
                return col

    return None


# ------------------------------------------------------------
# 3. Cargar stock inicial MB5B o usar manual
# ------------------------------------------------------------

def load_mb5b_stock_initial_6a(file_path):
    file_path = Path(file_path)

    if not file_path.exists():
        return pd.DataFrame()

    try:
        sheets = pd.read_excel(file_path, sheet_name=None)
    except Exception:
        return pd.DataFrame()

    parsed_frames = []

    for sheet_name, raw in sheets.items():
        if raw.empty:
            continue

        df = raw.copy()
        df.columns = normalize_columns_6a(df.columns)

        material_col = find_first_col_6a(
            df,
            candidates=["material", "numero_de_material", "n_material", "cod_material"],
            contains_any=["material"],
        )

        centro_col = find_first_col_6a(
            df,
            candidates=["centro", "ce"],
            contains_any=["centro"],
        )

        almacen_col = find_first_col_6a(
            df,
            candidates=["almacen", "almacen_"],
            contains_any=["almacen"],
        )

        qty_col = find_first_col_6a(
            df,
            candidates=[
                "stock_final",
                "stock_cierre",
                "stock_libre_utilizacion",
                "libre_utilizacion",
                "cantidad_stock",
                "stock",
                "total_stock",
                "cantidad",
            ],
            contains_any=["stock", "libre", "cantidad"],
        )

        if material_col is None or qty_col is None:
            continue

        temp = pd.DataFrame()
        temp["material"] = df[material_col].map(clean_key_6a)

        if centro_col is not None:
            temp["centro"] = df[centro_col].map(clean_key_6a)
        else:
            temp["centro"] = ALIMENTO_CENTRO

        if almacen_col is not None:
            temp["almacen"] = df[almacen_col].map(clean_key_6a)
        else:
            temp["almacen"] = ALIMENTO_ALMACEN

        temp["stock_inicial_kg"] = df[qty_col].map(parse_sap_number_6a)
        temp["hoja_mb5b"] = sheet_name

        temp = temp.loc[
            temp["material"].isin(FEED_MATERIAL_LIST_STOCK)
            & temp["centro"].eq(ALIMENTO_CENTRO)
            & temp["almacen"].eq(ALIMENTO_ALMACEN)
        ].copy()

        if not temp.empty:
            parsed_frames.append(temp)

    if not parsed_frames:
        return pd.DataFrame()

    result = pd.concat(parsed_frames, ignore_index=True)

    result = (
        result.groupby(["centro", "almacen", "material"], dropna=False)
        .agg(
            stock_inicial_kg=("stock_inicial_kg", "sum"),
            hojas_mb5b=("hoja_mb5b", compact_unique_6a),
        )
        .reset_index()
    )

    return result


stock_inicial_from_excel = pd.DataFrame()

if USAR_MB5B_EXCEL_SI_EXISTE:
    stock_inicial_from_excel = load_mb5b_stock_initial_6a(MB5B_STOCK_FILE)

if not stock_inicial_from_excel.empty:
    stock_inicial_alimento_mb5b = stock_inicial_from_excel.copy()
    stock_inicial_alimento_mb5b["fuente_stock_inicial"] = f"MB5B Excel: {MB5B_STOCK_FILE.name}"
else:
    stock_inicial_alimento_mb5b = pd.DataFrame(
        [
            {
                "centro": ALIMENTO_CENTRO,
                "almacen": ALIMENTO_ALMACEN,
                "material": material,
                "stock_inicial_kg": STOCK_INICIAL_MANUAL_KG.get(material, 0.0),
                "fuente_stock_inicial": "manual_respaldo",
            }
            for material in FEED_MATERIAL_LIST_STOCK
        ]
    )

stock_inicial_alimento_mb5b["fase_alimento"] = stock_inicial_alimento_mb5b["material"].map(FEED_MATERIALS_STOCK)
stock_inicial_alimento_mb5b["fecha_stock_inicial"] = fecha_ancla_stock_alimento

stock_inicial_alimento_mb5b = stock_inicial_alimento_mb5b[
    [
        "fecha_stock_inicial",
        "centro",
        "almacen",
        "material",
        "fase_alimento",
        "stock_inicial_kg",
        "fuente_stock_inicial",
    ]
].copy()

# Asegurar que existan los 5 materiales aunque MB5B no los haya traído
missing_materials = sorted(
    set(FEED_MATERIAL_LIST_STOCK) - set(stock_inicial_alimento_mb5b["material"].dropna().astype(str))
)

if missing_materials:
    missing_rows = pd.DataFrame(
        [
            {
                "fecha_stock_inicial": fecha_ancla_stock_alimento,
                "centro": ALIMENTO_CENTRO,
                "almacen": ALIMENTO_ALMACEN,
                "material": material,
                "fase_alimento": FEED_MATERIALS_STOCK.get(material, material),
                "stock_inicial_kg": STOCK_INICIAL_MANUAL_KG.get(material, 0.0),
                "fuente_stock_inicial": "manual_material_faltante_en_mb5b",
            }
            for material in missing_materials
        ]
    )

    stock_inicial_alimento_mb5b = pd.concat(
        [stock_inicial_alimento_mb5b, missing_rows],
        ignore_index=True,
    )

# ------------------------------------------------------------
# 4. Filtrar movimientos MB51/kardex del alimento en almacén 1100
# ------------------------------------------------------------

movimientos_alimento_1100_stock = kardex.loc[
    kardex["centro"].eq(ALIMENTO_CENTRO)
    & kardex["almacen"].eq(ALIMENTO_ALMACEN)
    & kardex["material"].isin(FEED_MATERIAL_LIST_STOCK)
    & pd.to_datetime(kardex["fecha"], errors="coerce").ge(fecha_inicio_movimientos_alimento)
    & pd.to_datetime(kardex["fecha"], errors="coerce").le(fecha_fin_movimientos_alimento)
].copy()

if movimientos_alimento_1100_stock.empty:
    show_md(
        """
## Advertencia

No se encontraron movimientos de alimento en el almacén 1100 dentro del rango analizado.
Se generará stock diario usando solo el stock inicial.
"""
    )
else:
    movimientos_alimento_1100_stock["fecha"] = pd.to_datetime(
        movimientos_alimento_1100_stock["fecha"],
        errors="coerce",
    )

    movimientos_alimento_1100_stock["fase_alimento"] = (
        movimientos_alimento_1100_stock["material"].map(FEED_MATERIALS_STOCK)
    )

    mov = text_upper_6a(movimientos_alimento_1100_stock["clase_movimiento"])
    evt = text_upper_6a(movimientos_alimento_1100_stock["clase_transaccion_evento"])

    movimientos_alimento_1100_stock["cantidad_kg_signed_sap"] = choose_quantity_kg_signed_6a(
        movimientos_alimento_1100_stock
    )

    movimientos_alimento_1100_stock["cantidad_kg_abs"] = choose_quantity_kg_abs_6a(
        movimientos_alimento_1100_stock
    )

    qty_abs = movimientos_alimento_1100_stock["cantidad_kg_abs"]
    qty_signed = movimientos_alimento_1100_stock["cantidad_kg_signed_sap"]

    # Efecto de stock:
    # Para movimientos con dirección estándar, usamos regla de signo.
    # Para traspasos/logística, usamos el signo de SAP porque puede sumar o restar.
    movimientos_alimento_1100_stock["efecto_stock_kg"] = 0.0
    movimientos_alimento_1100_stock["tipo_movimiento_stock"] = "otro_movimiento_stock_revisar"

    mask_101_we = mov.eq("101") & evt.eq("WE")
    mask_102_we = mov.eq("102") & evt.eq("WE")
    mask_261_wa = mov.eq("261") & evt.eq("WA")
    mask_262_wa = mov.eq("262") & evt.eq("WA")

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

    mask_wi = evt.eq("WI")
    mask_wl = evt.eq("WL")

    movimientos_alimento_1100_stock.loc[mask_101_we, "efecto_stock_kg"] = qty_abs.loc[mask_101_we]
    movimientos_alimento_1100_stock.loc[mask_101_we, "tipo_movimiento_stock"] = "entrada_101_we"

    movimientos_alimento_1100_stock.loc[mask_102_we, "efecto_stock_kg"] = -qty_abs.loc[mask_102_we]
    movimientos_alimento_1100_stock.loc[mask_102_we, "tipo_movimiento_stock"] = "reversa_entrada_102_we"

    movimientos_alimento_1100_stock.loc[mask_261_wa, "efecto_stock_kg"] = -qty_abs.loc[mask_261_wa]
    movimientos_alimento_1100_stock.loc[mask_261_wa, "tipo_movimiento_stock"] = "consumo_261_wa"

    movimientos_alimento_1100_stock.loc[mask_262_wa, "efecto_stock_kg"] = qty_abs.loc[mask_262_wa]
    movimientos_alimento_1100_stock.loc[mask_262_wa, "tipo_movimiento_stock"] = "reversa_consumo_262_wa"

    movimientos_alimento_1100_stock.loc[mask_511, "efecto_stock_kg"] = qty_abs.loc[mask_511]
    movimientos_alimento_1100_stock.loc[mask_511, "tipo_movimiento_stock"] = "ajuste_positivo_511"

    movimientos_alimento_1100_stock.loc[mask_512, "efecto_stock_kg"] = -qty_abs.loc[mask_512]
    movimientos_alimento_1100_stock.loc[mask_512, "tipo_movimiento_stock"] = "reversa_ajuste_512"

    movimientos_alimento_1100_stock.loc[mask_551, "efecto_stock_kg"] = -qty_abs.loc[mask_551]
    movimientos_alimento_1100_stock.loc[mask_551, "tipo_movimiento_stock"] = "merma_baja_551"

    movimientos_alimento_1100_stock.loc[mask_552, "efecto_stock_kg"] = qty_abs.loc[mask_552]
    movimientos_alimento_1100_stock.loc[mask_552, "tipo_movimiento_stock"] = "reversa_merma_552"

    movimientos_alimento_1100_stock.loc[mask_701, "efecto_stock_kg"] = qty_abs.loc[mask_701]
    movimientos_alimento_1100_stock.loc[mask_701, "tipo_movimiento_stock"] = "ajuste_inventario_701_wi"

    movimientos_alimento_1100_stock.loc[mask_702, "efecto_stock_kg"] = -qty_abs.loc[mask_702]
    movimientos_alimento_1100_stock.loc[mask_702, "tipo_movimiento_stock"] = "ajuste_inventario_702_wi"

    mask_traspaso_logistico = mask_301 | mask_311 | mask_641 | mask_643
    movimientos_alimento_1100_stock.loc[mask_traspaso_logistico, "efecto_stock_kg"] = qty_signed.loc[mask_traspaso_logistico]

    movimientos_alimento_1100_stock.loc[mask_301, "tipo_movimiento_stock"] = "traspaso_301_signo_sap"
    movimientos_alimento_1100_stock.loc[mask_311, "tipo_movimiento_stock"] = "traspaso_311_signo_sap"
    movimientos_alimento_1100_stock.loc[mask_641, "tipo_movimiento_stock"] = "logistico_641_signo_sap"
    movimientos_alimento_1100_stock.loc[mask_643, "tipo_movimiento_stock"] = "logistico_643_signo_sap"

    mask_wi_otro = mask_wi & ~mask_701 & ~mask_702
    movimientos_alimento_1100_stock.loc[mask_wi_otro, "efecto_stock_kg"] = qty_signed.loc[mask_wi_otro]
    movimientos_alimento_1100_stock.loc[mask_wi_otro, "tipo_movimiento_stock"] = "ajuste_wi_signo_sap"

    mask_wl_otro = mask_wl & ~mask_641 & ~mask_643
    movimientos_alimento_1100_stock.loc[mask_wl_otro, "efecto_stock_kg"] = qty_signed.loc[mask_wl_otro]
    movimientos_alimento_1100_stock.loc[mask_wl_otro, "tipo_movimiento_stock"] = "logistico_wl_signo_sap"

    movimientos_alimento_1100_stock["es_entrada_stock"] = movimientos_alimento_1100_stock["efecto_stock_kg"].gt(0)
    movimientos_alimento_1100_stock["es_salida_stock"] = movimientos_alimento_1100_stock["efecto_stock_kg"].lt(0)

    movimientos_alimento_1100_stock["es_entrada_101_we"] = mask_101_we
    movimientos_alimento_1100_stock["es_reversa_102_we"] = mask_102_we
    movimientos_alimento_1100_stock["es_consumo_261_wa"] = mask_261_wa
    movimientos_alimento_1100_stock["es_reversa_262_wa"] = mask_262_wa
    movimientos_alimento_1100_stock["es_traspaso_301_311"] = mask_301 | mask_311
    movimientos_alimento_1100_stock["es_wi"] = mask_wi
    movimientos_alimento_1100_stock["es_wl"] = mask_wl
    movimientos_alimento_1100_stock["es_641_643"] = mask_641 | mask_643
    movimientos_alimento_1100_stock["es_511_512"] = mask_511 | mask_512
    movimientos_alimento_1100_stock["es_551_552"] = mask_551 | mask_552

# ------------------------------------------------------------
# 5. Agregación diaria larga por material/fase
# ------------------------------------------------------------

date_index = pd.date_range(
    fecha_ancla_stock_alimento,
    fecha_fin_movimientos_alimento,
    freq="D",
)

base_stock_daily = pd.MultiIndex.from_product(
    [
        date_index,
        FEED_MATERIAL_LIST_STOCK,
    ],
    names=["fecha", "material"],
).to_frame(index=False)

base_stock_daily["centro"] = ALIMENTO_CENTRO
base_stock_daily["almacen"] = ALIMENTO_ALMACEN
base_stock_daily["fase_alimento"] = base_stock_daily["material"].map(FEED_MATERIALS_STOCK)

if movimientos_alimento_1100_stock.empty:
    mov_daily = pd.DataFrame(columns=["fecha", "material"])
else:
    mov_daily = (
        movimientos_alimento_1100_stock.groupby(["fecha", "material", "fase_alimento"], dropna=False)
        .agg(
            movimiento_stock_kg_dia=("efecto_stock_kg", "sum"),

            entrada_stock_kg_dia=("efecto_stock_kg", lambda s: s[s > 0].sum()),
            salida_stock_kg_dia=("efecto_stock_kg", lambda s: s[s < 0].sum()),

            entrada_101_we_kg_dia=(
                "cantidad_kg_abs",
                lambda s: s[movimientos_alimento_1100_stock.loc[s.index, "es_entrada_101_we"]].sum(),
            ),
            reversa_102_we_kg_dia=(
                "cantidad_kg_abs",
                lambda s: s[movimientos_alimento_1100_stock.loc[s.index, "es_reversa_102_we"]].sum(),
            ),
            consumo_total_almacen_kg_dia=(
                "cantidad_kg_abs",
                lambda s: s[movimientos_alimento_1100_stock.loc[s.index, "es_consumo_261_wa"]].sum(),
            ),
            reversa_consumo_262_kg_dia=(
                "cantidad_kg_abs",
                lambda s: s[movimientos_alimento_1100_stock.loc[s.index, "es_reversa_262_wa"]].sum(),
            ),
            traspaso_301_311_kg_dia=(
                "efecto_stock_kg",
                lambda s: s[movimientos_alimento_1100_stock.loc[s.index, "es_traspaso_301_311"]].sum(),
            ),
            ajuste_wi_kg_dia=(
                "efecto_stock_kg",
                lambda s: s[movimientos_alimento_1100_stock.loc[s.index, "es_wi"]].sum(),
            ),
            logistico_wl_kg_dia=(
                "efecto_stock_kg",
                lambda s: s[movimientos_alimento_1100_stock.loc[s.index, "es_wl"]].sum(),
            ),
            logistico_641_643_kg_dia=(
                "efecto_stock_kg",
                lambda s: s[movimientos_alimento_1100_stock.loc[s.index, "es_641_643"]].sum(),
            ),
            ajuste_511_512_kg_dia=(
                "efecto_stock_kg",
                lambda s: s[movimientos_alimento_1100_stock.loc[s.index, "es_511_512"]].sum(),
            ),
            merma_551_552_kg_dia=(
                "efecto_stock_kg",
                lambda s: s[movimientos_alimento_1100_stock.loc[s.index, "es_551_552"]].sum(),
            ),

            movimientos_alimento_stock_dia=("material", "size"),
            ordenes_consumo_alimento_dia=("orden", compact_unique_6a),
            lotes_alimento_stock_dia=("lote", compact_unique_6a),
            documentos_alimento_stock_dia=("documento_material", compact_unique_6a),
            movimientos_stock_resumen=("clase_movimiento", compact_unique_6a),
            eventos_stock_resumen=("clase_transaccion_evento", compact_unique_6a),
            tipos_movimiento_stock_resumen=("tipo_movimiento_stock", compact_unique_6a),
        )
        .reset_index()
    )

stock_diario_alimento_1100_largo = base_stock_daily.merge(
    mov_daily,
    on=["fecha", "material", "fase_alimento"],
    how="left",
)

numeric_stock_cols = [
    "movimiento_stock_kg_dia",
    "entrada_stock_kg_dia",
    "salida_stock_kg_dia",
    "entrada_101_we_kg_dia",
    "reversa_102_we_kg_dia",
    "consumo_total_almacen_kg_dia",
    "reversa_consumo_262_kg_dia",
    "traspaso_301_311_kg_dia",
    "ajuste_wi_kg_dia",
    "logistico_wl_kg_dia",
    "logistico_641_643_kg_dia",
    "ajuste_511_512_kg_dia",
    "merma_551_552_kg_dia",
    "movimientos_alimento_stock_dia",
]

for col in numeric_stock_cols:
    if col not in stock_diario_alimento_1100_largo.columns:
        stock_diario_alimento_1100_largo[col] = 0.0
    else:
        stock_diario_alimento_1100_largo[col] = safe_num_6a(stock_diario_alimento_1100_largo[col]).fillna(0.0)

text_stock_cols = [
    "ordenes_consumo_alimento_dia",
    "lotes_alimento_stock_dia",
    "documentos_alimento_stock_dia",
    "movimientos_stock_resumen",
    "eventos_stock_resumen",
    "tipos_movimiento_stock_resumen",
]

for col in text_stock_cols:
    if col not in stock_diario_alimento_1100_largo.columns:
        stock_diario_alimento_1100_largo[col] = ""
    else:
        stock_diario_alimento_1100_largo[col] = stock_diario_alimento_1100_largo[col].fillna("")

stock_diario_alimento_1100_largo = stock_diario_alimento_1100_largo.merge(
    stock_inicial_alimento_mb5b[
        [
            "centro",
            "almacen",
            "material",
            "stock_inicial_kg",
            "fuente_stock_inicial",
            "fecha_stock_inicial",
        ]
    ],
    on=["centro", "almacen", "material"],
    how="left",
)

stock_diario_alimento_1100_largo["stock_inicial_kg"] = (
    safe_num_6a(stock_diario_alimento_1100_largo["stock_inicial_kg"]).fillna(0.0)
)

stock_diario_alimento_1100_largo = stock_diario_alimento_1100_largo.sort_values(
    ["material", "fecha"]
).reset_index(drop=True)

stock_diario_alimento_1100_largo["movimiento_stock_kg_acum"] = (
    stock_diario_alimento_1100_largo.groupby("material")["movimiento_stock_kg_dia"].cumsum()
)

stock_diario_alimento_1100_largo["stock_cierre_kg"] = (
    stock_diario_alimento_1100_largo["stock_inicial_kg"]
    + stock_diario_alimento_1100_largo["movimiento_stock_kg_acum"]
)

stock_diario_alimento_1100_largo["stock_inicio_dia_kg"] = (
    stock_diario_alimento_1100_largo.groupby("material")["stock_cierre_kg"].shift(1)
)

stock_diario_alimento_1100_largo["stock_inicio_dia_kg"] = (
    stock_diario_alimento_1100_largo["stock_inicio_dia_kg"].fillna(
        stock_diario_alimento_1100_largo["stock_inicial_kg"]
    )
)

stock_diario_alimento_1100_largo["stock_negativo_flag"] = (
    stock_diario_alimento_1100_largo["stock_cierre_kg"].lt(0)
)

stock_diario_alimento_1100_largo["stock_cero_o_menor_flag"] = (
    stock_diario_alimento_1100_largo["stock_cierre_kg"].le(0)
)

# ------------------------------------------------------------
# 6. Tabla diaria ancha para unir con la línea de ciclos
# ------------------------------------------------------------

stock_daily_total = (
    stock_diario_alimento_1100_largo.groupby(["fecha", "centro", "almacen"], dropna=False)
    .agg(
        stock_alimento_total_kg=("stock_cierre_kg", "sum"),
        stock_inicio_alimento_total_kg=("stock_inicio_dia_kg", "sum"),
        movimiento_stock_alimento_total_kg_dia=("movimiento_stock_kg_dia", "sum"),
        entrada_stock_alimento_total_kg_dia=("entrada_stock_kg_dia", "sum"),
        salida_stock_alimento_total_kg_dia=("salida_stock_kg_dia", "sum"),
        entrada_101_we_alimento_total_kg_dia=("entrada_101_we_kg_dia", "sum"),
        reversa_102_we_alimento_total_kg_dia=("reversa_102_we_kg_dia", "sum"),
        consumo_total_almacen_alimento_kg_dia=("consumo_total_almacen_kg_dia", "sum"),
        reversa_consumo_262_alimento_kg_dia=("reversa_consumo_262_kg_dia", "sum"),
        traspaso_301_311_alimento_kg_dia=("traspaso_301_311_kg_dia", "sum"),
        ajuste_wi_alimento_kg_dia=("ajuste_wi_kg_dia", "sum"),
        logistico_wl_alimento_kg_dia=("logistico_wl_kg_dia", "sum"),
        logistico_641_643_alimento_kg_dia=("logistico_641_643_kg_dia", "sum"),
        ajuste_511_512_alimento_kg_dia=("ajuste_511_512_kg_dia", "sum"),
        merma_551_552_alimento_kg_dia=("merma_551_552_kg_dia", "sum"),
        movimientos_alimento_stock_dia=("movimientos_alimento_stock_dia", "sum"),
        stock_negativo_fases=("stock_negativo_flag", "sum"),
        stock_cero_o_menor_fases=("stock_cero_o_menor_flag", "sum"),
        ordenes_consumo_alimento_almacen_dia=("ordenes_consumo_alimento_dia", compact_unique_6a),
        movimientos_stock_resumen_dia=("movimientos_stock_resumen", compact_unique_6a),
        eventos_stock_resumen_dia=("eventos_stock_resumen", compact_unique_6a),
        tipos_movimiento_stock_resumen_dia=("tipos_movimiento_stock_resumen", compact_unique_6a),
    )
    .reset_index()
)

# Pivots por fase
fase_pivot_specs = {
    "stock_cierre_kg": "stock",
    "stock_inicio_dia_kg": "stock_inicio",
    "movimiento_stock_kg_dia": "movimiento_stock",
    "entrada_101_we_kg_dia": "entrada_101_we",
    "consumo_total_almacen_kg_dia": "consumo_total_almacen",
    "traspaso_301_311_kg_dia": "traspaso_301_311",
    "ajuste_wi_kg_dia": "ajuste_wi",
    "logistico_wl_kg_dia": "logistico_wl",
}

stock_wide = stock_daily_total.copy()

for value_col, prefix in fase_pivot_specs.items():
    temp_pivot = stock_diario_alimento_1100_largo.pivot_table(
        index=["fecha", "centro", "almacen"],
        columns="fase_alimento",
        values=value_col,
        aggfunc="sum",
        fill_value=0.0,
    ).reset_index()

    rename_cols = {}

    for col in temp_pivot.columns:
        if col in ["fecha", "centro", "almacen"]:
            continue

        rename_cols[col] = f"{prefix}_{normalize_label_6a(col)}_kg"

    temp_pivot = temp_pivot.rename(columns=rename_cols)

    stock_wide = stock_wide.merge(
        temp_pivot,
        on=["fecha", "centro", "almacen"],
        how="left",
    )

stock_diario_alimento_1100 = stock_wide.copy()

# ------------------------------------------------------------
# 6.1 Salida global independiente del almacén 1100
# ------------------------------------------------------------
# Esta tabla NO está recortada por un ciclo. Es la fuente que debe usar la
# vista global del dashboard para conservar movimientos anteriores al inicio
# biológico de las aves, por ejemplo una entrada 101 WE de alimento.

linea_diaria_stock_alimento = stock_diario_alimento_1100.copy()
linea_diaria_stock_alimento = linea_diaria_stock_alimento.sort_values(
    ["fecha", "centro", "almacen"]
).reset_index(drop=True)

# Alias explícitos para compatibilidad con dashboards/notebooks posteriores.
stock_alimento_diario = linea_diaria_stock_alimento
linea_diaria_almacen_alimento = linea_diaria_stock_alimento
almacen_alimento_diario = linea_diaria_stock_alimento

# ------------------------------------------------------------
# 6.2 Inicio operativo de alimento por ciclo
# ------------------------------------------------------------
# Para cada ciclo se identifica la primera entrada 101 WE de alimento después
# del cierre anterior y antes del inicio de aves. Si no existe una entrada
# previa, se toma la primera posterior dentro del rango del ciclo.

inicios_operativos_records = []

cycles_sorted_6a = cycles_scope.copy()
cycles_sorted_6a["fecha_inicio_ciclo"] = pd.to_datetime(
    cycles_sorted_6a["fecha_inicio_ciclo"],
    errors="coerce",
)
cycles_sorted_6a["fecha_fin_ciclo"] = pd.to_datetime(
    cycles_sorted_6a.get("fecha_fin_ciclo", pd.NaT),
    errors="coerce",
)
cycles_sorted_6a["fecha_corte_analisis"] = pd.to_datetime(
    cycles_sorted_6a["fecha_corte_analisis"],
    errors="coerce",
)

entradas_101_we_daily_6a = (
    movimientos_alimento_1100_stock.loc[
        movimientos_alimento_1100_stock.get(
            "es_entrada_101_we",
            pd.Series(False, index=movimientos_alimento_1100_stock.index),
        ).fillna(False)
    ]
    .groupby("fecha", as_index=False)
    .agg(
        entrada_inicial_alimento_kg=("cantidad_kg_abs", "sum"),
        materiales_entrada_inicial=("material", compact_unique_6a),
        documentos_entrada_inicial=("documento_material", compact_unique_6a),
    )
    .sort_values("fecha")
)

for _, cycle_row_6a in cycles_sorted_6a.iterrows():
    cycle_start_6a = cycle_row_6a["fecha_inicio_ciclo"]
    cycle_cut_6a = cycle_row_6a["fecha_corte_analisis"]

    previous_closed_6a = cycles_sorted_6a.loc[
        cycles_sorted_6a["fecha_fin_ciclo"].notna()
        & cycles_sorted_6a["fecha_fin_ciclo"].lt(cycle_start_6a),
        "fecha_fin_ciclo",
    ]
    previous_end_6a = (
        previous_closed_6a.max()
        if not previous_closed_6a.empty
        else pd.NaT
    )

    candidate_before_6a = entradas_101_we_daily_6a.loc[
        entradas_101_we_daily_6a["fecha"].le(cycle_start_6a)
    ].copy()

    if pd.notna(previous_end_6a):
        candidate_before_6a = candidate_before_6a.loc[
            candidate_before_6a["fecha"].gt(previous_end_6a)
        ]

    if not candidate_before_6a.empty:
        # Primera entrada después del cierre anterior.
        selected_entry_6a = candidate_before_6a.sort_values("fecha").iloc[0]
    else:
        candidate_after_6a = entradas_101_we_daily_6a.loc[
            entradas_101_we_daily_6a["fecha"].ge(cycle_start_6a)
            & entradas_101_we_daily_6a["fecha"].le(cycle_cut_6a)
        ].copy()

        selected_entry_6a = (
            candidate_after_6a.sort_values("fecha").iloc[0]
            if not candidate_after_6a.empty
            else None
        )

    inicios_operativos_records.append({
        "cycle_id": cycle_row_6a.get("cycle_id", pd.NA),
        "centro": cycle_row_6a.get("centro", pd.NA),
        "almacen_aves": cycle_row_6a.get("almacen", pd.NA),
        "lote_aves": cycle_row_6a.get("lote", pd.NA),
        "orden_operativa": cycle_row_6a.get("orden_operativa", pd.NA),
        "fecha_inicio_biologico_aves": cycle_start_6a,
        "fecha_cierre_anterior_referencia": previous_end_6a,
        "fecha_inicio_operativo_alimento": (
            selected_entry_6a["fecha"]
            if selected_entry_6a is not None
            else pd.NaT
        ),
        "entrada_inicial_alimento_kg": (
            selected_entry_6a["entrada_inicial_alimento_kg"]
            if selected_entry_6a is not None
            else np.nan
        ),
        "materiales_entrada_inicial": (
            selected_entry_6a["materiales_entrada_inicial"]
            if selected_entry_6a is not None
            else ""
        ),
        "documentos_entrada_inicial": (
            selected_entry_6a["documentos_entrada_inicial"]
            if selected_entry_6a is not None
            else ""
        ),
    })

inicios_operativos_alimento_por_ciclo = pd.DataFrame(
    inicios_operativos_records
)

# ------------------------------------------------------------
# 7. Unir stock reconstruido con línea diaria de ciclos
# ------------------------------------------------------------

linea_diaria_ciclos_con_stock_alimento = linea_diaria_ciclos.copy()

linea_diaria_ciclos_con_stock_alimento["fecha"] = pd.to_datetime(
    linea_diaria_ciclos_con_stock_alimento["fecha"],
    errors="coerce",
)

stock_for_merge = stock_diario_alimento_1100.copy()
stock_for_merge = stock_for_merge.rename(columns={"almacen": "almacen_alimento"})

linea_diaria_ciclos_con_stock_alimento = linea_diaria_ciclos_con_stock_alimento.merge(
    stock_for_merge,
    left_on=["fecha", "centro"],
    right_on=["fecha", "centro"],
    how="left",
)

linea_diaria_ciclos_con_stock_alimento["almacen_alimento"] = (
    linea_diaria_ciclos_con_stock_alimento["almacen_alimento"].fillna(ALIMENTO_ALMACEN)
)

if not inicios_operativos_alimento_por_ciclo.empty:
    linea_diaria_ciclos_con_stock_alimento = (
        linea_diaria_ciclos_con_stock_alimento.merge(
            inicios_operativos_alimento_por_ciclo,
            on=[
                "cycle_id",
                "centro",
                "almacen_aves",
                "lote_aves",
                "orden_operativa",
            ],
            how="left",
        )
    )

numeric_merge_cols = [
    col
    for col in linea_diaria_ciclos_con_stock_alimento.columns
    if (
        col.startswith("stock_")
        or col.startswith("stock_inicio_")
        or col.startswith("movimiento_stock_")
        or col.startswith("entrada_")
        or col.startswith("consumo_total_almacen_")
        or col.startswith("traspaso_")
        or col.startswith("ajuste_wi_")
        or col.startswith("logistico_")
        or col.startswith("merma_551_552_alimento")
        or col in [
            "stock_alimento_total_kg",
            "stock_inicio_alimento_total_kg",
            "movimiento_stock_alimento_total_kg_dia",
            "entrada_stock_alimento_total_kg_dia",
            "salida_stock_alimento_total_kg_dia",
            "entrada_101_we_alimento_total_kg_dia",
            "reversa_102_we_alimento_total_kg_dia",
            "consumo_total_almacen_alimento_kg_dia",
            "reversa_consumo_262_alimento_kg_dia",
            "stock_negativo_fases",
            "stock_cero_o_menor_fases",
        ]
    )
]

for col in numeric_merge_cols:
    linea_diaria_ciclos_con_stock_alimento[col] = safe_num_6a(
        linea_diaria_ciclos_con_stock_alimento[col]
    ).fillna(0.0)

linea_diaria_ciclos_con_stock_alimento["participacion_consumo_orden_vs_almacen_dia"] = np.where(
    linea_diaria_ciclos_con_stock_alimento["consumo_total_almacen_alimento_kg_dia"].gt(0),
    linea_diaria_ciclos_con_stock_alimento["consumo_orden_alimento_kg_dia"]
    / linea_diaria_ciclos_con_stock_alimento["consumo_total_almacen_alimento_kg_dia"],
    np.nan,
)

# ------------------------------------------------------------
# 8. Hitos de stock alimento por ciclo
# ------------------------------------------------------------

hitos_stock_records = []

for cycle_id, group in linea_diaria_ciclos_con_stock_alimento.groupby("cycle_id", dropna=False):
    group = group.sort_values("fecha").copy()

    if group.empty:
        continue

    first = group.iloc[0]
    last = group.iloc[-1]

    stock_cols_fase = [
        col for col in group.columns
        if col.startswith("stock_fase_") and col.endswith("_kg")
    ]

    first_entry_date = pd.NaT
    if "entrada_101_we_alimento_total_kg_dia" in group.columns:
        mask_entry = group["entrada_101_we_alimento_total_kg_dia"].gt(0)
        if mask_entry.any():
            first_entry_date = group.loc[mask_entry, "fecha"].min()

    first_stock_zero_date = pd.NaT
    if "stock_alimento_total_kg" in group.columns:
        mask_zero = group["stock_alimento_total_kg"].le(0)
        if mask_zero.any():
            first_stock_zero_date = group.loc[mask_zero, "fecha"].min()

    record = {
        "cycle_id": cycle_id,
        "centro": first.get("centro", pd.NA),
        "almacen_aves": first.get("almacen_aves", pd.NA),
        "lote_aves": first.get("lote_aves", pd.NA),
        "orden_operativa": first.get("orden_operativa", pd.NA),
        "fecha_inicio_ciclo": first.get("fecha_inicio_ciclo", pd.NaT),
        "fecha_corte_analisis": first.get("fecha_corte_analisis", pd.NaT),
        "estado_ciclo_negocio": first.get("estado_ciclo_negocio", pd.NA),

        "stock_alimento_inicio_ciclo_kg": first.get("stock_alimento_total_kg", np.nan),
        "stock_alimento_fin_corte_kg": last.get("stock_alimento_total_kg", np.nan),
        "stock_alimento_min_ciclo_kg": group["stock_alimento_total_kg"].min()
        if "stock_alimento_total_kg" in group.columns else np.nan,

        "primera_fecha_entrada_alimento_en_ciclo": first_entry_date,
        "primera_fecha_stock_alimento_cero_o_menor": first_stock_zero_date,

        "entrada_101_we_alimento_total_ciclo_kg": group["entrada_101_we_alimento_total_kg_dia"].sum()
        if "entrada_101_we_alimento_total_kg_dia" in group.columns else 0.0,

        "consumo_total_almacen_alimento_ciclo_kg": group["consumo_total_almacen_alimento_kg_dia"].sum()
        if "consumo_total_almacen_alimento_kg_dia" in group.columns else 0.0,

        "consumo_orden_alimento_ciclo_kg": group["consumo_orden_alimento_kg_dia"].sum()
        if "consumo_orden_alimento_kg_dia" in group.columns else 0.0,

        "traspaso_301_311_alimento_ciclo_kg": group["traspaso_301_311_alimento_kg_dia"].sum()
        if "traspaso_301_311_alimento_kg_dia" in group.columns else 0.0,

        "ajuste_wi_alimento_ciclo_kg": group["ajuste_wi_alimento_kg_dia"].sum()
        if "ajuste_wi_alimento_kg_dia" in group.columns else 0.0,

        "logistico_wl_alimento_ciclo_kg": group["logistico_wl_alimento_kg_dia"].sum()
        if "logistico_wl_alimento_kg_dia" in group.columns else 0.0,

        "dias_con_entrada_alimento_101": int(group["entrada_101_we_alimento_total_kg_dia"].gt(0).sum())
        if "entrada_101_we_alimento_total_kg_dia" in group.columns else 0,

        "dias_con_stock_cero_o_menor": int(group["stock_alimento_total_kg"].le(0).sum())
        if "stock_alimento_total_kg" in group.columns else 0,
    }

    for col in stock_cols_fase:
        record[f"{col}_inicio_ciclo"] = first.get(col, np.nan)
        record[f"{col}_fin_corte"] = last.get(col, np.nan)
        record[f"{col}_min_ciclo"] = group[col].min()

    hitos_stock_records.append(record)

hitos_stock_alimento_por_ciclo = pd.DataFrame(hitos_stock_records)

# ------------------------------------------------------------
# 9. Guardar outputs
# ------------------------------------------------------------

save_table(stock_inicial_alimento_mb5b, config.tables_dir / "02A_stock_inicial_alimento_mb5b.csv")
save_table(movimientos_alimento_1100_stock, config.tables_dir / "02A_movimientos_alimento_1100_stock.csv")
save_table(stock_diario_alimento_1100_largo, config.tables_dir / "02A_stock_diario_alimento_1100_largo.csv")
save_table(stock_diario_alimento_1100, config.tables_dir / "02A_stock_diario_alimento_1100.csv")
save_table(linea_diaria_stock_alimento, config.tables_dir / "02A_linea_diaria_stock_alimento_GLOBAL.csv")
save_table(inicios_operativos_alimento_por_ciclo, config.tables_dir / "02A_inicios_operativos_alimento_por_ciclo.csv")
save_table(linea_diaria_ciclos_con_stock_alimento, config.tables_dir / "02A_linea_diaria_ciclos_con_stock_alimento.csv")
save_table(hitos_stock_alimento_por_ciclo, config.tables_dir / "02A_hitos_stock_alimento_por_ciclo.csv")

# ------------------------------------------------------------
# 10. Mostrar resultados
# ------------------------------------------------------------

show_md(
    f"""
## Resultado Celda 6A

Se reconstruyó el stock diario de alimento del almacén **{ALIMENTO_ALMACEN}**.

Tablas generadas:

- `02A_stock_inicial_alimento_mb5b.csv`
- `02A_movimientos_alimento_1100_stock.csv`
- `02A_stock_diario_alimento_1100_largo.csv`
- `02A_stock_diario_alimento_1100.csv`
- `02A_linea_diaria_stock_alimento_GLOBAL.csv`
- `02A_inicios_operativos_alimento_por_ciclo.csv`
- `02A_linea_diaria_ciclos_con_stock_alimento.csv`
- `02A_hitos_stock_alimento_por_ciclo.csv`

Lectura:

- `stock_alimento_total_kg`: stock reconstruido total del almacén 1100.
- `stock_fase_1_kg` a `stock_fase_5_kg`: stock reconstruido por fase.
- `entrada_101_we_alimento_total_kg_dia`: entradas/reestock normales.
- `consumo_total_almacen_alimento_kg_dia`: consumo total de todas las órdenes.
- `consumo_orden_alimento_kg_dia`: consumo de la orden de la caseta/parvada.
- `participacion_consumo_orden_vs_almacen_dia`: qué tanto representa la orden seleccionada del consumo total del almacén ese día.
"""
)

show_md("## Stock inicial de alimento")
display(stock_inicial_alimento_mb5b)

show_md("## Inicios operativos de alimento por ciclo")
display(inicios_operativos_alimento_por_ciclo)

show_md("## Primeros movimientos de alimento detectados en almacén 1100")
display_cols_mov = existing_columns(
    movimientos_alimento_1100_stock,
    [
        "fecha",
        "centro",
        "almacen",
        "material",
        "fase_alimento",
        "lote",
        "orden",
        "clase_movimiento",
        "clase_transaccion_evento",
        "cantidad_kg_signed_sap",
        "cantidad_kg_abs",
        "efecto_stock_kg",
        "tipo_movimiento_stock",
        "documento_material",
    ],
)
display(movimientos_alimento_1100_stock[display_cols_mov].head(80))

show_md("## Stock diario reconstruido de alimento")
display_cols_stock = existing_columns(
    stock_diario_alimento_1100,
    [
        "fecha",
        "centro",
        "almacen",
        "stock_alimento_total_kg",
        "stock_fase_1_kg",
        "stock_fase_2_kg",
        "stock_fase_3_kg",
        "stock_fase_4_kg",
        "stock_fase_5_kg",
        "entrada_101_we_alimento_total_kg_dia",
        "consumo_total_almacen_alimento_kg_dia",
        "traspaso_301_311_alimento_kg_dia",
        "ajuste_wi_alimento_kg_dia",
        "logistico_wl_alimento_kg_dia",
        "movimientos_stock_resumen_dia",
        "ordenes_consumo_alimento_almacen_dia",
    ],
)
display(stock_diario_alimento_1100[display_cols_stock].head(120))

show_md("## Hitos de stock de alimento por ciclo")
display_cols_hitos_stock = existing_columns(
    hitos_stock_alimento_por_ciclo,
    [
        "cycle_id",
        "almacen_aves",
        "lote_aves",
        "orden_operativa",
        "fecha_inicio_ciclo",
        "fecha_corte_analisis",
        "estado_ciclo_negocio",
        "stock_alimento_inicio_ciclo_kg",
        "stock_alimento_fin_corte_kg",
        "stock_alimento_min_ciclo_kg",
        "primera_fecha_entrada_alimento_en_ciclo",
        "primera_fecha_stock_alimento_cero_o_menor",
        "entrada_101_we_alimento_total_ciclo_kg",
        "consumo_total_almacen_alimento_ciclo_kg",
        "consumo_orden_alimento_ciclo_kg",
        "traspaso_301_311_alimento_ciclo_kg",
        "ajuste_wi_alimento_ciclo_kg",
        "logistico_wl_alimento_ciclo_kg",
        "dias_con_entrada_alimento_101",
        "dias_con_stock_cero_o_menor",
        "stock_fase_1_kg_inicio_ciclo",
        "stock_fase_2_kg_inicio_ciclo",
        "stock_fase_3_kg_inicio_ciclo",
        "stock_fase_4_kg_inicio_ciclo",
        "stock_fase_5_kg_inicio_ciclo",
    ],
)
display(hitos_stock_alimento_por_ciclo[display_cols_hitos_stock])

show_md("## Vista previa de línea diaria con stock de alimento")
display_cols_linea_stock = existing_columns(
    linea_diaria_ciclos_con_stock_alimento,
    [
        "fecha",
        "cycle_id",
        "almacen_aves",
        "lote_aves",
        "orden_operativa",
        "edad_semana",
        "saldo_aves_operativo",
        "consumo_orden_alimento_kg_dia",
        "consumo_neto_alimento_kg_dia",
        "fases_alimento_dia",
        "produccion_neta_huevo_kg_dia",
        "ica_acumulado",
        "stock_alimento_total_kg",
        "stock_fase_1_kg",
        "stock_fase_2_kg",
        "stock_fase_3_kg",
        "stock_fase_4_kg",
        "stock_fase_5_kg",
        "entrada_101_we_alimento_total_kg_dia",
        "consumo_total_almacen_alimento_kg_dia",
        "participacion_consumo_orden_vs_almacen_dia",
        "traspaso_301_311_alimento_kg_dia",
        "ajuste_wi_alimento_kg_dia",
        "logistico_wl_alimento_kg_dia",
        "movimientos_stock_resumen_dia",
    ],
)
display(linea_diaria_ciclos_con_stock_alimento[display_cols_linea_stock].head(120))
