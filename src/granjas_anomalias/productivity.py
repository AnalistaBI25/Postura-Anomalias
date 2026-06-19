
from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd

from .config import ProjectConfig
from .utils import safe_divide


# ============================================================
# Contratos de entrada
# ============================================================

DAILY_REQUIRED_COLUMNS: Final[set[str]] = {
    "cycle_id",
    "fecha",
    "centro",
    "caseta",
    "lote",
    "orden_operativa",
    "estado_ciclo",
    "aves_iniciales",
    "aves_disponibles",
    "mortalidad_dia",
    "consumo_real_kg_dia",
    "produccion_real_kg_dia",
    "edad_semana",
    "edad_dia_semana",
}

STANDARD_REQUIRED_COLUMNS: Final[set[str]] = {
    "semana_edad",
    "consumo_g_ave_dia",
    "produccion_pct_ave_dia",
    "peso_huevo_g",
    "mortalidad_pct_acum",
    "ica_sap",
    "ica_estandar_principal",
}

WEEKLY_GROUP_COLUMNS: Final[list[str]] = [
    "cycle_id",
    "centro",
    "caseta",
    "lote",
    "orden_operativa",
    "estado_ciclo",
    "edad_semana",
]


# ============================================================
# Configuración productiva
# ============================================================

@dataclass(frozen=True)
class ProductivitySettings:
    """
    Parámetros utilizados para evaluar producción e ICA.

    Los valores pueden definirse en la configuración bajo una
    sección ``productivity``. Si esa sección no existe, se usan
    valores predeterminados.
    """

    minimum_production_ratio_for_ica: float = 0.30
    use_daily_ica_on_first_production_day: bool = True
    epsilon_kg: float = 1e-9

    @classmethod
    def from_config(
        cls,
        config: ProjectConfig,
    ) -> "ProductivitySettings":
        """
        Construye la configuración productiva desde ProjectConfig.

        Funciona tanto con configuraciones que tienen ``raw``
        como con versiones anteriores que solamente contienen
        los atributos ``project`` y ``sap``.
        """

        raw_config = getattr(
            config,
            "raw",
            {},
        )

        if not isinstance(raw_config, dict):
            raw_config = {}

        project_config = getattr(
            config,
            "project",
            {},
        )

        if not isinstance(project_config, dict):
            project_config = {}

        productivity_config = raw_config.get(
            "productivity",
            {},
        )

        if not isinstance(
            productivity_config,
            dict,
        ):
            productivity_config = {}

        minimum_ratio = float(
            productivity_config.get(
                "minimum_production_ratio_for_ica",
                project_config.get(
                    "minimum_production_ratio_for_ica",
                    0.30,
                ),
            )
        )

        use_daily_start = bool(
            productivity_config.get(
                "use_daily_ica_on_first_production_day",
                True,
            )
        )

        epsilon = float(
            productivity_config.get(
                "epsilon_kg",
                1e-9,
            )
        )

        if not 0 <= minimum_ratio <= 1:
            raise ValueError(
                "minimum_production_ratio_for_ica "
                "debe estar entre 0 y 1."
            )

        if epsilon <= 0:
            raise ValueError(
                "epsilon_kg debe ser mayor que cero."
            )

        return cls(
            minimum_production_ratio_for_ica=minimum_ratio,
            use_daily_ica_on_first_production_day=use_daily_start,
            epsilon_kg=epsilon,
        )



    


# ============================================================
# Validaciones internas
# ============================================================

def _require_columns(
    frame: pd.DataFrame,
    required: set[str],
    frame_name: str,
) -> None:
    """
    Valida que un DataFrame contenga las columnas requeridas.
    """

    missing = sorted(
        required.difference(frame.columns)
    )

    if missing:
        raise ValueError(
            f"Faltan columnas requeridas en "
            f"{frame_name}: {missing}"
        )


