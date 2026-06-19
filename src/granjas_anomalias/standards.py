
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .utils import normalize_text


# ============================================================
# Columnas canónicas utilizadas por el proyecto
# ============================================================

REQUIRED_COLUMNS = [
    "semana_edad",
    "mortalidad_pct_acum",
    "produccion_pct_ave_dia",
    "ica_sap",
    "consumo_g_ave_dia",
    "peso_huevo_g",
    "viabilidad_pct",
]


# ============================================================
# Reglas para detectar columnas en el archivo de política
# ============================================================

@dataclass(frozen=True)
class ColumnRule:
    target: str
    exact: tuple[str, ...]
    contains: tuple[str, ...] = ()
    excludes: tuple[str, ...] = ()


COLUMN_RULES: tuple[ColumnRule, ...] = (
    ColumnRule(
        target="semana_edad",
        exact=(
            "semana_edad",
            "edad_semana",
            "semana",
        ),
        contains=(
            "semana_edad",
            "edad_semana",
        ),
    ),
    ColumnRule(
        target="peso_corporal_g",
        exact=(
            "peso_corporal",
            "peso_corporal_g",
            "peso_corporal_gramos",
            "peso_corporal_kg",
        ),
        contains=(
            "peso_corporal",
        ),
    ),
    ColumnRule(
        target="mortalidad_pct_acum",
        exact=(
            "mort",
            "mortalidad",
            "mortalidad_pct",
            "mortalidad_acum",
            "mortalidad_pct_acum",
        ),
        contains=(
            "mortalidad",
            "mort",
        ),
    ),
    ColumnRule(
        target="produccion_pct_ave_dia",
        exact=(
            "produccion_ave_dia",
            "produccion_pct_ave_dia",
            "porcentaje_produccion",
            "produccion_pct",
            "produccion",
        ),
        contains=(
            "produccion_ave_dia",
            "porcentaje_produccion",
        ),
        excludes=(
            "kg",
            "peso",
        ),
    ),
    ColumnRule(
        target="ica_sap",
        exact=(
            "ica",
            "ica_sap",
            "conv",
            "conversion",
        ),
        contains=(
            "ica",
            "conversion",
        ),
        excludes=(
            "calculado",
            "principal",
            "brecha",
        ),
    ),
    ColumnRule(
        target="consumo_g_ave_dia",
        exact=(
            "consumo_de_alimento_ave_dia",
            "consumo_alimento_ave_dia",
            "consumo_ave_dia",
            "consumo_g_ave_dia",
            "consumo_kg_ave_dia",
            "consumo",
        ),
        contains=(
            "consumo_de_alimento_ave_dia",
            "consumo_ave_dia",
        ),
        excludes=(
            "total",
            "semanal",
            "estandar_kg",
        ),
    ),
    ColumnRule(
        target="peso_huevo_g",
        exact=(
            "peso_promedio_huevo_gramos",
            "peso_promedio_huevo_g",
            "peso_huevo_gramos",
            "peso_huevo_g",
            "peso_huevo_kg",
            "peso_huevo",
        ),
        contains=(
            "peso_promedio_huevo",
            "peso_huevo",
        ),
    ),
    ColumnRule(
        target="viabilidad_pct",
        exact=(
            "viabilidad",
            "viabilidad_pct",
        ),
        contains=(
            "viabilidad",
        ),
    ),
)


# ============================================================
# Helpers internos
# ============================================================

def _pick_column(
    normalized_to_original: dict[str, str],
    rule: ColumnRule,
) -> str | None:
    """
    Busca la columna original que corresponde a una columna canónica.

    Primero intenta coincidencias exactas y después coincidencias parciales.
    """

    for candidate in rule.exact:
        if candidate in normalized_to_original:
            return normalized_to_original[candidate]

    for normalized, original in normalized_to_original.items():
        if rule.excludes and any(
            token in normalized
            for token in rule.excludes
        ):
            continue

        if any(
            token in normalized
            for token in rule.contains
        ):
            return original

    return None


def _to_numeric(series: pd.Series) -> pd.Series:
    """
    Convierte una serie a numérico.

    Soporta valores con:
    - porcentaje;
    - comas;
    - espacios;
    - valores almacenados como texto.
    """

    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")

    cleaned = (
        series.astype("string")
        .str.strip()
        .str.replace("%", "", regex=False)
        .str.replace(",", "", regex=False)
    )

    return pd.to_numeric(cleaned, errors="coerce")


