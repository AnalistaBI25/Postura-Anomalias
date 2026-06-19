
from __future__ import annotations

from typing import Final

import pandas as pd

from .config import ProjectConfig
from .productivity import build_productivity_outputs
from .utils import compact_unique


# ============================================================
# Contratos mínimos de entrada
# ============================================================

CYCLE_REQUIRED_COLUMNS: Final[set[str]] = {
    "cycle_id",
    "centro",
    "caseta",
    "lote",
    "orden_operativa",
    "estado_ciclo",
    "aves_iniciales",
    "fecha_inicio_ciclo",
    "fecha_corte_analisis",
}

KARDEX_REQUIRED_COLUMNS: Final[set[str]] = {
    "fecha",
    "centro",
    "almacen",
    "material",
    "lote",
    "orden",
    "rol_movimiento",
    "cantidad_unidades",
    "movimiento_aves_neto",
    "consumo_alimento_neto_kg",
    "produccion_neta_kg",
    "clase_movimiento",
    "clase_transaccion_evento",
}

EPSILON: Final[float] = 1e-9


# ============================================================
# Validaciones generales
# ============================================================

def _require_dataframe(
    frame: pd.DataFrame,
    frame_name: str,
) -> None:
    """
    Valida que el objeto recibido sea un DataFrame no vacío.
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
    Valida las columnas mínimas de un DataFrame.
    """

    missing = sorted(
        required.difference(frame.columns)
    )

    if missing:
        raise ValueError(
            f"Faltan columnas requeridas en "
            f"{frame_name}: {missing}"
        )