def _prepare_daily_facts(
    daily_facts: pd.DataFrame,
) -> pd.DataFrame:
    """
    Valida y normaliza los hechos diarios producidos por daily.py.
    """

    if not isinstance(
        daily_facts,
        pd.DataFrame,
    ):
        raise TypeError(
            "daily_facts debe ser un pandas.DataFrame."
        )

    if daily_facts.empty:
        raise ValueError(
            "daily_facts está vacío."
        )

    _require_columns(
        daily_facts,
        DAILY_REQUIRED_COLUMNS,
        "daily_facts",
    )

    daily = daily_facts.copy()

    daily["fecha"] = pd.to_datetime(
        daily["fecha"],
        errors="coerce",
    )

    if daily["fecha"].isna().any():
        invalid = int(
            daily["fecha"].isna().sum()
        )

        raise ValueError(
            "daily_facts contiene "
            f"{invalid} fecha(s) inválida(s)."
        )

    duplicated = daily.duplicated(
        ["cycle_id", "fecha"],
        keep=False,
    )

    if duplicated.any():
        sample = (
            daily.loc[
                duplicated,
                ["cycle_id", "fecha"],
            ]
            .head(10)
            .to_dict("records")
        )

        raise ValueError(
            "daily_facts contiene más de una fila "
            "por ciclo y fecha. "
            f"Ejemplos: {sample}"
        )

    numeric_columns = [
        "aves_iniciales",
        "aves_disponibles",
        "mortalidad_dia",
        "consumo_real_kg_dia",
        "produccion_real_kg_dia",
        "edad_semana",
        "edad_dia_semana",
    ]

    for column in numeric_columns:
        daily[column] = pd.to_numeric(
            daily[column],
            errors="coerce",
        )

    if daily[
        [
            "edad_semana",
            "edad_dia_semana",
        ]
    ].isna().any().any():
        raise ValueError(
            "daily_facts contiene edades nulas "
            "o no numéricas."
        )

    daily["edad_semana"] = (
        daily["edad_semana"]
        .astype(int)
    )

    daily["edad_dia_semana"] = (
        daily["edad_dia_semana"]
        .astype(int)
    )

    daily["aves_iniciales"] = (
        daily["aves_iniciales"]
        .clip(lower=0)
    )

    daily["aves_disponibles"] = (
        daily["aves_disponibles"]
        .clip(lower=0)
    )

    daily["mortalidad_dia"] = (
        daily["mortalidad_dia"]
        .fillna(0.0)
    )

    daily["consumo_real_kg_dia"] = (
        daily["consumo_real_kg_dia"]
        .fillna(0.0)
    )

    daily["produccion_real_kg_dia"] = (
        daily["produccion_real_kg_dia"]
        .fillna(0.0)
    )

    return (
        daily
        .sort_values(
            ["cycle_id", "fecha"]
        )
        .reset_index(drop=True)
    )


def _prepare_standard_for_merge(
    standard: pd.DataFrame,
) -> pd.DataFrame:
    """
    Valida la política preparada antes de cruzarla con los ciclos.
    """

    if not isinstance(
        standard,
        pd.DataFrame,
    ):
        raise TypeError(
            "standard debe ser un pandas.DataFrame."
        )

    if standard.empty:
        raise ValueError(
            "standard está vacío."
        )

    _require_columns(
        standard,
        STANDARD_REQUIRED_COLUMNS,
        "standard",
    )

    policy = standard.copy()

    policy["semana_edad"] = pd.to_numeric(
        policy["semana_edad"],
        errors="coerce",
    )

    policy = (
        policy
        .dropna(
            subset=["semana_edad"]
        )
        .copy()
    )

    policy["semana_edad"] = (
        policy["semana_edad"]
        .astype(int)
    )

    duplicated = (
        policy["semana_edad"]
        .duplicated(keep=False)
    )

    if duplicated.any():
        weeks = sorted(
            policy.loc[
                duplicated,
                "semana_edad",
            ].unique()
        )

        raise ValueError(
            "standard contiene semanas duplicadas "
            "después de normalizar: "
            f"{weeks}"
        )

    return (
        policy
        .sort_values("semana_edad")
        .reset_index(drop=True)
    )


