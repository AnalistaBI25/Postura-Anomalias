from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from .config import ProjectConfig


DEFAULT_PHASES = [
    "Fase 1",
    "Fase 2",
    "Fase 3",
    "Fase 4",
    "Fase 5",
]

TRANSITION_PHASE = "Transición / sin desglose"


def _missing(value: Any) -> bool:
    """Indica si un valor debe tratarse como vacío."""

    if value is None:
        return True

    if isinstance(value, (dict, list, tuple, set)):
        return False

    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False

    if isinstance(result, (bool, np.bool_)):
        return bool(result)

    return False


def _text(value: Any, default: str = "-") -> str:
    """Convierte valores de pandas y numpy en texto limpio."""

    if _missing(value):
        return default

    if isinstance(value, (int, np.integer)):
        return str(int(value))

    if isinstance(value, (float, np.floating)):
        number = float(value)

        if np.isfinite(number) and number.is_integer():
            return str(int(number))

    text = str(value).strip()

    if text.lower() in {
        "",
        "nan",
        "none",
        "nat",
        "<na>",
    }:
        return default

    return text


def _number(
    value: Any,
    default: float | None = None,
) -> float | None:
    """Convierte un valor en un número compatible con JSON."""

    if _missing(value):
        return default

    try:
        number = float(value)
    except (TypeError, ValueError):
        return default

    if not np.isfinite(number):
        return default

    return number


def _integer(
    value: Any,
    default: int = 0,
) -> int:
    """Convierte un valor numérico en entero."""

    number = _number(value)

    if number is None:
        return default

    return int(round(number))


def _boolean(value: Any) -> bool:
    """Normaliza valores booleanos provenientes de pandas o CSV."""

    if _missing(value):
        return False

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {
            "1",
            "true",
            "sí",
            "si",
            "yes",
            "y",
        }:
            return True

        if normalized in {
            "0",
            "false",
            "no",
            "n",
        }:
            return False

    return bool(value)


def _date_iso(value: Any) -> str | None:
    """Convierte una fecha al formato YYYY-MM-DD."""

    timestamp = pd.to_datetime(
        value,
        errors="coerce",
    )

    if pd.isna(timestamp):
        return None

    return pd.Timestamp(
        timestamp
    ).strftime("%Y-%m-%d")


def _date_label(value: Any) -> str:
    """Convierte una fecha en una etiqueta DD/MM/YYYY."""

    timestamp = pd.to_datetime(
        value,
        errors="coerce",
    )

    if pd.isna(timestamp):
        return "-"

    return pd.Timestamp(
        timestamp
    ).strftime("%d/%m/%Y")


def _first(
    row: pd.Series,
    *columns: str,
    default: Any = None,
) -> Any:
    """Obtiene el primer valor no vacío entre varias columnas."""

    for column in columns:
        if column not in row.index:
            continue

        value = row[column]

        if not _missing(value):
            return value

    return default


