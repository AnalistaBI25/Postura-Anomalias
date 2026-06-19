
from __future__ import annotations

from typing import Final

import numpy as np
import pandas as pd

from .config import ProjectConfig
from .utils import compact_unique


# ============================================================
# Contratos y constantes
# ============================================================

STOCK_REQUIRED_COLUMNS: Final[set[str]] = {
    "fecha",
    "centro",
    "almacen",
    "material",
    "rol_movimiento",
    "cantidad_abs",
    "movimiento_stock_alimento_kg",
    "consumo_alimento_neto_kg",
    "clase_movimiento",
    "clase_transaccion_evento",
}

EPSILON: Final[float] = 1e-9

ENTRY_ROLES: Final[set[str]] = {
    "ALIMENTO_ENTRADA",
    "ENTRADA_ALIMENTO",
}

ENTRY_REVERSE_ROLES: Final[set[str]] = {
    "ALIMENTO_ENTRADA_REVERSA",
    "ALIMENTO_REVERSA_ENTRADA",
    "REVERSA_ENTRADA_ALIMENTO",
}

CONSUMPTION_ROLES: Final[set[str]] = {
    "CONSUMO_ALIMENTO",
    "ALIMENTO_CONSUMO",
}

CONSUMPTION_REVERSE_ROLES: Final[set[str]] = {
    "CONSUMO_ALIMENTO_REVERSA",
    "ALIMENTO_CONSUMO_REVERSA",
    "REVERSA_CONSUMO_ALIMENTO",
}


# ============================================================
# Validaciones
# ============================================================

def _require_dataframe(
    frame: pd.DataFrame,
    frame_name: str,
) -> None:
    """
    Valida que el objeto recibido sea un DataFrame.
    """

    if not isinstance(frame, pd.DataFrame):
        raise TypeError(
            f"{frame_name} debe ser un pandas.DataFrame."
        )

    if frame.empty:
        raise ValueError(
            f"{frame_name} está vacío."
        )


def _require_columns(
    frame: pd.DataFrame,
    required: set[str],
    frame_name: str,
) -> None:
    """
    Valida que existan las columnas mínimas requeridas.
    """

    missing = sorted(
        required.difference(frame.columns)
    )

    if missing:
        raise ValueError(
            f"Faltan columnas requeridas en "
            f"{frame_name}: {missing}"
        )


def _require_mapping(
    value: object,
    name: str,
) -> dict:
    """
    Valida que una sección de configuración sea un diccionario.
    """

    if not isinstance(value, dict):
        raise ValueError(
            f"La configuración {name} debe ser un diccionario."
        )

    return value


# ============================================================
# Preparación de configuración
# ============================================================

def _read_stock_configuration(
    config: ProjectConfig,
) -> tuple[
    str,
    str,
    dict[str, str],
    pd.Timestamp,
    dict[str, float],
]:
    """
    Extrae y valida la configuración necesaria para stock.
    """

    project = _require_mapping(
        getattr(config, "project", None),
        "project",
    )

    sap = _require_mapping(
        getattr(config, "sap", None),
        "sap",
    )

    stock_config = _require_mapping(
        getattr(config, "stock", None),
        "stock",
    )

    required_project_keys = {
        "center_id",
    }

    missing_project = sorted(
        required_project_keys.difference(project)
    )

    if missing_project:
        raise ValueError(
            "Faltan claves en config.project: "
            f"{missing_project}"
        )

    required_sap_keys = {
        "feed_warehouse",
        "feed_materials",
    }

    missing_sap = sorted(
        required_sap_keys.difference(sap)
    )

    if missing_sap:
        raise ValueError(
            "Faltan claves en config.sap: "
            f"{missing_sap}"
        )

    required_stock_keys = {
        "initial_stock_date",
        "initial_stock_kg",
    }

    missing_stock = sorted(
        required_stock_keys.difference(stock_config)
    )

    if missing_stock:
        raise ValueError(
            "Faltan claves en config.stock: "
            f"{missing_stock}"
        )

    center = str(
        project["center_id"]
    ).strip()

    warehouse = str(
        sap["feed_warehouse"]
    ).strip()

    feed_materials_raw = _require_mapping(
        sap["feed_materials"],
        "sap.feed_materials",
    )

    feed_materials = {
        str(material).strip(): str(phase).strip()
        for material, phase
        in feed_materials_raw.items()
    }

    if not feed_materials:
        raise ValueError(
            "config.sap['feed_materials'] está vacío."
        )

    initial_date = pd.to_datetime(
        stock_config["initial_stock_date"],
        errors="coerce",
    )

    if pd.isna(initial_date):
        raise ValueError(
            "config.stock['initial_stock_date'] "
            "no contiene una fecha válida."
        )

    initial_date = pd.Timestamp(
        initial_date
    ).normalize()

    initial_stock_raw = _require_mapping(
        stock_config["initial_stock_kg"],
        "stock.initial_stock_kg",
    )

    initial_stock: dict[str, float] = {}

    for material, quantity in initial_stock_raw.items():
        material_key = str(material).strip()

        try:
            initial_stock[material_key] = float(
                quantity
            )

        except (
            TypeError,
            ValueError,
        ) as error:
            raise ValueError(
                "El saldo inicial del material "
                f"{material_key!r} no es numérico: "
                f"{quantity!r}"
            ) from error

    return (
        center,
        warehouse,
        feed_materials,
        initial_date,
        initial_stock,
    )