def _prepare_cycles(
    cycles: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normaliza y valida el catálogo de ciclos.
    """

    _require_dataframe(
        cycles,
        "cycles",
    )

    _require_columns(
        cycles,
        CYCLE_REQUIRED_COLUMNS,
        "cycles",
    )

    prepared = cycles.copy()

    prepared["fecha_inicio_ciclo"] = pd.to_datetime(
        prepared["fecha_inicio_ciclo"],
        errors="coerce",
    )

    prepared["fecha_corte_analisis"] = pd.to_datetime(
        prepared["fecha_corte_analisis"],
        errors="coerce",
    )

    invalid_dates = (
        prepared["fecha_inicio_ciclo"].isna()
        | prepared["fecha_corte_analisis"].isna()
    )

    if invalid_dates.any():
        sample = (
            prepared.loc[
                invalid_dates,
                [
                    "cycle_id",
                    "fecha_inicio_ciclo",
                    "fecha_corte_analisis",
                ],
            ]
            .head(10)
            .to_dict("records")
        )

        raise ValueError(
            "Existen ciclos con fechas inválidas. "
            f"Ejemplos: {sample}"
        )

    invalid_range = (
        prepared["fecha_corte_analisis"]
        < prepared["fecha_inicio_ciclo"]
    )

    if invalid_range.any():
        sample = (
            prepared.loc[
                invalid_range,
                [
                    "cycle_id",
                    "fecha_inicio_ciclo",
                    "fecha_corte_analisis",
                ],
            ]
            .head(10)
            .to_dict("records")
        )

        raise ValueError(
            "La fecha de corte no puede ser anterior "
            "al inicio del ciclo. "
            f"Ejemplos: {sample}"
        )

    prepared["aves_iniciales"] = pd.to_numeric(
        prepared["aves_iniciales"],
        errors="coerce",
    )

    if prepared["aves_iniciales"].isna().any():
        raise ValueError(
            "Existen ciclos sin una cantidad válida "
            "de aves iniciales."
        )

    if prepared["aves_iniciales"].lt(0).any():
        raise ValueError(
            "Las aves iniciales no pueden ser negativas."
        )

    duplicated = prepared["cycle_id"].duplicated(
        keep=False
    )

    if duplicated.any():
        cycle_ids = (
            prepared.loc[
                duplicated,
                "cycle_id",
            ]
            .astype(str)
            .unique()
            .tolist()
        )

        raise ValueError(
            "Existen cycle_id duplicados: "
            f"{cycle_ids[:10]}"
        )

    return (
        prepared
        .sort_values(
            [
                "centro",
                "caseta",
                "fecha_inicio_ciclo",
            ]
        )
        .reset_index(drop=True)
    )


def _prepare_kardex(
    kardex: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normaliza y valida el kardex previamente clasificado.
    """

    _require_dataframe(
        kardex,
        "kardex",
    )

    _require_columns(
        kardex,
        KARDEX_REQUIRED_COLUMNS,
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

    numeric_columns = [
        "cantidad_unidades",
        "movimiento_aves_neto",
        "consumo_alimento_neto_kg",
        "produccion_neta_kg",
    ]

    for column in numeric_columns:
        prepared[column] = pd.to_numeric(
            prepared[column],
            errors="coerce",
        ).fillna(0.0)

    key_columns = [
        "centro",
        "almacen",
        "material",
        "lote",
        "orden",
        "rol_movimiento",
        "clase_movimiento",
        "clase_transaccion_evento",
    ]

    for column in key_columns:
        prepared[column] = (
            prepared[column]
            .astype("string")
            .str.strip()
        )

    return (
        prepared
        .sort_values("fecha")
        .reset_index(drop=True)
    )


# ============================================================
# Helpers de agregación diaria
# ============================================================

def _daily_aggregate(
    subset: pd.DataFrame,
    date_index: pd.DataFrame,
    value_columns: dict[
        str,
        tuple[str, str],
    ],
) -> pd.DataFrame:
    """
    Agrega columnas numéricas por fecha y completa días sin datos.

    Parameters
    ----------
    subset:
        Movimientos SAP correspondientes al proceso.

    date_index:
        Calendario completo del ciclo.

    value_columns:
        Diccionario:
        {
            "columna_salida": (
                "columna_fuente",
                "funcion_agregacion",
            )
        }
    """

    result = date_index.copy()

    if subset.empty:
        for output_column in value_columns:
            result[output_column] = 0.0

        return result

    aggregation = {
        output: pd.NamedAgg(
            column=source,
            aggfunc=agg_function,
        )
        for output, (
            source,
            agg_function,
        ) in value_columns.items()
    }

    daily = (
        subset
        .groupby(
            "fecha",
            as_index=False,
        )
        .agg(**aggregation)
    )

    result = result.merge(
        daily,
        on="fecha",
        how="left",
        validate="one_to_one",
    )

    for output_column in value_columns:
        result[output_column] = pd.to_numeric(
            result[output_column],
            errors="coerce",
        ).fillna(0.0)

    return result


def _absolute_sum_by_role(
    rows: pd.DataFrame,
    role: str,
) -> pd.Series:
    """
    Suma por fecha las cantidades absolutas de un rol SAP.
    """

    selected = rows.loc[
        rows["rol_movimiento"].eq(role)
    ]

    if selected.empty:
        return pd.Series(
            dtype="float64"
        )

    return (
        selected
        .groupby("fecha")[
            "cantidad_unidades"
        ]
        .apply(
            lambda values: (
                pd.to_numeric(
                    values,
                    errors="coerce",
                )
                .fillna(0.0)
                .abs()
                .sum()
            )
        )
    )


def _compact_daily_summary(
    rows: pd.DataFrame,
    source_column: str,
) -> pd.Series:
    """
    Crea un resumen compacto y único por fecha.
    """

    if (
        rows.empty
        or source_column not in rows.columns
    ):
        return pd.Series(
            dtype="object"
        )

    return (
        rows
        .groupby("fecha")[source_column]
        .agg(compact_unique)
    )


def _has_valid_order(
    order_value: object,
) -> bool:
    """
    Determina si una orden operativa es válida.
    """

    if pd.isna(order_value):
        return False

    text = str(order_value).strip()

    return (
        bool(text)
        and text.lower()
        not in {
            "nan",
            "none",
            "<na>",
        }
    )


# ============================================================
# Construcción de aves
# ============================================================

def _build_bird_daily(
    bird_rows: pd.DataFrame,
    dates: pd.DataFrame,
    initial_birds: float,
) -> pd.DataFrame:
    """
    Reconstruye diariamente:

    - movimientos netos de aves;
    - mortalidad;
    - reversas de mortalidad;
    - aves disponibles;
    - fuente utilizada para el saldo.
    """

    birds = _daily_aggregate(
        subset=bird_rows,
        date_index=dates,
        value_columns={
            "movimiento_aves_neto_dia": (
                "movimiento_aves_neto",
                "sum",
            ),
        },
    )

    mortality = _absolute_sum_by_role(
        bird_rows,
        "MORTALIDAD",
    )

    mortality_reverse = _absolute_sum_by_role(
        bird_rows,
        "MORTALIDAD_REVERSA",
    )

    birds["mortalidad_bruta_dia"] = (
        birds["fecha"]
        .map(mortality)
        .fillna(0.0)
    )

    birds["mortalidad_reversa_dia"] = (
        birds["fecha"]
        .map(mortality_reverse)
        .fillna(0.0)
    )

    birds["mortalidad_dia"] = (
        birds["mortalidad_bruta_dia"]
        - birds["mortalidad_reversa_dia"]
    )

    movement_balance = (
        birds["movimiento_aves_neto_dia"]
        .cumsum()
    )

    # Si el kardex contiene la entrada inicial de aves,
    # el saldo acumulado debe ser positivo.
    if movement_balance.max() > EPSILON:
        birds["aves_disponibles"] = (
            movement_balance.clip(lower=0.0)
        )

        birds["fuente_saldo_aves"] = (
            "movimientos_sap"
        )

    else:
        # Respaldo cuando la extracción no contiene la entrada
        # inicial pero sí se conoce el número de aves del ciclo.
        birds["aves_disponibles"] = (
            initial_birds
            + birds[
                "movimiento_aves_neto_dia"
            ].cumsum()
        ).clip(lower=0.0)

        birds["fuente_saldo_aves"] = (
            "aves_iniciales_mas_movimientos"
        )

    return birds


# ============================================================
# Construcción de alimento
# ============================================================

def _build_feed_daily(
    feed_rows: pd.DataFrame,
    dates: pd.DataFrame,
    feed_materials: dict[str, str],
) -> pd.DataFrame:
    """
    Reconstruye el consumo diario por orden y por fase.

    El consumo conserva su signo neto:
    261 WA - 262 WA.
    """

    feed_daily = _daily_aggregate(
        subset=feed_rows,
        date_index=dates,
        value_columns={
            "consumo_real_kg_dia": (
                "consumo_alimento_neto_kg",
                "sum",
            ),
        },
    )

    phase_columns: list[str] = []

    for material, phase_name in feed_materials.items():
        phase_column = (
            f"consumo_{material}_kg_dia"
        )

        phase_columns.append(
            phase_column
        )

        material_values = (
            feed_rows.loc[
                feed_rows["material"].eq(
                    material
                )
            ]
            .groupby("fecha")[
                "consumo_alimento_neto_kg"
            ]
            .sum()
        )

        feed_daily[phase_column] = (
            feed_daily["fecha"]
            .map(material_values)
            .fillna(0.0)
        )

    absolute_phase_values = (
        feed_daily[phase_columns]
        .abs()
    )

    feed_daily["fases_activas_dia"] = (
        absolute_phase_values
        .gt(EPSILON)
        .sum(axis=1)
    )

    primary_phase_column = (
        absolute_phase_values
        .idxmax(axis=1)
    )

    phase_name_map = {
        f"consumo_{material}_kg_dia": phase_name
        for material, phase_name
        in feed_materials.items()
    }

    phase_material_map = {
        f"consumo_{material}_kg_dia": material
        for material in feed_materials
    }

    feed_daily["fase_alimento_principal"] = (
        primary_phase_column
        .map(phase_name_map)
        .astype("string")
    )

    feed_daily["material_alimento_principal"] = (
        primary_phase_column
        .map(phase_material_map)
        .astype("string")
    )

    without_consumption = (
        absolute_phase_values
        .sum(axis=1)
        .le(EPSILON)
    )

    feed_daily.loc[
        without_consumption,
        [
            "fase_alimento_principal",
            "material_alimento_principal",
        ],
    ] = pd.NA

    feed_daily["es_transicion_fase"] = (
        feed_daily[
            "fases_activas_dia"
        ]
        .gt(1)
    )

    return feed_daily


# ============================================================
# Construcción de producción
# ============================================================

def _build_production_daily(
    production_rows: pd.DataFrame,
    dates: pd.DataFrame,
    production_materials: dict[str, str],
) -> pd.DataFrame:
    """
    Reconstruye la producción neta por orden y material.
    """

    production_daily = _daily_aggregate(
        subset=production_rows,
        date_index=dates,
        value_columns={
            "produccion_real_kg_dia": (
                "produccion_neta_kg",
                "sum",
            ),
        },
    )

    production_columns: list[str] = []

    for material, description in (
        production_materials.items()
    ):
        production_column = (
            f"produccion_{material}_kg_dia"
        )

        production_columns.append(
            production_column
        )

        material_values = (
            production_rows.loc[
                production_rows[
                    "material"
                ].eq(material)
            ]
            .groupby("fecha")[
                "produccion_neta_kg"
            ]
            .sum()
        )

        production_daily[
            production_column
        ] = (
            production_daily["fecha"]
            .map(material_values)
            .fillna(0.0)
        )

    production_daily[
        "tipos_huevo_activos_dia"
    ] = (
        production_daily[
            production_columns
        ]
        .abs()
        .gt(EPSILON)
        .sum(axis=1)
    )

    return production_daily


# ============================================================
# Contexto auditable SAP
# ============================================================

def _add_sap_context(
    daily: pd.DataFrame,
    kardex: pd.DataFrame,
    cycle: object,
    has_order: bool,
) -> pd.DataFrame:
    """
    Agrega códigos y contexto SAP por fecha.

    Se incluyen:
    - movimientos;
    - eventos;
    - materiales;
    - documentos, cuando estén disponibles;
    - órdenes observadas.
    """

    date_mask = kardex["fecha"].between(
        cycle.fecha_inicio_ciclo,
        cycle.fecha_corte_analisis,
    )

    biological_mask = (
        kardex["centro"].eq(
            str(cycle.centro)
        )
        & kardex["almacen"].eq(
            str(cycle.caseta)
        )
        & kardex["lote"].eq(
            str(cycle.lote)
        )
    )

    if has_order:
        order_mask = (
            kardex["centro"].eq(
                str(cycle.centro)
            )
            & kardex["orden"].eq(
                str(cycle.orden_operativa)
            )
        )

        scope_mask = (
            biological_mask
            | order_mask
        )

    else:
        scope_mask = biological_mask

    context = kardex.loc[
        date_mask & scope_mask
    ].copy()

    summaries = {
        "movimientos_sap_dia": (
            "clase_movimiento"
        ),
        "eventos_sap_dia": (
            "clase_transaccion_evento"
        ),
        "materiales_sap_dia": (
            "material"
        ),
        "ordenes_sap_dia": (
            "orden"
        ),
    }

    optional_document_columns = [
        "documento_material",
        "documento",
        "numero_documento",
    ]

    document_column = next(
        (
            column
            for column
            in optional_document_columns
            if column in context.columns
        ),
        None,
    )

    if document_column is not None:
        summaries[
            "documentos_sap_dia"
        ] = document_column

    for output_column, source_column in (
        summaries.items()
    ):
        summary = _compact_daily_summary(
            context,
            source_column,
        )

        daily[output_column] = (
            daily["fecha"]
            .map(summary)
            .fillna("")
        )

    if "documentos_sap_dia" not in daily:
        daily["documentos_sap_dia"] = ""

    return daily


# ============================================================
# Construcción de hechos diarios SAP
# ============================================================

def build_daily_facts(
    cycles: pd.DataFrame,
    kardex: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    """
    Construye una fila diaria por ciclo exclusivamente desde SAP.

    Este método no calcula:
    - política;
    - brechas;
    - ICA;
    - evaluación productiva.

    Esos cálculos pertenecen a productivity.py.
    """

    prepared_cycles = _prepare_cycles(
        cycles
    )

    prepared_kardex = _prepare_kardex(
        kardex
    )

    feed_materials = {
        str(material): str(phase)
        for material, phase
        in config.sap[
            "feed_materials"
        ].items()
    }

    production_materials = {
        str(material): str(description)
        for material, description
        in config.sap[
            "production_materials"
        ].items()
    }

    bird_material = str(
        config.sap["bird_material"]
    )

    initial_week = int(
        config.project[
            "initial_age_week"
        ]
    )

    initial_day = int(
        config.project[
            "initial_age_day"
        ]
    )

    all_daily: list[pd.DataFrame] = []

    for cycle in prepared_cycles.itertuples(
        index=False
    ):
        start_date = pd.Timestamp(
            cycle.fecha_inicio_ciclo
        )

        end_date = pd.Timestamp(
            cycle.fecha_corte_analisis
        )

        dates = pd.DataFrame({
            "fecha": pd.date_range(
                start=start_date,
                end=end_date,
                freq="D",
            )
        })

        daily = dates.copy()

        has_order = _has_valid_order(
            cycle.orden_operativa
        )

        # ----------------------------------------------------
        # Identificación del ciclo
        # ----------------------------------------------------

        daily["cycle_id"] = str(
            cycle.cycle_id
        )

        daily["centro"] = str(
            cycle.centro
        )

        daily["caseta"] = str(
            cycle.caseta
        )

        daily["lote"] = str(
            cycle.lote
        )

        daily["orden_operativa"] = (
            str(cycle.orden_operativa)
            if has_order
            else pd.NA
        )

        daily["estado_ciclo"] = str(
            cycle.estado_ciclo
        )

        daily["aves_iniciales"] = float(
            cycle.aves_iniciales
        )

        daily["fecha_inicio_ciclo"] = (
            start_date
        )

        daily["fecha_corte_analisis"] = (
            end_date
        )

        daily["tiene_orden_operativa"] = (
            has_order
        )

        daily["ciclo_sin_orden_operativa"] = (
            not has_order
        )

        # ----------------------------------------------------
        # Aves
        # ----------------------------------------------------

        bird_rows = prepared_kardex.loc[
            prepared_kardex["centro"].eq(
                str(cycle.centro)
            )
            & prepared_kardex["almacen"].eq(
                str(cycle.caseta)
            )
            & prepared_kardex["lote"].eq(
                str(cycle.lote)
            )
            & prepared_kardex["material"].eq(
                bird_material
            )
            & prepared_kardex["fecha"].between(
                start_date,
                end_date,
            )
        ].copy()

        bird_daily = _build_bird_daily(
            bird_rows=bird_rows,
            dates=dates,
            initial_birds=float(
                cycle.aves_iniciales
            ),
        )

        daily = daily.merge(
            bird_daily,
            on="fecha",
            how="left",
            validate="one_to_one",
        )

        # ----------------------------------------------------
        # Alimento y producción por orden
        # ----------------------------------------------------

        if has_order:
            order_mask = (
                prepared_kardex["centro"].eq(
                    str(cycle.centro)
                )
                & prepared_kardex["orden"].eq(
                    str(cycle.orden_operativa)
                )
                & prepared_kardex[
                    "fecha"
                ].between(
                    start_date,
                    end_date,
                )
            )

            feed_rows = prepared_kardex.loc[
                order_mask
                & prepared_kardex[
                    "material"
                ].isin(
                    feed_materials
                )
            ].copy()

            production_rows = (
                prepared_kardex.loc[
                    order_mask
                    & prepared_kardex[
                        "material"
                    ].isin(
                        production_materials
                    )
                ]
                .copy()
            )

        else:
            feed_rows = (
                prepared_kardex
                .iloc[0:0]
                .copy()
            )

            production_rows = (
                prepared_kardex
                .iloc[0:0]
                .copy()
            )

        feed_daily = _build_feed_daily(
            feed_rows=feed_rows,
            dates=dates,
            feed_materials=feed_materials,
        )

        daily = daily.merge(
            feed_daily,
            on="fecha",
            how="left",
            validate="one_to_one",
        )

        production_daily = (
            _build_production_daily(
                production_rows=production_rows,
                dates=dates,
                production_materials=(
                    production_materials
                ),
            )
        )

        daily = daily.merge(
            production_daily,
            on="fecha",
            how="left",
            validate="one_to_one",
        )

        # ----------------------------------------------------
        # Edad biológica
        # ----------------------------------------------------

        days_from_start = (
            daily["fecha"]
            - start_date
        ).dt.days.astype(int)

        total_age_days = (
            initial_week * 7
            + initial_day
            + days_from_start
        )

        daily["dias_desde_inicio"] = (
            days_from_start
        )

        daily["edad_semana"] = (
            total_age_days // 7
        ).astype(int)

        daily["edad_dia_semana"] = (
            total_age_days % 7
        ).astype(int)

        # ----------------------------------------------------
        # Contexto SAP
        # ----------------------------------------------------

        daily = _add_sap_context(
            daily=daily,
            kardex=prepared_kardex,
            cycle=cycle,
            has_order=has_order,
        )

        # ----------------------------------------------------
        # Indicadores de asignación
        # ----------------------------------------------------

        daily["consumo_asignado_por_orden"] = (
            has_order
            & daily[
                "consumo_real_kg_dia"
            ]
            .abs()
            .gt(EPSILON)
        )

        daily["produccion_asignada_por_orden"] = (
            has_order
            & daily[
                "produccion_real_kg_dia"
            ]
            .abs()
            .gt(EPSILON)
        )

        all_daily.append(
            daily
        )

    daily_facts = pd.concat(
        all_daily,
        ignore_index=True,
    )

    duplicated = daily_facts.duplicated(
        [
            "cycle_id",
            "fecha",
        ],
        keep=False,
    )

    if duplicated.any():
        sample = (
            daily_facts.loc[
                duplicated,
                [
                    "cycle_id",
                    "fecha",
                ],
            ]
            .head(10)
            .to_dict("records")
        )

        raise ValueError(
            "La reconstrucción generó filas duplicadas "
            "por ciclo y fecha. "
            f"Ejemplos: {sample}"
        )

    return (
        daily_facts
        .sort_values(
            [
                "cycle_id",
                "fecha",
            ]
        )
        .reset_index(drop=True)
    )


# ============================================================
# API pública compatible con el pipeline actual
# ============================================================

def build_daily_cycles(
    cycles: pd.DataFrame,
    kardex: pd.DataFrame,
    standard: pd.DataFrame,
    config: ProjectConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Construye los hechos SAP diarios y después aplica política.

    Se conserva la firma pública del proyecto anterior:

    daily, weekly = build_daily_cycles(
        cycles,
        kardex,
        standard,
        config,
    )

    Internamente, las responsabilidades están separadas:

    1. build_daily_facts():
       reconstrucción diaria desde SAP.

    2. build_productivity_outputs():
       política, brechas, preproducción e ICA.
    """

    daily_facts = build_daily_facts(
        cycles=cycles,
        kardex=kardex,
        config=config,
    )

    daily_productivity, weekly_productivity = (
        build_productivity_outputs(
            daily_facts=daily_facts,
            standard=standard,
            config=config,
        )
    )

    return (
        daily_productivity,
        weekly_productivity,
    )