def _json_clean(value: Any) -> Any:
    """Limpia valores incompatibles con json.dumps."""

    if isinstance(value, dict):
        return {
            str(key): _json_clean(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            _json_clean(item)
            for item in value
        ]

    if isinstance(
        value,
        (pd.Timestamp, datetime),
    ):
        return value.isoformat()

    if isinstance(value, np.bool_):
        return bool(value)

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(
        value,
        (float, np.floating),
    ):
        number = float(value)

        if np.isfinite(number):
            return number

        return None

    if _missing(value):
        return None

    return value


def _prepare_stock(
    stock_global: pd.DataFrame,
) -> pd.DataFrame:
    """
    Prepara el stock global para unirlo por fecha.

    El stock se mantiene como inventario del almacén
    compartido y no se distribuye entre casetas.
    """

    if stock_global.empty:
        return pd.DataFrame(
            columns=["fecha"]
        )

    column_mapping = {
        "fecha": "fecha",
        "stock_global_kg": "stock",
        "stock_apertura_global_kg": "stock_apertura",
        "entradas_netas_kg": "entrada_alimento",
        "otros_movimientos_stock_kg": "otros_movimientos_stock",
        "diferencia_conciliacion_kg": "diferencia_conciliacion_stock",
        "movimientos_sap": "stock_movimientos_sap",
        "eventos_sap": "stock_eventos_sap",
        "roles_sap": "stock_roles_sap",
        "documentos_sap": "stock_documentos_sap",
    }

    available_columns = [
        column
        for column in column_mapping
        if column in stock_global.columns
    ]

    if "fecha" not in available_columns:
        raise ValueError(
            "stock_global no contiene "
            "la columna 'fecha'."
        )

    stock = stock_global[
        available_columns
    ].copy()

    stock = stock.rename(
        columns=column_mapping
    )

    stock["fecha"] = pd.to_datetime(
        stock["fecha"],
        errors="coerce",
    ).dt.normalize()

    stock = stock.dropna(
        subset=["fecha"]
    )

    stock = stock.sort_values(
        "fecha"
    )

    stock = stock.drop_duplicates(
        subset=["fecha"],
        keep="last",
    )

    return stock.reset_index(
        drop=True
    )


def _prepare_scores(
    scored: pd.DataFrame,
) -> pd.DataFrame:
    """Prepara resultados del modelo y reglas de anomalías."""

    required_columns = {
        "cycle_id",
        "fecha",
    }

    if (
        scored.empty
        or not required_columns.issubset(
            scored.columns
        )
    ):
        return pd.DataFrame(
            columns=[
                "cycle_id",
                "fecha",
            ]
        )

    wanted_columns = [
        "cycle_id",
        "fecha",
        "score_anomalia",
        "severidad",
        "es_anomalia",
        "motivo_anomalia",
    ]

    available_columns = [
        column
        for column in wanted_columns
        if column in scored.columns
    ]

    result = scored[
        available_columns
    ].copy()

    result["cycle_id"] = result[
        "cycle_id"
    ].map(_text)

    result["fecha"] = pd.to_datetime(
        result["fecha"],
        errors="coerce",
    ).dt.normalize()

    result = result.dropna(
        subset=["fecha"]
    )

    result = result.drop_duplicates(
        subset=[
            "cycle_id",
            "fecha",
        ],
        keep="last",
    )

    return result.reset_index(
        drop=True
    )


def _compact_unique(
    values: pd.Series,
) -> str:
    """Une valores únicos conservando el orden."""

    result: list[str] = []

    for value in values:
        text = _text(
            value,
            "",
        )

        if text and text not in result:
            result.append(text)

    return ", ".join(result)


def _empty_movement_frame() -> pd.DataFrame:
    """Devuelve la estructura vacía de movimientos diarios."""

    return pd.DataFrame(
        columns=[
            "fecha",
            "entrada_alimento_detalle",
            "traspasos_internos",
            "ajustes_511_512",
            "ajustes_inventario",
            "traslados_641_643",
            "movimientos_logisticos",
            "mermas_551_552",
            "movimientos_resumen",
            "movimientos_adicionales",
            "movimientos_operativos",
            "documentos_sap",
        ]
    )


def _prepare_kardex_movements(
    kardex: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    """
    Separa por fecha los movimientos SAP del alimento.

    Los movimientos pertenecen al almacén compartido.
    No se asignan artificialmente a una caseta.
    """

    if kardex.empty:
        return _empty_movement_frame()

    required_columns = {
        "fecha",
        "centro",
        "almacen",
        "material",
        "rol_movimiento",
        "clase_movimiento",
        "clase_transaccion_evento",
        "movimiento_stock_alimento_kg",
    }

    missing_columns = (
        required_columns.difference(
            kardex.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "Faltan columnas en el Kardex "
            "para construir los movimientos "
            "del dashboard: "
            f"{sorted(missing_columns)}"
        )

    frame = kardex.copy()

    frame["fecha"] = pd.to_datetime(
        frame["fecha"],
        errors="coerce",
    ).dt.normalize()

    frame = frame.dropna(
        subset=["fecha"]
    )

    text_columns = [
        "centro",
        "almacen",
        "material",
        "rol_movimiento",
        "clase_movimiento",
        "clase_transaccion_evento",
    ]

    for column in text_columns:
        frame[column] = frame[
            column
        ].map(
            lambda value: _text(
                value,
                "",
            )
        )

    frame[
        "movimiento_stock_alimento_kg"
    ] = pd.to_numeric(
        frame[
            "movimiento_stock_alimento_kg"
        ],
        errors="coerce",
    ).fillna(0.0)

    center = _text(
        config.project.get(
            "center_id"
        ),
        "",
    )

    warehouse = _text(
        config.sap.get(
            "feed_warehouse"
        ),
        "",
    )

    feed_materials = {
        _text(material, "")
        for material in config.sap.get(
            "feed_materials",
            {},
        ).keys()
    }

    frame = frame.loc[
        frame["centro"].eq(center)
        & frame["almacen"].eq(
            warehouse
        )
        & frame["material"].isin(
            feed_materials
        )
    ].copy()

    if frame.empty:
        return _empty_movement_frame()

    role = frame[
        "rol_movimiento"
    ]

    signed_quantity = frame[
        "movimiento_stock_alimento_kg"
    ]

    frame[
        "entrada_alimento_detalle"
    ] = np.where(
        role.isin(
            [
                "ALIMENTO_ENTRADA",
                "ALIMENTO_ENTRADA_REVERSA",
            ]
        ),
        signed_quantity,
        0.0,
    )

    frame[
        "traspasos_internos"
    ] = np.where(
        role.eq(
            "ALIMENTO_TRASPASO"
        ),
        signed_quantity,
        0.0,
    )

    frame[
        "ajustes_511_512"
    ] = np.where(
        role.eq(
            "ALIMENTO_AJUSTE"
        ),
        signed_quantity,
        0.0,
    )

    frame[
        "ajustes_inventario"
    ] = np.where(
        role.eq(
            "ALIMENTO_DIF_INVENTARIO"
        ),
        signed_quantity,
        0.0,
    )

    frame[
        "traslados_641_643"
    ] = np.where(
        role.eq(
            "ALIMENTO_LOGISTICA"
        ),
        signed_quantity,
        0.0,
    )

    # Se conserva por compatibilidad con el HTML.
    # No se duplica el valor de traslados_641_643.
    frame[
        "movimientos_logisticos"
    ] = 0.0

    frame[
        "mermas_551_552"
    ] = np.where(
        role.eq(
            "ALIMENTO_MERMA"
        ),
        signed_quantity,
        0.0,
    )

    frame[
        "movimiento_codigo_evento"
    ] = (
        frame[
            "clase_movimiento"
        ]
        + " "
        + frame[
            "clase_transaccion_evento"
        ]
    ).str.strip()

    numeric_columns = [
        "entrada_alimento_detalle",
        "traspasos_internos",
        "ajustes_511_512",
        "ajustes_inventario",
        "traslados_641_643",
        "movimientos_logisticos",
        "mermas_551_552",
    ]

    numeric = (
        frame.groupby(
            "fecha",
            as_index=False,
        )[numeric_columns]
        .sum()
    )

    document_column = next(
        (
            column
            for column in [
                "documento_material",
                "documento",
                "numero_documento",
            ]
            if column in frame.columns
        ),
        None,
    )

    aggregations: dict[
        str,
        pd.NamedAgg,
    ] = {
        "movimientos_resumen": pd.NamedAgg(
            column=(
                "movimiento_codigo_evento"
            ),
            aggfunc=_compact_unique,
        ),
        "movimientos_adicionales": pd.NamedAgg(
            column="rol_movimiento",
            aggfunc=_compact_unique,
        ),
        "movimientos_operativos": pd.NamedAgg(
            column="material",
            aggfunc=_compact_unique,
        ),
    }

    if document_column is not None:
        aggregations[
            "documentos_sap"
        ] = pd.NamedAgg(
            column=document_column,
            aggfunc=_compact_unique,
        )

    metadata = (
        frame.groupby(
            "fecha",
            as_index=False,
        )
        .agg(**aggregations)
    )

    if (
        "documentos_sap"
        not in metadata.columns
    ):
        metadata[
            "documentos_sap"
        ] = ""

    result = numeric.merge(
        metadata,
        on="fecha",
        how="left",
        validate="one_to_one",
    )

    return (
        result.sort_values("fecha")
        .reset_index(drop=True)
    )


def _last_valid(
    values: pd.Series,
) -> float | None:
    """Devuelve el último número válido de una serie."""

    numeric = pd.to_numeric(
        values,
        errors="coerce",
    ).dropna()

    if numeric.empty:
        return None

    return float(
        numeric.iloc[-1]
    )


def _caseta_sort_key(
    value: str,
) -> tuple[int, Any]:
    """Ordena identificadores numéricos antes que texto."""

    try:
        return 0, int(value)
    except ValueError:
        return 1, value


def _build_shared_store(
    daily: pd.DataFrame,
    stock: pd.DataFrame,
    movement_daily: pd.DataFrame,
    config: ProjectConfig,
) -> dict[str, Any]:
    """
    Construye el almacén compartido por semana.

    Incluye stock global, movimientos y consumo
    por caseta y fase.
    """

    phase_map = {
        _text(material, ""): _text(
            phase,
            "",
        )
        for material, phase
        in config.sap.get(
            "feed_materials",
            {},
        ).items()
    }

    phases = list(
        dict.fromkeys(
            phase_map.values()
        )
    )

    if not phases:
        phases = DEFAULT_PHASES.copy()

    all_phases = [
        *phases,
        TRANSITION_PHASE,
    ]

    if daily.empty:
        return {
            "casetas": [],
            "phases": all_phases,
            "weekly": [],
            "phase_split_mode": (
                "columnas_por_material"
            ),
        }

    required_daily = {
        "fecha",
        "caseta",
        "consumo_real_kg_dia",
    }

    missing_daily = (
        required_daily.difference(
            daily.columns
        )
    )

    if missing_daily:
        raise ValueError(
            "Faltan columnas para construir "
            "el almacén compartido: "
            f"{sorted(missing_daily)}"
        )

    daily_work = daily.copy()

    daily_work["fecha"] = pd.to_datetime(
        daily_work["fecha"],
        errors="coerce",
    ).dt.normalize()

    daily_work = daily_work.dropna(
        subset=["fecha"]
    )

    daily_work["caseta"] = daily_work[
        "caseta"
    ].map(
        lambda value: _text(
            value,
            "",
        )
    )

    daily_work[
        "consumo_real_kg_dia"
    ] = pd.to_numeric(
        daily_work[
            "consumo_real_kg_dia"
        ],
        errors="coerce",
    ).fillna(0.0)

    casetas = sorted(
        {
            value
            for value in daily_work[
                "caseta"
            ]
            if value
        },
        key=_caseta_sort_key,
    )

    start_date = pd.Timestamp(
        daily_work["fecha"].min()
    ).normalize()

    end_date = pd.Timestamp(
        daily_work["fecha"].max()
    ).normalize()

    calendar = pd.DataFrame(
        {
            "fecha": pd.date_range(
                start=start_date,
                end=end_date,
                freq="D",
            )
        }
    )

    calendar["fecha_inicio"] = (
        calendar["fecha"]
        .dt.to_period("W-SUN")
        .dt.start_time
    )

    calendar["fecha_fin"] = (
        calendar["fecha"]
        .dt.to_period("W-SUN")
        .dt.end_time
        .dt.normalize()
    )

    weeks = (
        calendar[
            [
                "fecha_inicio",
                "fecha_fin",
            ]
        ]
        .drop_duplicates()
        .sort_values(
            "fecha_inicio"
        )
        .reset_index(
            drop=True
        )
    )

    # ======================================================
    # Stock y movimientos globales
    # ======================================================

    global_daily = stock.copy()

    if global_daily.empty:
        global_daily = pd.DataFrame(
            columns=[
                "fecha",
                "stock",
                "entrada_alimento",
            ]
        )

    if "fecha" not in global_daily.columns:
        global_daily[
            "fecha"
        ] = pd.Series(
            dtype="datetime64[ns]"
        )

    global_daily[
        "fecha"
    ] = pd.to_datetime(
        global_daily["fecha"],
        errors="coerce",
    ).dt.normalize()

    if not movement_daily.empty:
        global_daily = (
            global_daily.merge(
                movement_daily,
                on="fecha",
                how="outer",
                validate="one_to_one",
            )
        )

    numeric_defaults = [
        "entrada_alimento",
        "entrada_alimento_detalle",
        "traspasos_internos",
        "ajustes_511_512",
        "ajustes_inventario",
        "traslados_641_643",
        "movimientos_logisticos",
        "mermas_551_552",
    ]

    for column in numeric_defaults:
        if column not in global_daily.columns:
            if column == "entrada_alimento":
                global_daily[
                    column
                ] = np.nan
            else:
                global_daily[
                    column
                ] = 0.0

        global_daily[
            column
        ] = pd.to_numeric(
            global_daily[column],
            errors="coerce",
        )

    global_daily[
        "entrada_alimento"
    ] = (
        global_daily[
            "entrada_alimento"
        ]
        .combine_first(
            global_daily[
                "entrada_alimento_detalle"
            ]
        )
        .fillna(0.0)
    )

    if "stock" not in global_daily.columns:
        global_daily[
            "stock"
        ] = np.nan

    global_daily[
        "stock"
    ] = pd.to_numeric(
        global_daily["stock"],
        errors="coerce",
    )

    global_daily = global_daily.loc[
        global_daily[
            "fecha"
        ].between(
            start_date,
            end_date,
        )
    ].copy()

    global_daily = global_daily.sort_values(
        "fecha"
    )

    global_daily[
        "fecha_inicio"
    ] = (
        global_daily["fecha"]
        .dt.to_period("W-SUN")
        .dt.start_time
    )

    global_weekly = (
        global_daily.groupby(
            "fecha_inicio",
            as_index=False,
        )
        .agg(
            stock=(
                "stock",
                _last_valid,
            ),
            entradas=(
                "entrada_alimento",
                "sum",
            ),
            traspasos=(
                "traspasos_internos",
                "sum",
            ),
            ajustes_511_512=(
                "ajustes_511_512",
                "sum",
            ),
            ajustes_inventario=(
                "ajustes_inventario",
                "sum",
            ),
            traslados_641_643=(
                "traslados_641_643",
                "sum",
            ),
            movimientos_logisticos=(
                "movimientos_logisticos",
                "sum",
            ),
            mermas=(
                "mermas_551_552",
                "sum",
            ),
        )
    )

    global_weekly[
        "ajustes"
    ] = (
        global_weekly[
            "ajustes_511_512"
        ]
        + global_weekly[
            "ajustes_inventario"
        ]
    )

    global_weekly[
        "logistica"
    ] = (
        global_weekly[
            "traslados_641_643"
        ]
        + global_weekly[
            "movimientos_logisticos"
        ]
    )

    weeks = weeks.merge(
        global_weekly[
            [
                "fecha_inicio",
                "stock",
                "entradas",
                "traspasos",
                "ajustes",
                "logistica",
                "mermas",
            ]
        ],
        on="fecha_inicio",
        how="left",
        validate="one_to_one",
    )

    for column in [
        "entradas",
        "traspasos",
        "ajustes",
        "logistica",
        "mermas",
    ]:
        weeks[column] = pd.to_numeric(
            weeks[column],
            errors="coerce",
        ).fillna(0.0)

    # ======================================================
    # Consumo semanal por caseta y fase
    # ======================================================

    daily_work[
        "fecha_inicio"
    ] = (
        daily_work["fecha"]
        .dt.to_period("W-SUN")
        .dt.start_time
    )

    consumption_total = (
        daily_work.groupby(
            [
                "fecha_inicio",
                "caseta",
            ]
        )[
            "consumo_real_kg_dia"
        ]
        .sum()
        .to_dict()
    )

    consumption_phase: dict[
        tuple[
            pd.Timestamp,
            str,
            str,
        ],
        float,
    ] = {}

    available_phase_columns = 0

    for material, phase in phase_map.items():
        column = (
            f"consumo_{material}_kg_dia"
        )

        if column not in daily_work.columns:
            continue

        available_phase_columns += 1

        daily_work[
            column
        ] = pd.to_numeric(
            daily_work[column],
            errors="coerce",
        ).fillna(0.0)

        grouped = daily_work.groupby(
            [
                "fecha_inicio",
                "caseta",
            ]
        )[column].sum()

        for (
            week_start,
            caseta,
        ), value in grouped.items():
            consumption_phase[
                (
                    week_start,
                    caseta,
                    phase,
                )
            ] = float(value)

    if (
        phase_map
        and available_phase_columns
        == len(phase_map)
    ):
        split_mode = (
            "columnas_por_material"
        )
    elif available_phase_columns > 0:
        split_mode = (
            "columnas_parciales_por_material"
        )
    else:
        split_mode = (
            "sin_columnas_por_material"
        )

    weekly_records: list[
        dict[str, Any]
    ] = []

    for _, week in weeks.iterrows():
        week_start = pd.Timestamp(
            week["fecha_inicio"]
        )

        week_end = pd.Timestamp(
            week["fecha_fin"]
        )

        consumption_by_house: dict[
            str,
            float,
        ] = {}

        consumption_by_house_phase: dict[
            str,
            dict[str, float],
        ] = {}

        for caseta in casetas:
            total = float(
                consumption_total.get(
                    (
                        week_start,
                        caseta,
                    ),
                    0.0,
                )
            )

            phase_values = {
                phase: float(
                    consumption_phase.get(
                        (
                            week_start,
                            caseta,
                            phase,
                        ),
                        0.0,
                    )
                )
                for phase in phases
            }

            phase_sum = sum(
                phase_values.values()
            )

            residual = (
                total
                - phase_sum
            )

            if abs(residual) < 0.01:
                residual = 0.0

            phase_values[
                TRANSITION_PHASE
            ] = max(
                0.0,
                float(residual),
            )

            consumption_by_house[
                caseta
            ] = total

            consumption_by_house_phase[
                caseta
            ] = phase_values

        weekly_records.append(
            {
                "fecha_inicio": (
                    week_start.strftime(
                        "%Y-%m-%d"
                    )
                ),
                "fecha_fin": (
                    week_end.strftime(
                        "%Y-%m-%d"
                    )
                ),
                "etiqueta": (
                    f"{week_start:%d/%m/%y}"
                    f"–{week_end:%d/%m/%y}"
                ),
                "stock": _number(
                    week.get("stock")
                ),
                "entradas": _number(
                    week.get("entradas"),
                    0.0,
                ),
                "traspasos": _number(
                    week.get("traspasos"),
                    0.0,
                ),
                "ajustes": _number(
                    week.get("ajustes"),
                    0.0,
                ),
                "logistica": _number(
                    week.get("logistica"),
                    0.0,
                ),
                "mermas": _number(
                    week.get("mermas"),
                    0.0,
                ),
                "consumo_por_caseta": (
                    consumption_by_house
                ),
                "consumo_por_caseta_fase": (
                    consumption_by_house_phase
                ),
            }
        )

    return {
        "casetas": casetas,
        "phases": all_phases,
        "weekly": weekly_records,
        "phase_split_mode": split_mode,
    }


def _regression(
    points: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calcula la regresión consumo-producción."""

    valid_points = [
        point
        for point in points
        if _number(
            point.get("x")
        ) is not None
        and _number(
            point.get("y")
        ) is not None
    ]

    if len(valid_points) < 2:
        return {
            "n": len(valid_points),
            "slope": None,
            "intercept": None,
            "r2": None,
        }

    x = np.asarray(
        [
            float(point["x"])
            for point in valid_points
        ],
        dtype=float,
    )

    y = np.asarray(
        [
            float(point["y"])
            for point in valid_points
        ],
        dtype=float,
    )

    if np.unique(x).size < 2:
        return {
            "n": len(valid_points),
            "slope": None,
            "intercept": None,
            "r2": None,
        }

    slope, intercept = np.polyfit(
        x,
        y,
        1,
    )

    prediction = (
        slope * x
        + intercept
    )

    total_variation = float(
        np.sum(
            (
                y
                - y.mean()
            )
            ** 2
        )
    )

    residual_variation = float(
        np.sum(
            (
                y
                - prediction
            )
            ** 2
        )
    )

    if total_variation <= 1e-12:
        r2 = None
    else:
        r2 = (
            1.0
            - residual_variation
            / total_variation
        )

    return {
        "n": len(valid_points),
        "slope": float(slope),
        "intercept": float(
            intercept
        ),
        "r2": (
            None
            if r2 is None
            else float(r2)
        ),
    }


def _daily_records(
    frame: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Construye los registros diarios para JavaScript."""

    records: list[
        dict[str, Any]
    ] = []

    for _, row in frame.iterrows():
        phase = _text(
            row.get(
                "fase_alimento_principal"
            ),
            "Sin fase",
        )

        if _boolean(
            row.get(
                "es_transicion_fase"
            )
        ):
            phase = TRANSITION_PHASE

        record = {
            "fecha": _date_iso(
                row.get("fecha")
            ),
            "fecha_label": _date_label(
                row.get("fecha")
            ),
            "semana": _integer(
                row.get("edad_semana")
            ),
            "dia_semana": _integer(
                row.get(
                    "edad_dia_semana"
                )
            ),
            "aves": _number(
                row.get(
                    "aves_disponibles"
                ),
                0.0,
            ),
            "mortalidad_dia": _number(
                row.get(
                    "mortalidad_dia"
                ),
                0.0,
            ),
            "mortalidad_acum": _number(
                _first(
                    row,
                    "mortalidad_real_acum",
                    "mortalidad_acum",
                ),
                0.0,
            ),
            "consumo_real": _number(
                row.get(
                    "consumo_real_kg_dia"
                ),
                0.0,
            ),
            "consumo_estandar": _number(
                row.get(
                    "consumo_estandar_kg_dia"
                ),
                0.0,
            ),
            "consumo_acum": _number(
                row.get(
                    "consumo_real_kg_acum"
                ),
                0.0,
            ),
            "produccion_real": _number(
                row.get(
                    "produccion_real_kg_dia"
                ),
                0.0,
            ),
            "produccion_estandar": _number(
                row.get(
                    "produccion_estandar_kg_dia"
                ),
                0.0,
            ),
            "produccion_acum": _number(
                row.get(
                    "produccion_real_kg_acum"
                ),
                0.0,
            ),
            "ica_principal": _number(
                row.get(
                    "ica_principal"
                )
            ),
            "ica_estandar": _number(
                _first(
                    row,
                    "ica_estandar_principal",
                    "ica_estandar_calculado",
                    "ica_sap",
                )
            ),
            "estado_ica": _text(
                row.get("estado_ica"),
                "No evaluable",
            ),
            "fase": phase,
            "material_fase": _text(
                row.get(
                    "material_alimento_principal"
                ),
                "",
            ),
            "stock": _number(
                row.get("stock"),
                0.0,
            ),
            "stock_apertura": _number(
                row.get(
                    "stock_apertura"
                ),
                0.0,
            ),
            "entrada_alimento": _number(
                row.get(
                    "entrada_alimento"
                ),
                0.0,
            ),
            "traspasos_internos": _number(
                row.get(
                    "traspasos_internos"
                ),
                0.0,
            ),
            "ajustes_inventario": _number(
                row.get(
                    "ajustes_inventario"
                ),
                0.0,
            ),
            "movimientos_logisticos": _number(
                row.get(
                    "movimientos_logisticos"
                ),
                0.0,
            ),
            "traslados_641_643": _number(
                row.get(
                    "traslados_641_643"
                ),
                0.0,
            ),
            "ajustes_511_512": _number(
                row.get(
                    "ajustes_511_512"
                ),
                0.0,
            ),
            "mermas_551_552": _number(
                row.get(
                    "mermas_551_552"
                ),
                0.0,
            ),
            "otros_movimientos_stock": _number(
                row.get(
                    "otros_movimientos_stock"
                ),
                0.0,
            ),
            "diferencia_conciliacion_stock": _number(
                row.get(
                    "diferencia_conciliacion_stock"
                ),
                0.0,
            ),
            "movimientos_resumen": _text(
                _first(
                    row,
                    "movimientos_resumen",
                    "stock_movimientos_sap",
                    "movimientos_sap_dia",
                ),
                "",
            ),
            "movimientos_adicionales": _text(
                _first(
                    row,
                    "movimientos_adicionales",
                    "stock_eventos_sap",
                    "eventos_sap_dia",
                ),
                "",
            ),
            "movimientos_operativos": _text(
                _first(
                    row,
                    "movimientos_operativos",
                    "stock_roles_sap",
                    "materiales_sap_dia",
                ),
                "",
            ),
            "documentos_sap": _text(
                _first(
                    row,
                    "documentos_sap",
                    "stock_documentos_sap",
                    "documentos_sap_dia",
                ),
                "",
            ),
            "score_anomalia": _number(
                row.get(
                    "score_anomalia"
                )
            ),
            "severidad_anomalia": _text(
                row.get("severidad"),
                "sin_clasificar",
            ),
            "es_anomalia": _boolean(
                row.get("es_anomalia")
            ),
            "motivo_anomalia": _text(
                row.get(
                    "motivo_anomalia"
                ),
                "",
            ),
        }

        records.append(record)

    return records


def _weekly_records(
    frame: pd.DataFrame,
) -> list[dict[str, Any]]:
    """Construye registros semanales para el HTML."""

    if frame.empty:
        return []

    required_columns = {
        "edad_semana",
        "fecha_inicio_semana",
        "fecha_fin_semana",
    }

    missing_columns = (
        required_columns.difference(
            frame.columns
        )
    )

    if missing_columns:
        raise ValueError(
            "Faltan columnas en weekly "
            "para construir el dashboard: "
            f"{sorted(missing_columns)}"
        )

    records: list[
        dict[str, Any]
    ] = []

    ordered = frame.sort_values(
        [
            "edad_semana",
            "fecha_inicio_semana",
        ]
    )

    for _, row in ordered.iterrows():
        week = _integer(
            row.get("edad_semana")
        )

        records.append(
            {
                "semana": week,
                "etiqueta": (
                    f"Semana {week}"
                ),
                "fecha_inicio": _date_iso(
                    row.get(
                        "fecha_inicio_semana"
                    )
                ),
                "fecha_fin": _date_iso(
                    row.get(
                        "fecha_fin_semana"
                    )
                ),
                "consumo_real": _number(
                    row.get(
                        "consumo_real_kg"
                    ),
                    0.0,
                ),
                "consumo_estandar": _number(
                    row.get(
                        "consumo_estandar_kg"
                    ),
                    0.0,
                ),
                "produccion_real": _number(
                    row.get(
                        "produccion_real_kg"
                    ),
                    0.0,
                ),
                "produccion_estandar": _number(
                    row.get(
                        "produccion_estandar_kg"
                    ),
                    0.0,
                ),
                "ica_real": _number(
                    row.get("ica_real")
                ),
                "ica_estandar": _number(
                    _first(
                        row,
                        "ica_estandar_principal",
                        "ica_estandar_calculado",
                        "ica_estandar_sap",
                    )
                ),
                "estado_ica": _text(
                    row.get(
                        "estado_ica"
                    ),
                    "No evaluable",
                ),
                "es_ica_evaluable": _boolean(
                    row.get(
                        "es_ica_evaluable"
                    )
                ),
            }
        )

    return records


def _meta(
    cycle_id: str,
    cycle_daily: pd.DataFrame,
    cycle_lookup: dict[
        str,
        pd.Series,
    ],
    config: ProjectConfig,
) -> dict[str, Any]:
    """Construye metadatos superiores de cada ciclo."""

    if cycle_daily.empty:
        raise ValueError(
            f"El ciclo {cycle_id!r} "
            "no tiene registros diarios."
        )

    cycle = cycle_lookup.get(
        cycle_id
    )

    first_daily = cycle_daily.iloc[
        0
    ]

    def value(
        column: str,
        fallback: Any = None,
    ) -> Any:
        if (
            cycle is not None
            and column in cycle.index
        ):
            cycle_value = cycle[
                column
            ]

            if not _missing(
                cycle_value
            ):
                return cycle_value

        if column in first_daily.index:
            daily_value = first_daily[
                column
            ]

            if not _missing(
                daily_value
            ):
                return daily_value

        return fallback

    standard_path = config.paths.get(
        "standard_excel",
        "standard_sap.xlsx",
    )

    return {
        "centro": _text(
            value("centro")
        ),
        "caseta": _text(
            value("caseta")
        ),
        "estado": _text(
            value("estado_ciclo"),
            "Sin estado",
        ),
        "lote": _text(
            value("lote")
        ),
        "orden": _text(
            value(
                "orden_operativa"
            )
        ),
        "fecha_inicio": _date_iso(
            value(
                "fecha_inicio_ciclo"
            )
        ),
        "fecha_fin": _date_iso(
            value(
                "fecha_fin_ciclo",
                value(
                    "fecha_corte_analisis"
                ),
            )
        ),
        "aves_iniciales": _number(
            value(
                "aves_iniciales"
            ),
            0.0,
        ),
        "granja": _text(
            config.project.get(
                "farm_name"
            ),
            "-",
        ),
        "fuente_estandar": Path(
            str(standard_path)
        ).name,
    }


def build_dashboard_payload(
    daily: pd.DataFrame,
    weekly: pd.DataFrame,
    stock_global: pd.DataFrame,
    scored: pd.DataFrame,
    cycles: pd.DataFrame,
    kardex: pd.DataFrame,
    config: ProjectConfig,
) -> dict[str, Any]:
    """
    Convierte las salidas del pipeline al JSON
    requerido por el dashboard.
    """

    required_daily_columns = {
        "cycle_id",
        "fecha",
        "caseta",
    }

    missing_daily_columns = (
        required_daily_columns.difference(
            daily.columns
        )
    )

    if missing_daily_columns:
        raise ValueError(
            "Faltan columnas obligatorias "
            "en daily: "
            f"{sorted(missing_daily_columns)}"
        )

    daily_work = daily.copy()

    daily_work[
        "cycle_id"
    ] = daily_work[
        "cycle_id"
    ].map(_text)

    daily_work[
        "fecha"
    ] = pd.to_datetime(
        daily_work["fecha"],
        errors="coerce",
    ).dt.normalize()

    daily_work = daily_work.dropna(
        subset=["fecha"]
    )

    if daily_work.empty:
        raise ValueError(
            "daily no contiene fechas válidas."
        )

    # ======================================================
    # Stock global
    # ======================================================

    stock = _prepare_stock(
        stock_global
    )

    if not stock.empty:
        daily_work = daily_work.merge(
            stock,
            on="fecha",
            how="left",
            validate="many_to_one",
        )

    # ======================================================
    # Movimientos detallados del Kardex
    # ======================================================

    movement_daily = (
        _prepare_kardex_movements(
            kardex,
            config,
        )
    )

    if not movement_daily.empty:
        daily_work = daily_work.merge(
            movement_daily,
            on="fecha",
            how="left",
            validate="many_to_one",
        )

    movement_numeric_columns = [
        "entrada_alimento_detalle",
        "traspasos_internos",
        "ajustes_511_512",
        "ajustes_inventario",
        "traslados_641_643",
        "movimientos_logisticos",
        "mermas_551_552",
    ]

    for column in movement_numeric_columns:
        if column not in daily_work.columns:
            daily_work[
                column
            ] = 0.0

        daily_work[
            column
        ] = pd.to_numeric(
            daily_work[column],
            errors="coerce",
        ).fillna(0.0)

    if (
        "entrada_alimento"
        not in daily_work.columns
    ):
        daily_work[
            "entrada_alimento"
        ] = daily_work[
            "entrada_alimento_detalle"
        ]
    else:
        daily_work[
            "entrada_alimento"
        ] = (
            pd.to_numeric(
                daily_work[
                    "entrada_alimento"
                ],
                errors="coerce",
            )
            .combine_first(
                daily_work[
                    "entrada_alimento_detalle"
                ]
            )
            .fillna(0.0)
        )

    # ======================================================
    # Scores y anomalías
    # ======================================================

    scores = _prepare_scores(
        scored
    )

    if not scores.empty:
        score_fields = [
            column
            for column in scores.columns
            if column not in {
                "cycle_id",
                "fecha",
            }
        ]

        existing_score_fields = [
            column
            for column in score_fields
            if column
            in daily_work.columns
        ]

        if existing_score_fields:
            daily_work = daily_work.drop(
                columns=(
                    existing_score_fields
                )
            )

        daily_work = daily_work.merge(
            scores,
            on=[
                "cycle_id",
                "fecha",
            ],
            how="left",
            validate="one_to_one",
        )

    # ======================================================
    # Resumen semanal
    # ======================================================

    weekly_work = weekly.copy()

    if not weekly_work.empty:
        if (
            "cycle_id"
            not in weekly_work.columns
        ):
            raise ValueError(
                "weekly no contiene "
                "la columna 'cycle_id'."
            )

        weekly_work[
            "cycle_id"
        ] = weekly_work[
            "cycle_id"
        ].map(_text)

        for column in [
            "fecha_inicio_semana",
            "fecha_fin_semana",
        ]:
            if column in weekly_work.columns:
                weekly_work[
                    column
                ] = pd.to_datetime(
                    weekly_work[
                        column
                    ],
                    errors="coerce",
                ).dt.normalize()

    # ======================================================
    # Catálogo de ciclos
    # ======================================================

    cycle_lookup: dict[
        str,
        pd.Series,
    ] = {}

    if (
        not cycles.empty
        and "cycle_id"
        in cycles.columns
    ):
        cycles_work = cycles.copy()

        cycles_work[
            "cycle_id"
        ] = cycles_work[
            "cycle_id"
        ].map(_text)

        cycles_work = (
            cycles_work.drop_duplicates(
                subset=["cycle_id"],
                keep="last",
            )
        )

        cycle_lookup = {
            row["cycle_id"]: row
            for _, row
            in cycles_work.iterrows()
        }

    # ======================================================
    # Orden del selector de periodos
    # ======================================================

    period_order = (
        daily_work.groupby(
            "cycle_id",
            as_index=False,
        )
        .agg(
            fecha_inicio=(
                "fecha",
                "min",
            ),
            caseta=(
                "caseta",
                "first",
            ),
        )
        .sort_values(
            [
                "fecha_inicio",
                "caseta",
                "cycle_id",
            ]
        )
    )

    period_ids = period_order[
        "cycle_id"
    ].tolist()

    periods: dict[
        str,
        Any,
    ] = {}

    # ======================================================
    # Construcción de cada ciclo
    # ======================================================

    for cycle_id in period_ids:
        cycle_daily = daily_work.loc[
            daily_work[
                "cycle_id"
            ].eq(cycle_id)
        ].copy()

        cycle_daily = (
            cycle_daily
            .sort_values("fecha")
            .drop_duplicates(
                subset=["fecha"],
                keep="last",
            )
        )

        if weekly_work.empty:
            cycle_weekly = (
                pd.DataFrame()
            )
        else:
            cycle_weekly = (
                weekly_work.loc[
                    weekly_work[
                        "cycle_id"
                    ].eq(cycle_id)
                ].copy()
            )

        daily_records = _daily_records(
            cycle_daily
        )

        weekly_records = _weekly_records(
            cycle_weekly
        )

        scatter = [
            {
                "x": row[
                    "consumo_real"
                ],
                "y": row[
                    "produccion_real"
                ],
                "fecha": row[
                    "fecha"
                ],
            }
            for row in daily_records
            if (
                row["consumo_real"]
                is not None
                and row[
                    "produccion_real"
                ]
                is not None
            )
        ]

        periods[
            cycle_id
        ] = {
            "meta": _meta(
                cycle_id,
                cycle_daily,
                cycle_lookup,
                config,
            ),
            "daily": daily_records,
            "weekly": weekly_records,
            "scatter": scatter,
            "regression_stats": (
                _regression(scatter)
            ),
        }

    # ======================================================
    # Almacén compartido
    # ======================================================

    shared_store = (
        _build_shared_store(
            daily=daily_work,
            stock=stock,
            movement_daily=(
                movement_daily
            ),
            config=config,
        )
    )

    timezone_name = _text(
        config.project.get(
            "timezone"
        ),
        "America/Merida",
    )

    try:
        generated_at = datetime.now(
            ZoneInfo(
                timezone_name
            )
        ).isoformat(
            timespec="seconds"
        )
    except Exception:
        generated_at = (
            datetime.now().isoformat(
                timespec="seconds"
            )
        )

    payload = {
        "generated_at": (
            generated_at
        ),
        "period_ids": period_ids,
        "periods": periods,
        "shared_store": shared_store,
    }

    return _json_clean(
        payload
    )


def validate_dashboard_payload(
    payload: dict[str, Any],
) -> None:
    """
    Valida la estructura y las conciliaciones
    principales del payload.
    """

    period_ids = payload.get(
        "period_ids"
    )

    periods = payload.get(
        "periods"
    )

    if not isinstance(
        period_ids,
        list,
    ):
        raise ValueError(
            "payload['period_ids'] "
            "debe ser una lista."
        )

    if not period_ids:
        raise ValueError(
            "El payload no contiene "
            "periodos productivos."
        )

    if not isinstance(
        periods,
        dict,
    ):
        raise ValueError(
            "payload['periods'] "
            "debe ser un diccionario."
        )

    required_period_keys = {
        "meta",
        "daily",
        "weekly",
        "scatter",
        "regression_stats",
    }

    required_daily_keys = {
        "fecha",
        "fecha_label",
        "semana",
        "dia_semana",
        "aves",
        "consumo_real",
        "produccion_real",
        "stock",
        "fase",
        "entrada_alimento",
        "traspasos_internos",
        "ajustes_inventario",
        "ajustes_511_512",
        "traslados_641_643",
        "movimientos_logisticos",
        "mermas_551_552",
    }

    for period_id in period_ids:
        period = periods.get(
            period_id
        )

        if period is None:
            raise ValueError(
                "No existe el periodo "
                f"{period_id!r}."
            )

        missing_period_keys = (
            required_period_keys
            .difference(period)
        )

        if missing_period_keys:
            raise ValueError(
                f"El periodo {period_id!r} "
                "no contiene las claves: "
                f"{sorted(missing_period_keys)}"
            )

        if not period["daily"]:
            raise ValueError(
                f"El periodo {period_id!r} "
                "no tiene registros diarios."
            )

        missing_daily_keys = (
            required_daily_keys
            .difference(
                period["daily"][0]
            )
        )

        if missing_daily_keys:
            raise ValueError(
                "Los datos diarios de "
                f"{period_id!r} no contienen: "
                f"{sorted(missing_daily_keys)}"
            )

    # ======================================================
    # Validación del almacén compartido
    # ======================================================

    shared_store = payload.get(
        "shared_store"
    )

    if not isinstance(
        shared_store,
        dict,
    ):
        raise ValueError(
            "payload['shared_store'] "
            "debe ser un diccionario."
        )

    required_shared_keys = {
        "casetas",
        "phases",
        "weekly",
        "phase_split_mode",
    }

    missing_shared_keys = (
        required_shared_keys
        .difference(
            shared_store
        )
    )

    if missing_shared_keys:
        raise ValueError(
            "El almacén compartido "
            "no contiene: "
            f"{sorted(missing_shared_keys)}"
        )

    if not isinstance(
        shared_store["casetas"],
        list,
    ):
        raise ValueError(
            "shared_store['casetas'] "
            "debe ser una lista."
        )

    if not isinstance(
        shared_store["phases"],
        list,
    ):
        raise ValueError(
            "shared_store['phases'] "
            "debe ser una lista."
        )

    if not shared_store["weekly"]:
        raise ValueError(
            "El almacén compartido "
            "no contiene semanas."
        )

    required_week_keys = {
        "fecha_inicio",
        "fecha_fin",
        "etiqueta",
        "stock",
        "entradas",
        "traspasos",
        "ajustes",
        "logistica",
        "mermas",
        "consumo_por_caseta",
        "consumo_por_caseta_fase",
    }

    missing_week_keys = (
        required_week_keys
        .difference(
            shared_store[
                "weekly"
            ][0]
        )
    )

    if missing_week_keys:
        raise ValueError(
            "Las semanas del almacén "
            "compartido no contienen: "
            f"{sorted(missing_week_keys)}"
        )

    # ======================================================
    # Conciliaciones de consumo
    # ======================================================

    shared_consumption = sum(
        sum(
            float(
                value or 0.0
            )
            for value in week[
                "consumo_por_caseta"
            ].values()
        )
        for week in shared_store[
            "weekly"
        ]
    )

    phase_consumption = sum(
        sum(
            sum(
                float(
                    value or 0.0
                )
                for value
                in phases.values()
            )
            for phases
            in week[
                "consumo_por_caseta_fase"
            ].values()
        )
        for week in shared_store[
            "weekly"
        ]
    )

    daily_consumption = sum(
        sum(
            float(
                row.get(
                    "consumo_real",
                    0.0,
                )
                or 0.0
            )
            for row in periods[
                period_id
            ]["daily"]
        )
        for period_id in period_ids
    )

    if abs(
        shared_consumption
        - daily_consumption
    ) > 0.01:
        raise ValueError(
            "El consumo semanal por caseta "
            "no concilia contra el consumo "
            "diario de los ciclos. Diferencia: "
            f"{shared_consumption - daily_consumption:.2f} kg."
        )

    if abs(
        phase_consumption
        - shared_consumption
    ) > 0.01:
        raise ValueError(
            "El consumo por fase no concilia "
            "contra el consumo por caseta. "
            "Diferencia: "
            f"{phase_consumption - shared_consumption:.2f} kg."
        )



    