# ============================================================
# Preparación del kardex
# ============================================================

def _prepare_kardex(
    kardex: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normaliza columnas del kardex necesarias para stock.
    """

    _require_dataframe(
        kardex,
        "kardex",
    )

    _require_columns(
        kardex,
        STOCK_REQUIRED_COLUMNS,
        "kardex",
    )

    prepared = kardex.copy()

    prepared["fecha"] = pd.to_datetime(
        prepared["fecha"],
        errors="coerce",
    )

    invalid_dates = int(
        prepared["fecha"].isna().sum()
    )

    if invalid_dates:
        raise ValueError(
            "El kardex contiene "
            f"{invalid_dates} fecha(s) inválida(s)."
        )

    prepared["fecha"] = (
        prepared["fecha"]
        .dt.normalize()
    )

    text_columns = [
        "centro",
        "almacen",
        "material",
        "rol_movimiento",
        "clase_movimiento",
        "clase_transaccion_evento",
    ]

    optional_text_columns = [
        "orden",
        "documento_material",
        "documento",
        "numero_documento",
    ]

    for column in [
        *text_columns,
        *[
            optional
            for optional in optional_text_columns
            if optional in prepared.columns
        ],
    ]:
        prepared[column] = (
            prepared[column]
            .astype("string")
            .fillna("")
            .str.strip()
        )

    numeric_columns = [
        "cantidad_abs",
        "movimiento_stock_alimento_kg",
        "consumo_alimento_neto_kg",
    ]

    for column in numeric_columns:
        prepared[column] = pd.to_numeric(
            prepared[column],
            errors="coerce",
        ).fillna(0.0)

    return (
        prepared
        .sort_values("fecha")
        .reset_index(drop=True)
    )


# ============================================================
# Clasificación de componentes físicos
# ============================================================

def _best_absolute_quantity(
    preferred: pd.Series,
    fallback: pd.Series,
    physical: pd.Series,
) -> pd.Series:
    """
    Elige la mejor cantidad absoluta disponible por movimiento.
    """

    preferred_abs = (
        pd.to_numeric(
            preferred,
            errors="coerce",
        )
        .fillna(0.0)
        .abs()
    )

    fallback_abs = (
        pd.to_numeric(
            fallback,
            errors="coerce",
        )
        .fillna(0.0)
        .abs()
    )

    physical_abs = (
        pd.to_numeric(
            physical,
            errors="coerce",
        )
        .fillna(0.0)
        .abs()
    )

    result = preferred_abs.copy()

    use_fallback = result.le(EPSILON)

    result.loc[use_fallback] = (
        fallback_abs.loc[use_fallback]
    )

    use_physical = result.le(EPSILON)

    result.loc[use_physical] = (
        physical_abs.loc[use_physical]
    )

    return result


def _add_movement_components(
    movements: pd.DataFrame,
) -> pd.DataFrame:
    """
    Separa las principales operaciones de alimento:

    - entrada 101 WE;
    - reversa 102 WE;
    - consumo 261 WA;
    - reversa 262 WA;
    - otros movimientos físicos.

    El movimiento físico oficial sigue siendo
    movimiento_stock_alimento_kg.
    """

    result = movements.copy()

    role = (
        result["rol_movimiento"]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.upper()
    )

    movement_code = (
        result["clase_movimiento"]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.upper()
    )

    event_code = (
        result["clase_transaccion_evento"]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.upper()
    )

    entry_mask = (
        role.isin(ENTRY_ROLES)
        | (
            movement_code.eq("101")
            & event_code.eq("WE")
        )
    )

    entry_reverse_mask = (
        role.isin(ENTRY_REVERSE_ROLES)
        | (
            movement_code.eq("102")
            & event_code.eq("WE")
        )
    )

    consumption_mask = (
        role.isin(CONSUMPTION_ROLES)
        | (
            movement_code.eq("261")
            & event_code.eq("WA")
        )
    )

    consumption_reverse_mask = (
        role.isin(
            CONSUMPTION_REVERSE_ROLES
        )
        | (
            movement_code.eq("262")
            & event_code.eq("WA")
        )
    )

    known_mask = (
        entry_mask
        | entry_reverse_mask
        | consumption_mask
        | consumption_reverse_mask
    )

    general_quantity = _best_absolute_quantity(
        preferred=result["cantidad_abs"],
        fallback=result[
            "movimiento_stock_alimento_kg"
        ],
        physical=result[
            "movimiento_stock_alimento_kg"
        ],
    )

    consumption_quantity = _best_absolute_quantity(
        preferred=result[
            "consumo_alimento_neto_kg"
        ],
        fallback=result["cantidad_abs"],
        physical=result[
            "movimiento_stock_alimento_kg"
        ],
    )

    result["entrada_101_we_kg_row"] = np.where(
        entry_mask,
        general_quantity,
        0.0,
    )

    result["reversa_102_we_kg_row"] = np.where(
        entry_reverse_mask,
        general_quantity,
        0.0,
    )

    result["consumo_261_kg_row"] = np.where(
        consumption_mask,
        consumption_quantity,
        0.0,
    )

    result[
        "reversa_consumo_262_kg_row"
    ] = np.where(
        consumption_reverse_mask,
        consumption_quantity,
        0.0,
    )

    result[
        "otros_movimientos_stock_kg_row"
    ] = np.where(
        ~known_mask,
        result[
            "movimiento_stock_alimento_kg"
        ],
        0.0,
    )

    result["movimiento_stock_kg_row"] = (
        result[
            "movimiento_stock_alimento_kg"
        ]
    )

    result["consumo_neto_fuente_kg_row"] = (
        result[
            "consumo_alimento_neto_kg"
        ]
    )

    result[
        "consumo_neto_calculado_kg_row"
    ] = (
        result["consumo_261_kg_row"]
        - result[
            "reversa_consumo_262_kg_row"
        ]
    )

    result[
        "movimiento_stock_reconstruido_kg_row"
    ] = (
        result["entrada_101_we_kg_row"]
        - result["reversa_102_we_kg_row"]
        - result["consumo_261_kg_row"]
        + result[
            "reversa_consumo_262_kg_row"
        ]
        + result[
            "otros_movimientos_stock_kg_row"
        ]
    )

    result["es_entrada_101_we"] = entry_mask
    result["es_reversa_102_we"] = (
        entry_reverse_mask
    )
    result["es_consumo_261_wa"] = (
        consumption_mask
    )
    result["es_reversa_262_wa"] = (
        consumption_reverse_mask
    )
    result["es_otro_movimiento_stock"] = (
        ~known_mask
    )

    return result


# ============================================================
# Agregación diaria
# ============================================================

def _optional_document_column(
    frame: pd.DataFrame,
) -> str | None:
    """
    Identifica una columna de documento SAP disponible.
    """

    candidates = [
        "documento_material",
        "documento",
        "numero_documento",
    ]

    return next(
        (
            column
            for column in candidates
            if column in frame.columns
        ),
        None,
    )


def _aggregate_daily_movements(
    movements: pd.DataFrame,
) -> pd.DataFrame:
    """
    Agrega los movimientos por fecha y material.
    """

    numeric_columns = [
        "entrada_101_we_kg_row",
        "reversa_102_we_kg_row",
        "consumo_261_kg_row",
        "reversa_consumo_262_kg_row",
        "consumo_neto_fuente_kg_row",
        "consumo_neto_calculado_kg_row",
        "otros_movimientos_stock_kg_row",
        "movimiento_stock_kg_row",
        "movimiento_stock_reconstruido_kg_row",
    ]

    numeric = (
        movements
        .groupby(
            [
                "fecha",
                "material",
            ],
            dropna=False,
        )[numeric_columns]
        .sum()
        .reset_index()
        .rename(
            columns={
                "entrada_101_we_kg_row":
                    "entrada_101_we_kg",
                "reversa_102_we_kg_row":
                    "reversa_102_we_kg",
                "consumo_261_kg_row":
                    "consumo_261_kg",
                "reversa_consumo_262_kg_row":
                    "reversa_consumo_262_kg",
                "consumo_neto_fuente_kg_row":
                    "consumo_neto_fuente_kg",
                "consumo_neto_calculado_kg_row":
                    "consumo_neto_calculado_kg",
                "otros_movimientos_stock_kg_row":
                    "otros_movimientos_stock_kg",
                "movimiento_stock_kg_row":
                    "movimiento_stock_kg",
                "movimiento_stock_reconstruido_kg_row":
                    "movimiento_stock_reconstruido_kg",
            }
        )
    )

    metadata_aggregation: dict[
        str,
        tuple[str, object],
    ] = {
        "movimientos_sap": (
            "clase_movimiento",
            compact_unique,
        ),
        "eventos_sap": (
            "clase_transaccion_evento",
            compact_unique,
        ),
        "roles_sap": (
            "rol_movimiento",
            compact_unique,
        ),
    }

    if "orden" in movements.columns:
        metadata_aggregation["ordenes_sap"] = (
            "orden",
            compact_unique,
        )

    document_column = _optional_document_column(
        movements
    )

    if document_column is not None:
        metadata_aggregation[
            "documentos_sap"
        ] = (
            document_column,
            compact_unique,
        )

    metadata = (
        movements
        .groupby(
            [
                "fecha",
                "material",
            ],
            dropna=False,
        )
        .agg(
            **{
                output: pd.NamedAgg(
                    column=source,
                    aggfunc=function,
                )
                for output, (
                    source,
                    function,
                ) in metadata_aggregation.items()
            }
        )
        .reset_index()
    )

    return numeric.merge(
        metadata,
        on=[
            "fecha",
            "material",
        ],
        how="left",
        validate="one_to_one",
    )


# ============================================================
# Calendario
# ============================================================

def _build_calendar(
    initial_date: pd.Timestamp,
    end_date: pd.Timestamp,
    feed_materials: dict[str, str],
) -> pd.DataFrame:
    """
    Construye una fila por día y material.
    """

    if end_date < initial_date:
        end_date = initial_date

    return (
        pd.MultiIndex.from_product(
            [
                pd.date_range(
                    initial_date,
                    end_date,
                    freq="D",
                ),
                list(feed_materials),
            ],
            names=[
                "fecha",
                "material",
            ],
        )
        .to_frame(index=False)
    )


# ============================================================
# Reconstrucción por material
# ============================================================

def _reconstruct_stock_by_material(
    stock: pd.DataFrame,
    initial_stock: dict[str, float],
) -> pd.DataFrame:
    """
    Reconstruye apertura, variación y cierre por material.
    """

    pieces: list[pd.DataFrame] = []

    for material, group in stock.groupby(
        "material",
        sort=False,
    ):
        group = (
            group
            .sort_values("fecha")
            .copy()
        )

        material_key = str(material)

        initial_configured = (
            material_key in initial_stock
        )

        opening_balance = float(
            initial_stock.get(
                material_key,
                0.0,
            )
        )

        group["stock_inicial_kg"] = (
            opening_balance
        )

        group[
            "saldo_inicial_configurado"
        ] = initial_configured

        group["stock_inicial_faltante"] = (
            not initial_configured
        )

        group["stock_cierre_kg"] = (
            opening_balance
            + group[
                "movimiento_stock_kg"
            ].cumsum()
        )

        group["stock_apertura_kg"] = (
            group["stock_cierre_kg"]
            .shift(1)
        )

        group.loc[
            group.index[0],
            "stock_apertura_kg",
        ] = opening_balance

        group[
            "stock_cierre_esperado_kg"
        ] = (
            group["stock_apertura_kg"]
            + group["movimiento_stock_kg"]
        )

        group["variacion_stock_kg"] = (
            group["stock_cierre_kg"]
            - group["stock_apertura_kg"]
        )

        group[
            "diferencia_conciliacion_kg"
        ] = (
            group["stock_cierre_kg"]
            - group[
                "stock_cierre_esperado_kg"
            ]
        )

        group[
            "diferencia_movimiento_variacion_kg"
        ] = (
            group["variacion_stock_kg"]
            - group["movimiento_stock_kg"]
        )

        group[
            "diferencia_desglose_movimientos_kg"
        ] = (
            group["movimiento_stock_kg"]
            - group[
                "movimiento_stock_reconstruido_kg"
            ]
        )

        group[
            "diferencia_consumo_neto_kg"
        ] = (
            group[
                "consumo_neto_fuente_kg"
            ]
            - group[
                "consumo_neto_calculado_kg"
            ]
        )

        # Compatibilidad con la salida anterior.
        group["consumo_neto_kg"] = (
            group[
                "consumo_neto_fuente_kg"
            ]
        )

        group["entradas_netas_kg"] = (
            group["entrada_101_we_kg"]
            - group["reversa_102_we_kg"]
        )

        group["stock_negativo"] = (
            group["stock_cierre_kg"]
            .lt(-EPSILON)
        )

        pieces.append(group)

    return pd.concat(
        pieces,
        ignore_index=True,
    )


# ============================================================
# Reconstrucción global
# ============================================================

def _build_global_stock(
    stock_material: pd.DataFrame,
    initial_date: pd.Timestamp,
) -> pd.DataFrame:
    """
    Consolida todos los materiales del almacén.
    """

    aggregation: dict[
        str,
        tuple[str, object],
    ] = {
        "stock_inicial_global_kg": (
            "stock_inicial_kg",
            "sum",
        ),
        "stock_apertura_global_kg": (
            "stock_apertura_kg",
            "sum",
        ),
        "stock_global_kg": (
            "stock_cierre_kg",
            "sum",
        ),
        "entradas_alimento_kg": (
            "entrada_101_we_kg",
            "sum",
        ),
        "reversas_entrada_kg": (
            "reversa_102_we_kg",
            "sum",
        ),
        "entradas_netas_kg": (
            "entradas_netas_kg",
            "sum",
        ),
        "consumo_261_kg": (
            "consumo_261_kg",
            "sum",
        ),
        "reversas_consumo_kg": (
            "reversa_consumo_262_kg",
            "sum",
        ),
        "consumo_total_alimento_kg": (
            "consumo_neto_kg",
            "sum",
        ),
        "consumo_neto_calculado_kg": (
            "consumo_neto_calculado_kg",
            "sum",
        ),
        "otros_movimientos_stock_kg": (
            "otros_movimientos_stock_kg",
            "sum",
        ),
        "movimiento_stock_total_kg": (
            "movimiento_stock_kg",
            "sum",
        ),
        "movimiento_stock_reconstruido_kg": (
            "movimiento_stock_reconstruido_kg",
            "sum",
        ),
        "materiales_stock_negativo": (
            "stock_negativo",
            "sum",
        ),
        "materiales_sin_saldo_inicial": (
            "stock_inicial_faltante",
            "sum",
        ),
        "movimientos_sap": (
            "movimientos_sap",
            compact_unique,
        ),
        "eventos_sap": (
            "eventos_sap",
            compact_unique,
        ),
        "roles_sap": (
            "roles_sap",
            compact_unique,
        ),
    }

    if "ordenes_sap" in stock_material.columns:
        aggregation["ordenes_sap"] = (
            "ordenes_sap",
            compact_unique,
        )

    if "documentos_sap" in stock_material.columns:
        aggregation["documentos_sap"] = (
            "documentos_sap",
            compact_unique,
        )

    stock_global = (
        stock_material
        .groupby(
            "fecha",
            as_index=False,
        )
        .agg(
            **{
                output: pd.NamedAgg(
                    column=source,
                    aggfunc=function,
                )
                for output, (
                    source,
                    function,
                ) in aggregation.items()
            }
        )
        .sort_values("fecha")
        .reset_index(drop=True)
    )

    stock_global[
        "stock_cierre_esperado_global_kg"
    ] = (
        stock_global[
            "stock_apertura_global_kg"
        ]
        + stock_global[
            "movimiento_stock_total_kg"
        ]
    )

    stock_global[
        "variacion_stock_global_kg"
    ] = (
        stock_global["stock_global_kg"]
        - stock_global[
            "stock_apertura_global_kg"
        ]
    )

    stock_global[
        "diferencia_conciliacion_kg"
    ] = (
        stock_global["stock_global_kg"]
        - stock_global[
            "stock_cierre_esperado_global_kg"
        ]
    )

    stock_global[
        "diferencia_movimiento_variacion_kg"
    ] = (
        stock_global[
            "variacion_stock_global_kg"
        ]
        - stock_global[
            "movimiento_stock_total_kg"
        ]
    )

    stock_global[
        "diferencia_desglose_movimientos_kg"
    ] = (
        stock_global[
            "movimiento_stock_total_kg"
        ]
        - stock_global[
            "movimiento_stock_reconstruido_kg"
        ]
    )

    stock_global[
        "diferencia_consumo_neto_kg"
    ] = (
        stock_global[
            "consumo_total_alimento_kg"
        ]
        - stock_global[
            "consumo_neto_calculado_kg"
        ]
    )

    stock_global["stock_negativo"] = (
        stock_global["stock_global_kg"]
        .lt(-EPSILON)
    )

    stock_global[
        "saldo_inicial_completo"
    ] = (
        stock_global[
            "materiales_sin_saldo_inicial"
        ]
        .eq(0)
    )

    stock_global["fecha_saldo_inicial"] = (
        initial_date
    )

    stock_global[
        "es_fecha_saldo_inicial"
    ] = (
        stock_global["fecha"]
        .eq(initial_date)
    )

    return stock_global


# ============================================================
# API pública
# ============================================================

def build_feed_stock(
    kardex: pd.DataFrame,
    config: ProjectConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Reconstruye el stock físico diario del almacén de alimento.

    La configuración de saldo inicial se interpreta como el
    cierre validado mediante MB5B en initial_stock_date.

    Por ese motivo solamente se aplican movimientos posteriores:

        fecha > initial_stock_date

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        - stock diario por material;
        - stock diario global del almacén.
    """

    (
        center,
        warehouse,
        feed_materials,
        initial_date,
        initial_stock,
    ) = _read_stock_configuration(
        config
    )

    prepared_kardex = _prepare_kardex(
        kardex
    )

    scope = prepared_kardex.loc[
        prepared_kardex["centro"].eq(
            center
        )
        & prepared_kardex["almacen"].eq(
            warehouse
        )
        & prepared_kardex["material"].isin(
            feed_materials
        )
    ].copy()

    movements = scope.loc[
        scope["fecha"].gt(
            initial_date
        )
    ].copy()

    if movements.empty:
        end_date = initial_date

        aggregated = pd.DataFrame(
            columns=[
                "fecha",
                "material",
            ]
        )

    else:
        movements = _add_movement_components(
            movements
        )

        end_date = pd.Timestamp(
            movements["fecha"].max()
        )

        aggregated = (
            _aggregate_daily_movements(
                movements
            )
        )

    calendar = _build_calendar(
        initial_date=initial_date,
        end_date=end_date,
        feed_materials=feed_materials,
    )

    stock = calendar.merge(
        aggregated,
        on=[
            "fecha",
            "material",
        ],
        how="left",
        validate="one_to_one",
    )

    numeric_columns = [
        "entrada_101_we_kg",
        "reversa_102_we_kg",
        "consumo_261_kg",
        "reversa_consumo_262_kg",
        "consumo_neto_fuente_kg",
        "consumo_neto_calculado_kg",
        "otros_movimientos_stock_kg",
        "movimiento_stock_kg",
        "movimiento_stock_reconstruido_kg",
    ]

    for column in numeric_columns:
        if column not in stock.columns:
            stock[column] = 0.0

        stock[column] = pd.to_numeric(
            stock[column],
            errors="coerce",
        ).fillna(0.0)

    text_columns = [
        "movimientos_sap",
        "eventos_sap",
        "roles_sap",
        "ordenes_sap",
        "documentos_sap",
    ]

    for column in text_columns:
        if column not in stock.columns:
            stock[column] = ""

        stock[column] = (
            stock[column]
            .fillna("")
            .astype(str)
        )

    stock["fase_alimento"] = (
        stock["material"]
        .map(feed_materials)
    )

    stock["fecha_saldo_inicial"] = (
        initial_date
    )

    stock["es_fecha_saldo_inicial"] = (
        stock["fecha"].eq(
            initial_date
        )
    )

    stock_material = (
        _reconstruct_stock_by_material(
            stock=stock,
            initial_stock=initial_stock,
        )
    )

    stock_global = _build_global_stock(
        stock_material=stock_material,
        initial_date=initial_date,
    )

    stock_material = (
        stock_material
        .sort_values(
            [
                "material",
                "fecha",
            ]
        )
        .reset_index(drop=True)
    )

    stock_global = (
        stock_global
        .sort_values("fecha")
        .reset_index(drop=True)
    )

    return (
        stock_material,
        stock_global,
    )

