"""Cobertura de alimento: sobrestock y riesgo de desabasto.

Trabaja sobre el stock diario reconstruido (global y por material) del único
almacén de alimento configurado. Los umbrales de días de cobertura son
provisionales y están marcados como PENDIENTE DE CONFIRMACIÓN en
docs/preguntas_pendientes.md; se parametrizan en ``coverage`` dentro de
config/project.yml.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ProjectConfig

EPSILON_KG = 1e-6

DEFAULTS = {
    "dias_cobertura_minimo": 3.0,
    "dias_cobertura_objetivo": 7.0,
    "dias_cobertura_maximo": 15.0,
    "ventana_consumo_dias": 7,
    "min_dias_historia": 3,
    "dias_sin_movimiento_alerta": 14,
}


def _parametros(config: ProjectConfig) -> dict:
    params = dict(DEFAULTS)
    params.update(config.coverage)
    return params


def _consumo_estimado(consumo: pd.Series, ventana: int, min_dias: int) -> pd.Series:
    """Consumo diario estimado: media móvil del consumo neto reciente.

    Usa solo historia previa (shift) para que el estimado del día no se
    contamine con el propio día evaluado.
    """
    return consumo.shift(1).rolling(int(ventana), min_periods=int(min_dias)).mean()


def _dias_consecutivos(flag: pd.Series) -> pd.Series:
    """Días consecutivos que la bandera lleva activa hasta cada fecha."""
    grupos = (~flag).cumsum()
    return flag.groupby(grupos).cumsum().astype(int)


def build_coverage(
    stock_material: pd.DataFrame,
    stock_global: pd.DataFrame,
    daily: pd.DataFrame,
    config: ProjectConfig,
) -> pd.DataFrame:
    """Construye la línea diaria de cobertura (nivel global y por material)."""
    params = _parametros(config)
    ventana = int(params["ventana_consumo_dias"])
    min_dias = int(params["min_dias_historia"])
    minimo = float(params["dias_cobertura_minimo"])
    objetivo = float(params["dias_cobertura_objetivo"])
    maximo = float(params["dias_cobertura_maximo"])
    sin_mov = int(params["dias_sin_movimiento_alerta"])

    aves_dia = (
        daily.groupby("fecha", as_index=False)["aves_disponibles"]
        .sum()
        .rename(columns={"aves_disponibles": "aves_activas"})
    )

    # ----- nivel global -----
    glob = stock_global.sort_values("fecha").copy()
    glob["nivel"] = "global"
    glob["material"] = "(global)"
    glob["stock_kg"] = pd.to_numeric(glob["stock_global_kg"], errors="coerce")
    glob["consumo_neto_dia_kg"] = pd.to_numeric(
        glob.get("consumo_neto_calculado_kg"), errors="coerce"
    )
    glob["entradas_dia_kg"] = pd.to_numeric(glob.get("entradas_netas_kg"), errors="coerce")
    glob["stock_apertura_kg"] = pd.to_numeric(glob.get("stock_apertura_global_kg"), errors="coerce")
    glob["stock_negativo_flag"] = glob.get("stock_negativo", False)
    glob = glob[
        [
            "fecha",
            "nivel",
            "material",
            "stock_kg",
            "stock_apertura_kg",
            "consumo_neto_dia_kg",
            "entradas_dia_kg",
            "stock_negativo_flag",
        ]
    ]

    # ----- nivel material -----
    mat = stock_material.sort_values(["material", "fecha"]).copy()
    mat["nivel"] = "material"
    mat["stock_kg"] = pd.to_numeric(mat["stock_cierre_kg"], errors="coerce")
    mat["stock_apertura_kg"] = pd.to_numeric(mat.get("stock_apertura_kg"), errors="coerce")
    mat["consumo_neto_dia_kg"] = pd.to_numeric(mat.get("consumo_neto_kg"), errors="coerce")
    mat["entradas_dia_kg"] = pd.to_numeric(mat.get("entradas_netas_kg"), errors="coerce")
    mat["stock_negativo_flag"] = mat.get("stock_negativo", False)
    mat = mat[
        [
            "fecha",
            "nivel",
            "material",
            "stock_kg",
            "stock_apertura_kg",
            "consumo_neto_dia_kg",
            "entradas_dia_kg",
            "stock_negativo_flag",
        ]
    ]

    frames = []
    for _, grupo in pd.concat([glob, mat], ignore_index=True).groupby(
        ["nivel", "material"], sort=False
    ):
        g = grupo.sort_values("fecha").copy()
        g["consumo_diario_estimado_kg"] = _consumo_estimado(
            g["consumo_neto_dia_kg"].fillna(0.0), ventana, min_dias
        )
        estimado = g["consumo_diario_estimado_kg"]
        con_consumo = estimado.gt(EPSILON_KG)

        g["dias_cobertura"] = np.where(
            con_consumo, g["stock_kg"] / estimado.where(con_consumo), np.nan
        )
        g["inventario_requerido_kg"] = np.where(con_consumo, estimado * objetivo, np.nan)
        g["exceso_estimado_kg"] = np.where(
            con_consumo,
            (g["stock_kg"] - estimado * maximo).clip(lower=0.0),
            0.0,
        )
        g["datos_insuficientes"] = estimado.isna()
        g["consumo_estimado_cero"] = estimado.notna() & ~con_consumo

        g["flag_sobrestock"] = con_consumo & g["dias_cobertura"].gt(maximo)
        g["flag_desabasto"] = (
            con_consumo & g["dias_cobertura"].lt(minimo) & g["stock_kg"].ge(0)
        )
        g["flag_stock_negativo"] = g["stock_negativo_flag"].fillna(False).astype(bool) | g[
            "stock_kg"
        ].lt(-EPSILON_KG)
        g["flag_sin_movimiento"] = (
            g["stock_kg"].gt(EPSILON_KG)
            & g["consumo_neto_dia_kg"].fillna(0.0).abs().le(EPSILON_KG)
        )
        g["dias_sin_movimiento"] = _dias_consecutivos(g["flag_sin_movimiento"])
        g["flag_sin_movimiento_alerta"] = g["dias_sin_movimiento"].ge(sin_mov)
        g["flag_consumo_mayor_que_disponible"] = (
            g["consumo_neto_dia_kg"].fillna(0.0)
            > g["stock_apertura_kg"].fillna(0.0)
            + g["entradas_dia_kg"].fillna(0.0)
            + EPSILON_KG
        )
        g["dias_cobertura_minimo"] = minimo
        g["dias_cobertura_objetivo"] = objetivo
        g["dias_cobertura_maximo"] = maximo
        frames.append(g)

    cobertura = pd.concat(frames, ignore_index=True)
    cobertura = cobertura.merge(aves_dia, on="fecha", how="left")
    cobertura["aves_activas"] = cobertura["aves_activas"].fillna(0.0)
    cobertura["flag_inventario_cero_con_aves"] = (
        cobertura["nivel"].eq("global")
        & cobertura["aves_activas"].gt(0)
        & cobertura["stock_kg"].le(EPSILON_KG)
    )
    cobertura["granularidad"] = "diaria"
    return cobertura


def eventos_cobertura(cobertura: pd.DataFrame, config: ProjectConfig) -> list[dict]:
    """Extrae eventos de alerta vigentes (a la última fecha con datos).

    Devuelve diccionarios neutros; ``alerts.construir_alertas`` los convierte
    al esquema canónico.
    """
    if cobertura.empty:
        return []
    params = _parametros(config)
    fecha_corte = cobertura["fecha"].max()
    vigente = cobertura.loc[cobertura["fecha"].eq(fecha_corte)]
    eventos: list[dict] = []

    def _persistencia(nivel: str, material: str, columna: str) -> int:
        serie = cobertura.loc[
            cobertura["nivel"].eq(nivel) & cobertura["material"].eq(material)
        ].sort_values("fecha")
        if serie.empty or columna not in serie.columns:
            return 0
        return int(_dias_consecutivos(serie[columna].fillna(False).astype(bool)).iloc[-1])

    for fila in vigente.itertuples():
        base = {
            "fecha": fecha_corte,
            "nivel": fila.nivel,
            "material": fila.material,
            "stock_kg": float(fila.stock_kg) if pd.notna(fila.stock_kg) else np.nan,
            "consumo_diario_estimado_kg": (
                float(fila.consumo_diario_estimado_kg)
                if pd.notna(fila.consumo_diario_estimado_kg)
                else np.nan
            ),
            "dias_cobertura": (
                float(fila.dias_cobertura) if pd.notna(fila.dias_cobertura) else np.nan
            ),
            "aves_activas": float(fila.aves_activas),
        }
        if fila.flag_stock_negativo:
            eventos.append(
                base
                | {
                    "tipo": "STOCK_NEGATIVO",
                    "tipo_resultado": "CALIDAD_DE_DATOS",
                    "severidad": "alta",
                    "persistencia_dias": _persistencia(
                        fila.nivel, fila.material, "flag_stock_negativo"
                    ),
                }
            )
        if fila.flag_consumo_mayor_que_disponible:
            eventos.append(
                base
                | {
                    "tipo": "CONSUMO_MAYOR_QUE_DISPONIBLE",
                    "tipo_resultado": "CALIDAD_DE_DATOS",
                    "severidad": "alta",
                    "persistencia_dias": 1,
                }
            )
        if fila.flag_inventario_cero_con_aves:
            eventos.append(
                base
                | {
                    "tipo": "INVENTARIO_CERO_CON_AVES",
                    "tipo_resultado": "OPERATIVA",
                    "severidad": "critica",
                    "persistencia_dias": _persistencia(
                        fila.nivel, fila.material, "flag_inventario_cero_con_aves"
                    ),
                }
            )
        if fila.flag_desabasto:
            mitad = float(params["dias_cobertura_minimo"]) / 2.0
            eventos.append(
                base
                | {
                    "tipo": "RIESGO_DESABASTO",
                    "tipo_resultado": "OPERATIVA",
                    "severidad": "critica" if base["dias_cobertura"] < mitad else "alta",
                    "persistencia_dias": _persistencia(fila.nivel, fila.material, "flag_desabasto"),
                }
            )
        if fila.flag_sobrestock:
            doble = float(params["dias_cobertura_maximo"]) * 2.0
            eventos.append(
                base
                | {
                    "tipo": "SOBRESTOCK",
                    "tipo_resultado": "OPERATIVA",
                    "severidad": "alta" if base["dias_cobertura"] > doble else "media",
                    "persistencia_dias": _persistencia(fila.nivel, fila.material, "flag_sobrestock"),
                }
            )
        if fila.flag_sin_movimiento_alerta and fila.nivel == "material":
            eventos.append(
                base
                | {
                    "tipo": "ALIMENTO_SIN_MOVIMIENTO",
                    "tipo_resultado": "OPERATIVA",
                    "severidad": "media",
                    "persistencia_dias": int(fila.dias_sin_movimiento),
                }
            )
        if fila.datos_insuficientes and fila.nivel == "global":
            eventos.append(
                base
                | {
                    "tipo": "COBERTURA_SIN_HISTORIA_SUFICIENTE",
                    "tipo_resultado": "CALIDAD_DE_DATOS",
                    "severidad": "informativa",
                    "persistencia_dias": 0,
                }
            )
    return eventos