def _has_percent_hint(original_header: str) -> bool:
    """
    Determina si el encabezado indica explícitamente porcentaje.
    """

    normalized = normalize_text(original_header)

    return (
        "%" in str(original_header)
        or "pct" in normalized
        or "porcentaje" in normalized
        or "percent" in normalized
    )


def _normalize_percent(
    series: pd.Series,
    original_header: str,
    *,
    metric: str,
) -> tuple[pd.Series, str]:
    """
    Normaliza una variable porcentual a escala 0-100.

    La inferencia depende del indicador porque valores como 1.0
    son ambiguos:

    - Producción:
        0.90 se interpreta como 90 %.
    - Viabilidad:
        0.99 se interpreta como 99 %.
    - Mortalidad:
        0.01 se interpreta como 1 %.
        1.00 se conserva como 1 %, no se convierte a 100 %.

    Parameters
    ----------
    series:
        Valores originales de la política.
    original_header:
        Nombre original de la columna.
    metric:
        Indicador que se está normalizando:
        ``production``, ``mortality`` o ``viability``.

    Returns
    -------
    tuple[pd.Series, str]
        Serie normalizada y descripción de la regla aplicada.
    """

    values = _to_numeric(series)
    finite = values.dropna().abs()

    if finite.empty:
        return values, "sin_datos"

    if _has_percent_hint(original_header):
        return values, "porcentaje_explicito"

    q95 = float(finite.quantile(0.95))
    maximum = float(finite.max())

    if metric == "mortality":
        # En políticas avícolas una mortalidad de 1.0 normalmente
        # representa 1 %, no una fracción equivalente a 100 %.
        #
        # Solo valores claramente fraccionarios, por ejemplo 0.01,
        # se convierten a porcentaje.
        if maximum <= 0.20:
            return (
                values * 100.0,
                "fraccion_a_porcentaje_mortalidad",
            )

        return (
            values,
            "porcentaje_inferido_mortalidad",
        )

    if metric in {"production", "viability"}:
        if q95 <= 1.5:
            return (
                values * 100.0,
                f"fraccion_a_porcentaje_{metric}",
            )

        return (
            values,
            f"porcentaje_inferido_{metric}",
        )

    raise ValueError(
        "metric debe ser 'production', "
        "'mortality' o 'viability'. "
        f"Valor recibido: {metric!r}"
    )


def _normalize_mass_to_grams(
    series: pd.Series,
    original_header: str,
    kind: str,
) -> tuple[pd.Series, str]:
    """
    Normaliza pesos y consumos a gramos.

    kind puede ser:
    - consumo;
    - peso_huevo;
    - peso_corporal.
    """

    values = _to_numeric(series)
    normalized_header = normalize_text(original_header)
    finite = values.dropna().abs()

    if "kg" in normalized_header:
        return values * 1000.0, "kg_a_g_por_encabezado"

    if any(
        token in normalized_header
        for token in ("gramo", "gramos", "_g")
    ):
        return values, "gramos_explicitos"

    if finite.empty:
        return values, "sin_datos"

    median = float(finite.median())

    # Inferencias conservadoras cuando el encabezado no declara la unidad.
    if kind == "peso_corporal" and median < 20:
        return (
            values * 1000.0,
            "kg_a_g_inferido_peso_corporal",
        )

    if kind == "peso_huevo" and median < 1:
        return (
            values * 1000.0,
            "kg_a_g_inferido_peso_huevo",
        )

    if kind == "consumo" and median < 1:
        return (
            values * 1000.0,
            "kg_a_g_inferido_consumo",
        )

    return values, "gramos_inferidos"


def _build_quality_row(
    level: str,
    code: str,
    message: str,
    affected: int = 0,
) -> dict[str, object]:
    """
    Crea una fila estandarizada para el reporte de calidad.
    """

    return {
        "nivel": level,
        "codigo": code,
        "mensaje": message,
        "filas_afectadas": int(affected),
    }


# ============================================================
# Validación de política normalizada
# ============================================================