def _merge_policy(
    daily: pd.DataFrame,
    standard: pd.DataFrame,
) -> pd.DataFrame:
    """
    Cruza la política por semana de edad.

    La operación es idempotente: puede ejecutarse nuevamente
    aunque el DataFrame ya contenga columnas de política.
    """

    policy_columns = [
        column
        for column in standard.columns
        if column != "semana_edad"
    ]

    columns_to_drop = [
        column
        for column in [
            "semana_edad",
            *policy_columns,
        ]
        if column in daily.columns
    ]

    clean_daily = daily.drop(
        columns=columns_to_drop,
        errors="ignore",
    )

    merged = clean_daily.merge(
        standard,
        left_on="edad_semana",
        right_on="semana_edad",
        how="left",
        validate="many_to_one",
    )

    merged["politica_disponible"] = (
        merged[
            [
                "consumo_g_ave_dia",
                "produccion_pct_ave_dia",
                "peso_huevo_g",
                "ica_estandar_principal",
            ]
        ]
        .notna()
        .any(axis=1)
    )

    return merged


# ============================================================
# Enriquecimiento diario
# ============================================================

def enrich_daily_productivity(
    daily_facts: pd.DataFrame,
    standard: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    """
    Enriquece la línea diaria SAP con política e indicadores.

    Este módulo no reconstruye movimientos SAP. Recibe los hechos
    diarios generados por daily.py y calcula:

    - consumo esperado;
    - producción esperada;
    - mortalidad esperada;
    - acumulados reales y esperados;
    - primera producción;
    - preproducción;
    - periodo productivo;
    - ICA diario de referencia;
    - ICA semanal acumulado hasta cada fecha;
    - brechas contra política;
    - estado de evaluación del ICA.
    """

    settings = ProductivitySettings.from_config(
        config
    )

    daily = _prepare_daily_facts(
        daily_facts
    )

    policy = _prepare_standard_for_merge(
        standard
    )

    daily = _merge_policy(
        daily,
        policy,
    )

    numeric_policy_columns = [
        "consumo_g_ave_dia",
        "produccion_pct_ave_dia",
        "peso_huevo_g",
        "mortalidad_pct_acum",
        "ica_sap",
        "ica_estandar_principal",
    ]

    for column in numeric_policy_columns:
        daily[column] = pd.to_numeric(
            daily[column],
            errors="coerce",
        )

    birds_available = (
        daily["aves_disponibles"]
        .clip(lower=0)
    )

    birds_initial = (
        daily["aves_iniciales"]
        .clip(lower=0)
    )

    # --------------------------------------------------------
    # Valores esperados diarios
    # --------------------------------------------------------

    daily["consumo_estandar_kg_dia"] = (
        birds_available
        * daily["consumo_g_ave_dia"]
        / 1000.0
    )

    daily["produccion_estandar_kg_dia"] = (
        birds_available
        * daily["produccion_pct_ave_dia"]
        / 100.0
        * daily["peso_huevo_g"]
        / 1000.0
    )

    daily["mortalidad_estandar_acum_aves"] = (
        birds_initial
        * daily["mortalidad_pct_acum"]
        / 100.0
    )

    grouped_cycle = daily.groupby(
        "cycle_id",
        sort=False,
    )

    # --------------------------------------------------------
    # Acumulados reales
    # --------------------------------------------------------

    daily["consumo_real_kg_acum"] = (
        grouped_cycle[
            "consumo_real_kg_dia"
        ]
        .cumsum()
    )

    daily["produccion_real_kg_acum"] = (
        grouped_cycle[
            "produccion_real_kg_dia"
        ]
        .cumsum()
    )

    daily["mortalidad_real_acum"] = (
        grouped_cycle[
            "mortalidad_dia"
        ]
        .cumsum()
    )

    # Alias conservado para compatibilidad con el dashboard
    # y las salidas anteriores.
    daily["mortalidad_acum"] = (
        daily["mortalidad_real_acum"]
    )

    # --------------------------------------------------------
    # Acumulados esperados
    # --------------------------------------------------------

    daily["consumo_estandar_kg_acum"] = (
        daily["consumo_estandar_kg_dia"]
        .fillna(0.0)
        .groupby(
            daily["cycle_id"],
            sort=False,
        )
        .cumsum()
    )

    daily["produccion_estandar_kg_acum"] = (
        daily["produccion_estandar_kg_dia"]
        .fillna(0.0)
        .groupby(
            daily["cycle_id"],
            sort=False,
        )
        .cumsum()
    )

    # --------------------------------------------------------
    # Referencias diarias
    # --------------------------------------------------------

    daily["ica_diario"] = safe_divide(
        daily["consumo_real_kg_dia"],
        daily["produccion_real_kg_dia"],
    )

    daily["ica_acumulado_referencia"] = (
        safe_divide(
            daily["consumo_real_kg_acum"],
            daily["produccion_real_kg_acum"],
        )
    )

    # --------------------------------------------------------
    # Brechas diarias
    # --------------------------------------------------------

    daily["brecha_consumo_kg_dia"] = (
        daily["consumo_real_kg_dia"]
        - daily["consumo_estandar_kg_dia"]
    )

    # Se conserva como proporción:
    # 0.15 equivale a 15 % por encima de política.
    daily["brecha_consumo_pct_dia"] = (
        safe_divide(
            daily["consumo_real_kg_dia"],
            daily["consumo_estandar_kg_dia"],
        )
        - 1.0
    )

    daily["brecha_produccion_kg_dia"] = (
        daily["produccion_real_kg_dia"]
        - daily["produccion_estandar_kg_dia"]
    )

    daily["brecha_produccion_pct_dia"] = (
        safe_divide(
            daily["produccion_real_kg_dia"],
            daily["produccion_estandar_kg_dia"],
        )
        - 1.0
    )

    daily["brecha_mortalidad_acum_aves"] = (
        daily["mortalidad_real_acum"]
        - daily["mortalidad_estandar_acum_aves"]
    )

    # --------------------------------------------------------
    # Primera producción
    # --------------------------------------------------------

    positive_production = (
        daily["produccion_real_kg_dia"]
        .gt(settings.epsilon_kg)
    )

    first_production = (
        daily.loc[
            positive_production
        ]
        .groupby("cycle_id")["fecha"]
        .min()
    )

    daily["primera_fecha_produccion"] = (
        daily["cycle_id"]
        .map(first_production)
    )

    daily["hay_produccion"] = (
        daily["primera_fecha_produccion"]
        .notna()
    )

    # En ciclos sin producción, todo el consumo existente
    # sigue siendo preproductivo.
    daily["es_preproduccion"] = (
        ~daily["hay_produccion"]
        | daily["fecha"].lt(
            daily["primera_fecha_produccion"]
        )
    )

    daily["es_primer_dia_produccion"] = (
        daily["hay_produccion"]
        & daily["fecha"].eq(
            daily["primera_fecha_produccion"]
        )
    )

    productive_mask = (
        daily["hay_produccion"]
        & daily["fecha"].ge(
            daily["primera_fecha_produccion"]
        )
    )

    # --------------------------------------------------------
    # Consumo previo al inicio de producción
    # --------------------------------------------------------

    daily["consumo_preproductivo_kg_dia"] = (
        np.where(
            daily["es_preproduccion"],
            daily["consumo_real_kg_dia"],
            0.0,
        )
    )

    daily["consumo_preproductivo_kg_acum"] = (
        daily.groupby(
            "cycle_id",
            sort=False,
        )[
            "consumo_preproductivo_kg_dia"
        ]
        .cumsum()
    )

    # --------------------------------------------------------
    # Periodo productivo
    # --------------------------------------------------------

    daily["consumo_productivo_kg_dia"] = (
        np.where(
            productive_mask,
            daily["consumo_real_kg_dia"],
            0.0,
        )
    )

    daily["produccion_productiva_kg_dia"] = (
        np.where(
            productive_mask,
            daily["produccion_real_kg_dia"],
            0.0,
        )
    )

    daily[
        "consumo_estandar_productivo_kg_dia"
    ] = np.where(
        productive_mask,
        daily[
            "consumo_estandar_kg_dia"
        ].fillna(0.0),
        0.0,
    )

    daily[
        "produccion_estandar_productiva_kg_dia"
    ] = np.where(
        productive_mask,
        daily[
            "produccion_estandar_kg_dia"
        ].fillna(0.0),
        0.0,
    )

    # --------------------------------------------------------
    # Acumulados dentro de cada semana de edad
    # --------------------------------------------------------

    week_group = daily.groupby(
        [
            "cycle_id",
            "edad_semana",
        ],
        sort=False,
    )

    daily[
        "consumo_semana_productiva_kg"
    ] = (
        week_group[
            "consumo_productivo_kg_dia"
        ]
        .cumsum()
    )

    daily[
        "produccion_semana_productiva_kg"
    ] = (
        week_group[
            "produccion_productiva_kg_dia"
        ]
        .cumsum()
    )

    daily[
        "consumo_estandar_semana_productiva_kg"
    ] = (
        week_group[
            "consumo_estandar_productivo_kg_dia"
        ]
        .cumsum()
    )

    daily[
        "produccion_estandar_semana_productiva_kg"
    ] = (
        week_group[
            "produccion_estandar_productiva_kg_dia"
        ]
        .cumsum()
    )

    # --------------------------------------------------------
    # ICA diario de arranque
    # --------------------------------------------------------

    daily["ica_arranque_diario"] = np.where(
        (
            daily["es_primer_dia_produccion"]
            & daily[
                "produccion_real_kg_dia"
            ].gt(settings.epsilon_kg)
        ),
        safe_divide(
            daily["consumo_real_kg_dia"],
            daily["produccion_real_kg_dia"],
        ),
        np.nan,
    )

    # --------------------------------------------------------
    # ICA semanal real
    # --------------------------------------------------------

    daily["ica_semanal_real"] = (
        safe_divide(
            daily[
                "consumo_semana_productiva_kg"
            ],
            daily[
                "produccion_semana_productiva_kg"
            ],
        )
    )

    daily["ica_estandar_calculado"] = (
        safe_divide(
            daily[
                "consumo_estandar_semana_productiva_kg"
            ],
            daily[
                "produccion_estandar_semana_productiva_kg"
            ],
        )
    )

    # ICA oficial SAP tiene prioridad.
    official_ica = (
        daily["ica_sap"]
        .where(
            daily["ica_sap"].gt(0)
        )
    )

    daily["ica_estandar_principal"] = (
        official_ica.fillna(
            daily["ica_estandar_calculado"]
        )
    )

    daily["ratio_produccion_vs_estandar"] = (
        safe_divide(
            daily[
                "produccion_semana_productiva_kg"
            ],
            daily[
                "produccion_estandar_semana_productiva_kg"
            ],
        )
    )

    # --------------------------------------------------------
    # Estado de evaluación
    # --------------------------------------------------------

    daily["estado_ica"] = np.select(
        [
            ~daily["hay_produccion"],
            daily["es_preproduccion"],
            daily[
                "es_primer_dia_produccion"
            ],
            daily[
                "produccion_semana_productiva_kg"
            ].le(settings.epsilon_kg),
            (
                daily[
                    "ratio_produccion_vs_estandar"
                ].notna()
                & daily[
                    "ratio_produccion_vs_estandar"
                ].lt(
                    settings
                    .minimum_production_ratio_for_ica
                )
            ),
        ],
        [
            "Sin producción registrada",
            "Preproducción: ICA no evaluable",
            "Arranque sensible",
            "No evaluable: sin producción semanal",
            "No estable: producción baja vs estándar",
        ],
        default="Evaluable: ICA semanal",
    )

    daily["ica_principal"] = np.nan

    if (
        settings
        .use_daily_ica_on_first_production_day
    ):
        daily.loc[
            daily[
                "es_primer_dia_produccion"
            ],
            "ica_principal",
        ] = daily.loc[
            daily[
                "es_primer_dia_produccion"
            ],
            "ica_arranque_diario",
        ]

    weekly_ica_mask = (
        daily["hay_produccion"]
        & ~daily["es_preproduccion"]
        & ~daily[
            "es_primer_dia_produccion"
        ]
    )

    daily.loc[
        weekly_ica_mask,
        "ica_principal",
    ] = daily.loc[
        weekly_ica_mask,
        "ica_semanal_real",
    ]

    daily["brecha_ica"] = (
        daily["ica_principal"]
        - daily["ica_estandar_principal"]
    )

    daily["brecha_ica_pct"] = (
        safe_divide(
            daily["ica_principal"],
            daily["ica_estandar_principal"],
        )
        - 1.0
    )

    daily["es_ica_evaluable"] = (
        daily["estado_ica"]
        .eq("Evaluable: ICA semanal")
    )

    return (
        daily
        .sort_values(
            ["cycle_id", "fecha"]
        )
        .reset_index(drop=True)
    )


# ============================================================
# Resumen semanal
# ============================================================

def build_weekly_productivity(
    daily_productivity: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    """
    Construye el resumen por ciclo y semana de edad.

    El ICA utiliza solamente el consumo y la producción
    registrados desde el inicio productivo.
    """

    settings = ProductivitySettings.from_config(
        config
    )

    if not isinstance(
        daily_productivity,
        pd.DataFrame,
    ):
        raise TypeError(
            "daily_productivity debe ser "
            "un pandas.DataFrame."
        )

    if daily_productivity.empty:
        raise ValueError(
            "daily_productivity está vacío."
        )

    required = {
        *WEEKLY_GROUP_COLUMNS,
        "fecha",
        "aves_iniciales",
        "aves_disponibles",
        "consumo_real_kg_dia",
        "consumo_estandar_kg_dia",
        "produccion_real_kg_dia",
        "produccion_estandar_kg_dia",
        "consumo_productivo_kg_dia",
        "produccion_productiva_kg_dia",
        "consumo_estandar_productivo_kg_dia",
        "produccion_estandar_productiva_kg_dia",
        "consumo_preproductivo_kg_dia",
        "mortalidad_dia",
        "mortalidad_estandar_acum_aves",
        "ica_sap",
        "primera_fecha_produccion",
    }

    _require_columns(
        daily_productivity,
        required,
        "daily_productivity",
    )

    weekly = (
        daily_productivity
        .sort_values(
            ["cycle_id", "fecha"]
        )
        .groupby(
            WEEKLY_GROUP_COLUMNS,
            dropna=False,
            as_index=False,
        )
        .agg(
            fecha_inicio_semana=(
                "fecha",
                "min",
            ),
            fecha_fin_semana=(
                "fecha",
                "max",
            ),
            dias_observados=(
                "fecha",
                "size",
            ),
            aves_iniciales=(
                "aves_iniciales",
                "first",
            ),
            aves_promedio=(
                "aves_disponibles",
                "mean",
            ),
            aves_fin_semana=(
                "aves_disponibles",
                "last",
            ),
            consumo_real_kg=(
                "consumo_real_kg_dia",
                "sum",
            ),
            consumo_estandar_kg=(
                "consumo_estandar_kg_dia",
                "sum",
            ),
            consumo_productivo_kg=(
                "consumo_productivo_kg_dia",
                "sum",
            ),
            consumo_estandar_productivo_kg=(
                "consumo_estandar_productivo_kg_dia",
                "sum",
            ),
            consumo_preproductivo_kg=(
                "consumo_preproductivo_kg_dia",
                "sum",
            ),
            produccion_real_kg=(
                "produccion_real_kg_dia",
                "sum",
            ),
            produccion_estandar_kg=(
                "produccion_estandar_kg_dia",
                "sum",
            ),
            produccion_productiva_kg=(
                "produccion_productiva_kg_dia",
                "sum",
            ),
            produccion_estandar_productiva_kg=(
                "produccion_estandar_productiva_kg_dia",
                "sum",
            ),
            mortalidad_real_aves=(
                "mortalidad_dia",
                "sum",
            ),
            mortalidad_estandar_fin_aves=(
                "mortalidad_estandar_acum_aves",
                "last",
            ),
            ica_estandar_sap=(
                "ica_sap",
                "last",
            ),
            primera_fecha_produccion=(
                "primera_fecha_produccion",
                "first",
            ),
        )
    )

    weekly["semana_completa"] = (
        weekly["dias_observados"]
        .ge(7)
    )

    weekly["ica_real"] = safe_divide(
        weekly["consumo_productivo_kg"],
        weekly["produccion_productiva_kg"],
    )

    weekly["ica_estandar_calculado"] = (
        safe_divide(
            weekly[
                "consumo_estandar_productivo_kg"
            ],
            weekly[
                "produccion_estandar_productiva_kg"
            ],
        )
    )

    official_ica = (
        weekly["ica_estandar_sap"]
        .where(
            weekly["ica_estandar_sap"].gt(0)
        )
    )

    weekly["ica_estandar_principal"] = (
        official_ica.fillna(
            weekly[
                "ica_estandar_calculado"
            ]
        )
    )

    weekly["ratio_produccion_vs_estandar"] = (
        safe_divide(
            weekly[
                "produccion_productiva_kg"
            ],
            weekly[
                "produccion_estandar_productiva_kg"
            ],
        )
    )

    weekly["brecha_consumo_kg"] = (
        weekly["consumo_real_kg"]
        - weekly["consumo_estandar_kg"]
    )

    weekly["brecha_consumo_pct"] = (
        safe_divide(
            weekly["consumo_real_kg"],
            weekly["consumo_estandar_kg"],
        )
        - 1.0
    )

    weekly["brecha_produccion_kg"] = (
        weekly["produccion_real_kg"]
        - weekly["produccion_estandar_kg"]
    )

    weekly["brecha_produccion_pct"] = (
        safe_divide(
            weekly["produccion_real_kg"],
            weekly["produccion_estandar_kg"],
        )
        - 1.0
    )

    weekly["brecha_mortalidad_aves"] = (
        weekly["mortalidad_real_aves"]
        - weekly[
            "mortalidad_estandar_fin_aves"
        ]
    )

    weekly["brecha_ica"] = (
        weekly["ica_real"]
        - weekly["ica_estandar_principal"]
    )

    weekly["brecha_ica_pct"] = (
        safe_divide(
            weekly["ica_real"],
            weekly["ica_estandar_principal"],
        )
        - 1.0
    )

    no_production = (
        weekly["produccion_productiva_kg"]
        .le(settings.epsilon_kg)
    )

    low_production = (
        weekly[
            "ratio_produccion_vs_estandar"
        ].notna()
        & weekly[
            "ratio_produccion_vs_estandar"
        ].lt(
            settings
            .minimum_production_ratio_for_ica
        )
    )

    missing_standard = (
        weekly[
            "ica_estandar_principal"
        ]
        .isna()
    )

    better_or_equal = (
        weekly["ica_real"]
        .le(
            weekly[
                "ica_estandar_principal"
            ]
        )
    )

    weekly["estado_ica"] = np.select(
        [
            no_production,
            low_production,
            missing_standard,
            better_or_equal,
        ],
        [
            "Preproducción / ICA no evaluable",
            "No estable: producción baja",
            "ICA calculado; estándar no disponible",
            "ICA igual o mejor que estándar",
        ],
        default="ICA por encima del estándar",
    )

    weekly["es_ica_evaluable"] = ~(
        no_production
        | low_production
        | missing_standard
    )

    return (
        weekly
        .sort_values(
            [
                "cycle_id",
                "edad_semana",
            ]
        )
        .reset_index(drop=True)
    )


# ============================================================
# API pública
# ============================================================

def build_productivity_outputs(
    daily_facts: pd.DataFrame,
    standard: pd.DataFrame,
    config: ProjectConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Devuelve la línea diaria enriquecida y el resumen semanal.

    Parameters
    ----------
    daily_facts:
        Hechos diarios construidos desde movimientos SAP.

    standard:
        Política preparada por standards.prepare_standard().

    config:
        Configuración general del proyecto.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        Línea diaria productiva y resumen semanal.
    """

    daily = enrich_daily_productivity(
        daily_facts=daily_facts,
        standard=standard,
        config=config,
    )

    weekly = build_weekly_productivity(
        daily_productivity=daily,
        config=config,
    )

    return daily, weekly