def validate_standard(
    standard: pd.DataFrame,
) -> pd.DataFrame:
    """
    Valida la política ya normalizada.

    Devuelve un DataFrame auditable con errores, advertencias o estado OK.
    """

    rows: list[dict[str, object]] = []

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in standard.columns
    ]

    if missing:
        rows.append(
            _build_quality_row(
                level="ERROR",
                code="COLUMNAS_FALTANTES",
                message=(
                    f"Faltan columnas requeridas: {missing}"
                ),
                affected=len(missing),
            )
        )

        return pd.DataFrame(rows)

    duplicated = int(
        standard["semana_edad"]
        .duplicated()
        .sum()
    )

    if duplicated:
        rows.append(
            _build_quality_row(
                level="ERROR",
                code="SEMANAS_DUPLICADAS",
                message=(
                    "La política normalizada conserva "
                    "semanas duplicadas."
                ),
                affected=duplicated,
            )
        )

    invalid_week = (
        standard["semana_edad"].isna()
        | standard["semana_edad"].lt(0)
    )

    if invalid_week.any():
        rows.append(
            _build_quality_row(
                level="ERROR",
                code="SEMANA_INVALIDA",
                message=(
                    "Existen semanas de edad nulas "
                    "o negativas."
                ),
                affected=int(invalid_week.sum()),
            )
        )

    percentage_columns = (
        "produccion_pct_ave_dia",
        "mortalidad_pct_acum",
        "viabilidad_pct",
    )

    for column in percentage_columns:
        invalid = (
            standard[column].notna()
            & ~standard[column].between(0, 100)
        )

        if invalid.any():
            rows.append(
                _build_quality_row(
                    level="ERROR",
                    code=f"RANGO_{column.upper()}",
                    message=(
                        f"{column} debe estar entre 0 y 100."
                    ),
                    affected=int(invalid.sum()),
                )
            )

    non_negative_columns = (
        "consumo_g_ave_dia",
        "peso_huevo_g",
        "ica_estandar_principal",
    )

    for column in non_negative_columns:
        invalid = (
            standard[column].notna()
            & standard[column].lt(0)
        )

        if invalid.any():
            rows.append(
                _build_quality_row(
                    level="ERROR",
                    code=f"NEGATIVO_{column.upper()}",
                    message=f"{column} no puede ser negativo.",
                    affected=int(invalid.sum()),
                )
            )

    missing_ica = (
        standard["ica_estandar_principal"]
        .isna()
    )

    if missing_ica.any():
        rows.append(
            _build_quality_row(
                level="WARNING",
                code="ICA_NO_DISPONIBLE",
                message=(
                    "Hay semanas sin ICA oficial "
                    "ni ICA calculable."
                ),
                affected=int(missing_ica.sum()),
            )
        )

    viability_check = (
        standard["mortalidad_pct_acum"]
        + standard["viabilidad_pct"]
    )

    inconsistent = (
        viability_check.notna()
        & viability_check.sub(100).abs().gt(2.0)
    )

    if inconsistent.any():
        rows.append(
            _build_quality_row(
                level="WARNING",
                code="MORTALIDAD_VIABILIDAD",
                message=(
                    "Mortalidad acumulada + viabilidad "
                    "difiere de 100 en más de 2 puntos."
                ),
                affected=int(inconsistent.sum()),
            )
        )

    if not rows:
        rows.append(
            _build_quality_row(
                level="OK",
                code="POLITICA_VALIDA",
                message=(
                    "La política normalizada pasó "
                    "las validaciones definidas."
                ),
                affected=0,
            )
        )

    return pd.DataFrame(rows)


# ============================================================
# Preparación principal de la política
# ============================================================

def prepare_standard(
    raw: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normaliza la política productiva y calcula métricas derivadas.

    Salidas principales:
    - semana de edad;
    - consumo en g/ave/día;
    - producción en porcentaje;
    - peso de huevo en gramos;
    - mortalidad acumulada;
    - viabilidad;
    - ICA oficial SAP;
    - ICA calculado;
    - métricas diarias y semanales para 1000 aves.

    La auditoría de unidades y calidad se almacena en:
    - standard.attrs["unit_audit"]
    - standard.attrs["quality_report"]
    - standard.attrs["source_columns"]
    """

    if not isinstance(raw, pd.DataFrame):
        raise TypeError(
            "raw debe ser un pandas.DataFrame"
        )

    if raw.empty:
        raise ValueError(
            "La política está vacía."
        )

    original_columns = [
        str(column)
        for column in raw.columns
    ]

    normalized_to_original: dict[str, str] = {}

    for original in original_columns:
        normalized = normalize_text(original)

        normalized_to_original.setdefault(
            normalized,
            original,
        )

    source_columns: dict[str, str] = {}

    for rule in COLUMN_RULES:
        source = _pick_column(
            normalized_to_original,
            rule,
        )

        if source is not None:
            source_columns[rule.target] = source

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in source_columns
    ]

    if missing:
        raise ValueError(
            "Faltan columnas de política después de normalizar: "
            f"{missing}. "
            f"Columnas recibidas: {original_columns}"
        )

    standard = pd.DataFrame(
        index=raw.index
    )

    unit_audit: list[dict[str, str]] = []

    standard["semana_edad"] = _to_numeric(
        raw[source_columns["semana_edad"]]
    )

    standard["ica_sap"] = _to_numeric(
        raw[source_columns["ica_sap"]]
    )

    # --------------------------------------------------------
    # Producción
    # --------------------------------------------------------

    production, production_rule = _normalize_percent(
    raw[source_columns["produccion_pct_ave_dia"]],
    source_columns["produccion_pct_ave_dia"],
    metric="production",
)

    standard["produccion_pct_ave_dia"] = production

    unit_audit.append({
        "columna": "produccion_pct_ave_dia",
        "origen": source_columns[
            "produccion_pct_ave_dia"
        ],
        "regla": production_rule,
    })

    # --------------------------------------------------------
    # Mortalidad
    # --------------------------------------------------------

    mortality, mortality_rule = _normalize_percent(
        raw[source_columns["mortalidad_pct_acum"]],
        source_columns["mortalidad_pct_acum"],
        metric="mortality",
    )

    standard["mortalidad_pct_acum"] = mortality

    unit_audit.append({
        "columna": "mortalidad_pct_acum",
        "origen": source_columns[
            "mortalidad_pct_acum"
        ],
        "regla": mortality_rule,
    })

    # --------------------------------------------------------
    # Viabilidad
    # --------------------------------------------------------

    viability, viability_rule = _normalize_percent(
        raw[source_columns["viabilidad_pct"]],
        source_columns["viabilidad_pct"],
        metric="viability",
    )

    standard["viabilidad_pct"] = viability

    unit_audit.append({
        "columna": "viabilidad_pct",
        "origen": source_columns[
            "viabilidad_pct"
        ],
        "regla": viability_rule,
    })

    # --------------------------------------------------------
    # Consumo
    # --------------------------------------------------------

    consumption, consumption_rule = (
        _normalize_mass_to_grams(
            raw[source_columns["consumo_g_ave_dia"]],
            source_columns["consumo_g_ave_dia"],
            kind="consumo",
        )
    )

    standard["consumo_g_ave_dia"] = consumption

    unit_audit.append({
        "columna": "consumo_g_ave_dia",
        "origen": source_columns[
            "consumo_g_ave_dia"
        ],
        "regla": consumption_rule,
    })

    # --------------------------------------------------------
    # Peso del huevo
    # --------------------------------------------------------

    egg_weight, egg_weight_rule = (
        _normalize_mass_to_grams(
            raw[source_columns["peso_huevo_g"]],
            source_columns["peso_huevo_g"],
            kind="peso_huevo",
        )
    )

    standard["peso_huevo_g"] = egg_weight

    unit_audit.append({
        "columna": "peso_huevo_g",
        "origen": source_columns[
            "peso_huevo_g"
        ],
        "regla": egg_weight_rule,
    })

    # --------------------------------------------------------
    # Peso corporal opcional
    # --------------------------------------------------------

    if "peso_corporal_g" in source_columns:
        body_weight, body_weight_rule = (
            _normalize_mass_to_grams(
                raw[source_columns["peso_corporal_g"]],
                source_columns["peso_corporal_g"],
                kind="peso_corporal",
            )
        )

        standard["peso_corporal_g"] = body_weight

        unit_audit.append({
            "columna": "peso_corporal_g",
            "origen": source_columns[
                "peso_corporal_g"
            ],
            "regla": body_weight_rule,
        })

    else:
        standard["peso_corporal_g"] = np.nan

    # --------------------------------------------------------
    # Limpieza de semanas
    # --------------------------------------------------------

    standard = (
        standard
        .dropna(subset=["semana_edad"])
        .copy()
    )

    if standard.empty:
        raise ValueError(
            "No quedaron semanas de edad válidas "
            "después de normalizar."
        )

    standard["semana_edad"] = (
        standard["semana_edad"]
        .round()
        .astype(int)
    )

    standard["registros_fuente_semana"] = 1

    # Si existen varias filas por semana, se promedian.
    numeric_columns = [
        column
        for column in standard.columns
        if column not in {
            "semana_edad",
            "registros_fuente_semana",
        }
    ]

    aggregation: dict[str, str] = {
        column: "mean"
        for column in numeric_columns
    }

    aggregation["registros_fuente_semana"] = "sum"

    standard = (
        standard
        .groupby(
            "semana_edad",
            as_index=False,
        )
        .agg(aggregation)
        .sort_values("semana_edad")
        .reset_index(drop=True)
    )

    # ========================================================
    # Métricas derivadas de política
    # ========================================================

    standard["produccion_fraccion"] = (
        standard["produccion_pct_ave_dia"]
        / 100.0
    )

    standard["mortalidad_fraccion_acum"] = (
        standard["mortalidad_pct_acum"]
        / 100.0
    )

    standard["viabilidad_fraccion"] = (
        standard["viabilidad_pct"]
        / 100.0
    )

    # Huevos producidos por cada 1000 aves al día.
    standard["huevos_1000_aves_dia"] = (
        1000.0
        * standard["produccion_fraccion"]
    )

    # Producción kg por 1000 aves al día.
    standard["produccion_kg_1000_aves_dia"] = (
        standard["huevos_1000_aves_dia"]
        * standard["peso_huevo_g"]
        / 1000.0
    )

    # Producción kg por 1000 aves por semana.
    standard["produccion_kg_1000_aves_semana"] = (
        7.0
        * standard["produccion_kg_1000_aves_dia"]
    )

    # Para 1000 aves:
    # g/ave/día y kg/1000 aves/día
    # tienen el mismo valor numérico.
    standard["consumo_kg_1000_aves_dia"] = (
        standard["consumo_g_ave_dia"]
    )

    standard["consumo_kg_1000_aves_semana"] = (
        7.0
        * standard["consumo_kg_1000_aves_dia"]
    )

    standard["mortalidad_aves_1000_acum"] = (
        1000.0
        * standard["mortalidad_fraccion_acum"]
    )

    standard["aves_viables_1000"] = (
        1000.0
        * standard["viabilidad_fraccion"]
    )

    # --------------------------------------------------------
    # ICA calculado desde política
    # --------------------------------------------------------

    standard["ica_calculado_politica"] = np.where(
        standard[
            "produccion_kg_1000_aves_dia"
        ].gt(0),
        (
            standard["consumo_kg_1000_aves_dia"]
            / standard[
                "produccion_kg_1000_aves_dia"
            ]
        ),
        np.nan,
    )

    # El ICA oficial SAP tiene prioridad.
    official_ica = (
        standard["ica_sap"]
        .where(
            standard["ica_sap"].gt(0)
        )
    )

    standard["ica_estandar_principal"] = (
        official_ica.fillna(
            standard["ica_calculado_politica"]
        )
    )

    # --------------------------------------------------------
    # Control entre ICA SAP e ICA calculado
    # --------------------------------------------------------

    standard["ica_diferencia_control"] = (
        standard["ica_sap"]
        - standard["ica_calculado_politica"]
    )

    standard["ica_diferencia_control_pct"] = np.where(
        standard[
            "ica_calculado_politica"
        ].abs().gt(1e-12),
        (
            100.0
            * standard["ica_diferencia_control"]
            / standard["ica_calculado_politica"]
        ),
        np.nan,
    )

    # ========================================================
    # Auditoría
    # ========================================================

    quality_report = validate_standard(
        standard
    )

    standard.attrs["unit_audit"] = (
        pd.DataFrame(unit_audit)
    )

    standard.attrs["quality_report"] = (
        quality_report
    )

    standard.attrs["source_columns"] = (
        source_columns
    )

    return standard

