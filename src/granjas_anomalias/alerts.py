"""Consolidación de alertas: consenso de 4 capas, severidad y ciclo de vida.

Adapta la metodología de 4 capas al dominio avícola sin sustituir el score
oficial existente (65% reglas + 35% Isolation Forest):

- Capa 1 (calidad/reglas duras): validez estructural y conciliación.
- Capa 2 (estadística robusta): z robusto y cambios abruptos vs historial.
- Capa 3 (contextual): brechas contra el estándar por edad y contexto operativo.
- Capa 4 (multivariada): Isolation Forest oficial (los modelos sombra solo
  aportan evidencia, no promueven alertas).

La severidad de consenso nunca degrada la severidad oficial del score.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

import numpy as np
import pandas as pd

from .config import ProjectConfig
from .db import Warehouse, ahora_iso

SEVERIDADES = ["informativa", "baja", "media", "alta", "critica"]
_ORDEN_SEV = {s: i for i, s in enumerate(SEVERIDADES)}

CAPA_1 = ["consumo_negativo", "consumo_sin_orden", "orden_fuera_maestro", "flag_stock_inconsistente"]
CAPA_2 = ["flag_z_robusto", "flag_cambio_abrupto"]
CAPA_3 = [
    "flag_brecha_politica",
    "flag_brecha_politica_critica",
    "consumo_cero_con_aves",
    "flag_mortalidad_alta",
    "fase_multiple_dia",
    "flag_produccion_baja",
    "flag_produccion_cero",
]
CAPA_4 = ["flag_ml"]

ALERT_COLUMNS = [
    "alerta_id",
    "run_id",
    "clave_seguimiento",
    "familia",
    "tipo",
    "tipo_resultado",
    "granularidad",
    "fecha_inicial",
    "fecha_final",
    "semana",
    "mes",
    "granja",
    "centro",
    "almacen",
    "caseta",
    "material",
    "cycle_id",
    "edad_semana",
    "poblacion",
    "valor_real",
    "valor_esperado",
    "diferencia",
    "diferencia_pct",
    "capas",
    "n_capas",
    "score",
    "severidad",
    "cambio_severidad",
    "motivo",
    "evidencia",
    "posible_causa",
    "recomendacion",
    "calidad_datos",
    "estado",
    "archivo_fuente",
    "creado_en",
]

# Catálogo de tipos derivados de la línea diaria puntuada.
# (flag, familia, tipo, tipo_resultado, posible_causa, recomendacion,
#  columna_valor_real, columna_valor_esperado)
_CATALOGO_DIARIO = [
    (
        "consumo_negativo",
        "CALIDAD_DATOS",
        "CONSUMO_NETO_NEGATIVO",
        "CALIDAD_DE_DATOS",
        "Reversas 262 mayores al consumo del día o movimiento mal clasificado.",
        "Revisar los documentos 261/262 del día en MB51 y confirmar la reversa.",
        "consumo_real_kg_dia",
        "consumo_estandar_kg_dia",
    ),
    (
        "consumo_sin_orden",
        "CALIDAD_DATOS",
        "CONSUMO_SIN_ORDEN",
        "CALIDAD_DE_DATOS",
        "Consumo registrado sin orden operativa asociada.",
        "Verificar la orden en el maestro de organización y en el documento SAP.",
        "consumo_real_kg_dia",
        "consumo_estandar_kg_dia",
    ),
    (
        "orden_fuera_maestro",
        "CALIDAD_DATOS",
        "ORDEN_FUERA_DE_MAESTRO",
        "CALIDAD_DE_DATOS",
        "La orden del ciclo no aparece vigente en el maestro de organización.",
        "Actualizar el maestro de organización o confirmar el cierre de la orden.",
        "consumo_real_kg_dia",
        "consumo_estandar_kg_dia",
    ),
    (
        "flag_stock_inconsistente",
        "INVENTARIO",
        "DIFERENCIA_CONCILIACION",
        "CALIDAD_DE_DATOS",
        "El stock reconstruido no concilia con los movimientos del día.",
        "Contrastar MB5B/MB51 del día y revisar traspasos o ajustes sin clasificar.",
        "diferencia_conciliacion_kg",
        None,
    ),
    (
        "flag_z_robusto",
        "CONSUMO",
        "CONSUMO_FUERA_DE_HISTORICO",
        "OPERATIVA",
        "Consumo por ave fuera del comportamiento histórico del ciclo.",
        "Confirmar captura del día y condiciones de la caseta (clima, dieta, salud).",
        "consumo_real_kg_dia",
        "consumo_rolling_median_28",
    ),
    (
        "flag_cambio_abrupto",
        "CONSUMO",
        "CAMBIO_ABRUPTO_CONSUMO",
        "OPERATIVA",
        "Salto fuerte respecto al día anterior.",
        "Verificar si hubo doble captura, corrección o evento operativo.",
        "consumo_real_kg_dia",
        "consumo_promedio_7d",
    ),
    (
        "flag_brecha_politica",
        "CONSUMO",
        "DESVIACION_VS_ESTANDAR",
        "OPERATIVA",
        "Consumo alejado del estándar corporativo para la edad.",
        "Comparar con la política por edad y validar población y fase de alimento.",
        "consumo_real_kg_dia",
        "consumo_estandar_kg_dia",
    ),
    (
        "consumo_cero_con_aves",
        "CONSUMO",
        "CONSUMO_CERO_CON_AVES",
        "OPERATIVA",
        "Aves activas sin consumo registrado: falta de captura o desabasto.",
        "Confirmar si faltó capturar el 261 del día o si la caseta quedó sin alimento.",
        "consumo_real_kg_dia",
        "consumo_estandar_kg_dia",
    ),
    (
        "fase_multiple_dia",
        "CONSUMO",
        "FASES_SIMULTANEAS",
        "OPERATIVA",
        "Más de una fase de alimento el mismo día (transición o error).",
        "Confirmar el cambio de dieta con producción; si no hubo, revisar materiales.",
        "fases_activas_dia",
        None,
    ),
    (
        "flag_mortalidad_alta",
        "AVES",
        "MORTALIDAD_ALTA",
        "OPERATIVA",
        "Mortalidad diaria por encima del umbral (2 por millar).",
        "Notificar al responsable de la granja y revisar causas sanitarias.",
        "mortalidad_dia",
        "mortalidad_estandar_acum_aves",
    ),
    (
        "flag_produccion_baja",
        "PRODUCCION",
        "PRODUCCION_BAJO_ESTANDAR",
        "OPERATIVA",
        "Producción por debajo del estándar por edad de forma significativa.",
        "Revisar mortalidad, edad, dieta y registro de producción del periodo.",
        "produccion_real_kg_dia",
        "produccion_estandar_kg_dia",
    ),
    (
        "flag_produccion_cero",
        "PRODUCCION",
        "PRODUCCION_CERO_CON_AVES",
        "OPERATIVA",
        "Ciclo en etapa productiva sin producción registrada.",
        "Confirmar si faltó capturar el 101 WF del día o si hubo evento en caseta.",
        "produccion_real_kg_dia",
        "produccion_estandar_kg_dia",
    ),
    (
        "flag_ml",
        "MULTIVARIADA",
        "PATRON_MULTIVARIABLE_ATIPICO",
        "OPERATIVA",
        "Combinación inusual de consumo, producción, mortalidad y edad.",
        "Revisar el día completo del ciclo en el dashboard (todas las variables).",
        "score_anomalia",
        None,
    ),
]

_RECOMENDACIONES_COBERTURA = {
    "SOBRESTOCK": (
        "Más días de cobertura que el máximo parametrizado.",
        "Reprogramar pedidos y validar consumo reciente antes de recibir más alimento.",
    ),
    "RIESGO_DESABASTO": (
        "Cobertura por debajo del mínimo parametrizado.",
        "Confirmar pedidos en tránsito y adelantar reposición.",
    ),
    "INVENTARIO_CERO_CON_AVES": (
        "Stock de alimento agotado con aves activas.",
        "Atención inmediata: verificar silo físico y pedido urgente.",
    ),
    "ALIMENTO_SIN_MOVIMIENTO": (
        "Material con stock y sin consumo por varios días.",
        "Confirmar cambio de dieta o material inmovilizado para reasignar.",
    ),
    "STOCK_NEGATIVO": (
        "El stock reconstruido quedó negativo: faltan entradas o hay consumo duplicado.",
        "Revisar MB5B de ancla y los movimientos del material en MB51.",
    ),
    "CONSUMO_MAYOR_QUE_DISPONIBLE": (
        "El consumo del día supera el alimento disponible.",
        "Revisar documentos del día: probable error de captura o entrada faltante.",
    ),
    "COBERTURA_SIN_HISTORIA_SUFICIENTE": (
        "Historia insuficiente para estimar consumo diario.",
        "Cargar más días de historial antes de confiar en la cobertura.",
    ),
}


def _sev_max(a: str, b: str) -> str:
    return a if _ORDEN_SEV.get(a, 0) >= _ORDEN_SEV.get(b, 0) else b


def _hash_id(*partes: object) -> str:
    texto = "|".join("" if p is None else str(p) for p in partes)
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:16]


# ----------------------------------------------------------------------
# Consenso de capas sobre la línea diaria puntuada
# ----------------------------------------------------------------------
def aplicar_consenso_capas(scored: pd.DataFrame, config: ProjectConfig) -> pd.DataFrame:
    """Agrega capas, consenso y severidad de consenso a la línea puntuada."""
    result = scored.copy()
    critical_gap = float(config.anomaly.get("policy_gap_critical_pct", 0.30))

    brecha_prod = pd.to_numeric(result.get("brecha_produccion_pct_dia"), errors="coerce")
    hay_prod = result.get("hay_produccion", pd.Series(False, index=result.index)).fillna(False)
    aves = pd.to_numeric(result.get("aves_disponibles"), errors="coerce").fillna(0)
    produccion = pd.to_numeric(result.get("produccion_real_kg_dia"), errors="coerce").fillna(0)
    result["flag_produccion_baja"] = (
        hay_prod.astype(bool) & brecha_prod.le(-critical_gap).fillna(False)
    )
    result["flag_produccion_cero"] = (
        hay_prod.astype(bool) & aves.gt(0) & produccion.le(0)
    )

    def _capa(columnas: list[str]) -> pd.Series:
        activa = pd.Series(False, index=result.index)
        for col in columnas:
            if col in result.columns:
                activa |= result[col].fillna(False).astype(bool)
        return activa

    result["capa1_calidad"] = _capa(CAPA_1)
    result["capa2_estadistica"] = _capa(CAPA_2)
    result["capa3_contextual"] = _capa(CAPA_3)
    result["capa4_multivariada"] = _capa(CAPA_4)
    capas = ["capa1_calidad", "capa2_estadistica", "capa3_contextual", "capa4_multivariada"]
    result["n_capas"] = result[capas].sum(axis=1).astype(int)
    result["capas_activas"] = result[capas].apply(
        lambda fila: ", ".join(c.split("_")[0] for c in capas if fila[c]), axis=1
    )
    result["tipo_resultado"] = np.where(
        result["capa1_calidad"]
        & ~(result["capa2_estadistica"] | result["capa3_contextual"] | result["capa4_multivariada"]),
        "CALIDAD_DE_DATOS",
        "OPERATIVA",
    )

    oficial = result.get("severidad", pd.Series("baja", index=result.index)).fillna("baja")
    consenso = pd.Series("informativa", index=result.index)
    consenso = consenso.mask(result["n_capas"].ge(1), "baja")
    consenso = consenso.mask(result["n_capas"].ge(2), "alta")
    consenso = consenso.mask(result["n_capas"].ge(3), "critica")
    result["severidad_consenso"] = [
        _sev_max(str(a), str(b)) for a, b in zip(oficial, consenso)
    ]
    return result


# ----------------------------------------------------------------------
# Construcción de alertas canónicas
# ----------------------------------------------------------------------
def _plantilla(config: ProjectConfig, run_id: str) -> dict:
    return {
        "run_id": run_id,
        "granularidad": "diaria",
        "granja": str(config.project.get("farm_name", "")),
        "centro": str(config.project.get("center_id", "")),
        "almacen": str(config.sap.get("feed_warehouse", "")),
        "cambio_severidad": "",
        "estado": "nueva",
        "archivo_fuente": "",
        "creado_en": ahora_iso(),
    }


def _consolidar_eventos_diarios(
    activos: pd.DataFrame,
    flag: str,
    familia: str,
    tipo: str,
    tipo_resultado: str,
    causa: str,
    recomendacion: str,
    col_real: str,
    col_esperado: str | None,
    base: dict,
) -> list[dict]:
    eventos = activos.loc[activos[flag].fillna(False).astype(bool)]
    if eventos.empty:
        return []
    filas: list[dict] = []
    for cycle_id, grupo in eventos.groupby("cycle_id"):
        grupo = grupo.sort_values("fecha")
        ultimo = grupo.iloc[-1]
        fecha_ini = pd.Timestamp(grupo["fecha"].min())
        fecha_fin = pd.Timestamp(grupo["fecha"].max())
        valor_real = pd.to_numeric(pd.Series([ultimo.get(col_real)]), errors="coerce").iloc[0]
        valor_esp = (
            pd.to_numeric(pd.Series([ultimo.get(col_esperado)]), errors="coerce").iloc[0]
            if col_esperado
            else np.nan
        )
        diferencia = (
            valor_real - valor_esp if pd.notna(valor_real) and pd.notna(valor_esp) else np.nan
        )
        diferencia_pct = (
            diferencia / valor_esp
            if pd.notna(diferencia) and pd.notna(valor_esp) and abs(valor_esp) > 1e-9
            else np.nan
        )
        clave = "|".join(
            [familia, tipo, base["centro"], str(ultimo.get("caseta", "")), str(cycle_id)]
        )
        calidad = "completa"
        if bool(ultimo.get("capa1_calidad", False)) and tipo_resultado == "OPERATIVA":
            calidad = "con_incidencias_capa1"
        filas.append(
            base
            | {
                "alerta_id": _hash_id(clave, str(fecha_fin.date())),
                "clave_seguimiento": clave,
                "familia": familia,
                "tipo": tipo,
                "tipo_resultado": tipo_resultado,
                "fecha_inicial": str(fecha_ini.date()),
                "fecha_final": str(fecha_fin.date()),
                "semana": str(fecha_fin.to_period("W-SUN")),
                "mes": str(fecha_fin.to_period("M")),
                "caseta": str(ultimo.get("caseta", "")),
                "material": str(ultimo.get("material_alimento_principal", "") or ""),
                "cycle_id": str(cycle_id),
                "edad_semana": pd.to_numeric(
                    pd.Series([ultimo.get("edad_semana")]), errors="coerce"
                ).iloc[0],
                "poblacion": pd.to_numeric(
                    pd.Series([ultimo.get("aves_disponibles")]), errors="coerce"
                ).iloc[0],
                "valor_real": valor_real,
                "valor_esperado": valor_esp,
                "diferencia": diferencia,
                "diferencia_pct": diferencia_pct,
                "capas": str(ultimo.get("capas_activas", "")),
                "n_capas": int(ultimo.get("n_capas", 0) or 0),
                "score": pd.to_numeric(
                    pd.Series([ultimo.get("score_anomalia")]), errors="coerce"
                ).iloc[0],
                "severidad": str(ultimo.get("severidad_consenso", "media")),
                "motivo": f"{tipo.replace('_', ' ').capitalize()} en {len(grupo)} día(s); "
                f"último: {fecha_fin.date()}.",
                "evidencia": (
                    f"{len(grupo)} evento(s) entre {fecha_ini.date()} y {fecha_fin.date()}; "
                    f"capas: {ultimo.get('capas_activas', '')}; "
                    f"acuerdo modelos sombra: {ultimo.get('acuerdo_modelos', '')}"
                ),
                "posible_causa": causa,
                "recomendacion": recomendacion,
                "calidad_datos": calidad,
            }
        )
    return filas


def construir_alertas(
    scored: pd.DataFrame,
    weekly: pd.DataFrame,
    eventos_cobertura: list[dict],
    config: ProjectConfig,
    run_id: str,
    ventana_actividad_dias: int = 7,
) -> pd.DataFrame:
    """Construye la tabla canónica de alertas vigentes de la corrida.

    Solo se consideran *vigentes* los eventos dentro de la ventana de
    actividad respecto a la última fecha con datos; el histórico completo
    permanece en la línea diaria puntuada (10/11) y en la base SQLite.
    """
    base = _plantilla(config, run_id)
    filas: list[dict] = []

    if not scored.empty:
        fechas = pd.to_datetime(scored["fecha"], errors="coerce")
        corte = fechas.max() - pd.Timedelta(days=int(ventana_actividad_dias) - 1)
        activos = scored.loc[fechas.ge(corte)].copy()
        for (
            flag,
            familia,
            tipo,
            tipo_resultado,
            causa,
            recomendacion,
            col_real,
            col_esperado,
        ) in _CATALOGO_DIARIO:
            if flag not in activos.columns:
                continue
            filas.extend(
                _consolidar_eventos_diarios(
                    activos,
                    flag,
                    familia,
                    tipo,
                    tipo_resultado,
                    causa,
                    recomendacion,
                    col_real,
                    col_esperado,
                    base,
                )
            )

        # --- ICA semanal (familia propia, granularidad semanal) ---
        if weekly is not None and not weekly.empty and "es_ica_evaluable" in weekly.columns:
            warning_gap = float(config.anomaly.get("policy_gap_warning_pct", 0.15))
            evaluable = weekly.loc[weekly["es_ica_evaluable"].fillna(False).astype(bool)].copy()
            evaluable["brecha_ica_pct"] = pd.to_numeric(
                evaluable.get("brecha_ica_pct"), errors="coerce"
            )
            ult_semana = evaluable.groupby("cycle_id").tail(2)
            for cycle_id, grupo in ult_semana.groupby("cycle_id"):
                fila = grupo.sort_values("edad_semana").iloc[-1]
                brecha = fila["brecha_ica_pct"]
                if pd.isna(brecha) or abs(brecha) < warning_gap:
                    continue
                tipo = "ICA_SUPERIOR_AL_ESTANDAR" if brecha > 0 else "ICA_INFERIOR_AL_ESTANDAR"
                consecutivas = int(
                    (grupo["brecha_ica_pct"].abs() >= warning_gap).sum()
                )
                clave = "|".join(["ICA", tipo, base["centro"], str(fila.get("caseta", "")), str(cycle_id)])
                filas.append(
                    base
                    | {
                        "alerta_id": _hash_id(clave, str(fila.get("fecha_fin_semana", ""))),
                        "clave_seguimiento": clave,
                        "familia": "ICA",
                        "tipo": tipo,
                        "tipo_resultado": "OPERATIVA",
                        "granularidad": "semanal",
                        "fecha_inicial": str(fila.get("fecha_inicio_semana", "")),
                        "fecha_final": str(fila.get("fecha_fin_semana", "")),
                        "semana": str(fila.get("edad_semana", "")),
                        "mes": "",
                        "caseta": str(fila.get("caseta", "")),
                        "material": "",
                        "cycle_id": str(cycle_id),
                        "edad_semana": pd.to_numeric(
                            pd.Series([fila.get("edad_semana")]), errors="coerce"
                        ).iloc[0],
                        "poblacion": pd.to_numeric(
                            pd.Series([fila.get("aves_promedio")]), errors="coerce"
                        ).iloc[0],
                        "valor_real": pd.to_numeric(
                            pd.Series([fila.get("ica_real")]), errors="coerce"
                        ).iloc[0],
                        "valor_esperado": pd.to_numeric(
                            pd.Series([fila.get("ica_estandar_principal")]), errors="coerce"
                        ).iloc[0],
                        "diferencia": pd.to_numeric(
                            pd.Series([fila.get("brecha_ica")]), errors="coerce"
                        ).iloc[0],
                        "diferencia_pct": brecha,
                        "capas": "capa3",
                        "n_capas": 1,
                        "score": np.nan,
                        "severidad": "alta" if consecutivas >= 2 else "media",
                        "motivo": f"ICA semanal {'sobre' if brecha > 0 else 'bajo'} el estándar "
                        f"({brecha:+.1%}); {consecutivas} semana(s) recientes fuera.",
                        "evidencia": f"ICA real {fila.get('ica_real')} vs estándar "
                        f"{fila.get('ica_estandar_principal')} (semana edad {fila.get('edad_semana')}).",
                        "posible_causa": (
                            "Consumo alto o producción baja para la edad; posible desperdicio, "
                            "fuga o subregistro de producción."
                            if brecha > 0
                            else "ICA sospechosamente bajo: posible consumo subregistrado o "
                            "producción sobrerregistrada."
                        ),
                        "recomendacion": "Contrastar consumo y producción de la semana contra "
                        "documentos SAP y estándar por edad.",
                        "calidad_datos": "completa"
                        if bool(fila.get("semana_completa", True))
                        else "semana_incompleta",
                    }
                )

    # --- Cobertura de alimento (familia INVENTARIO) ---
    for evento in eventos_cobertura:
        tipo = evento["tipo"]
        causa, recomendacion = _RECOMENDACIONES_COBERTURA.get(tipo, ("", ""))
        clave = "|".join(["INVENTARIO", tipo, base["centro"], "", str(evento.get("material", ""))])
        fecha = pd.Timestamp(evento["fecha"])
        filas.append(
            base
            | {
                "alerta_id": _hash_id(clave, str(fecha.date())),
                "clave_seguimiento": clave,
                "familia": "INVENTARIO",
                "tipo": tipo,
                "tipo_resultado": evento.get("tipo_resultado", "OPERATIVA"),
                "fecha_inicial": str(
                    (fecha - pd.Timedelta(days=max(evento.get("persistencia_dias", 1) - 1, 0))).date()
                ),
                "fecha_final": str(fecha.date()),
                "semana": str(fecha.to_period("W-SUN")),
                "mes": str(fecha.to_period("M")),
                "caseta": "",
                "material": str(evento.get("material", "")),
                "cycle_id": "",
                "edad_semana": np.nan,
                "poblacion": evento.get("aves_activas", np.nan),
                "valor_real": evento.get("dias_cobertura", np.nan),
                "valor_esperado": np.nan,
                "diferencia": np.nan,
                "diferencia_pct": np.nan,
                "capas": "capa1" if evento.get("tipo_resultado") == "CALIDAD_DE_DATOS" else "capa3",
                "n_capas": 1,
                "score": np.nan,
                "severidad": evento.get("severidad", "media"),
                "motivo": f"{tipo.replace('_', ' ').capitalize()} "
                f"(stock {evento.get('stock_kg', float('nan')):,.0f} kg, "
                f"cobertura {evento.get('dias_cobertura', float('nan')):.1f} días, "
                f"persistencia {evento.get('persistencia_dias', 0)} día(s)).",
                "evidencia": f"Consumo diario estimado: "
                f"{evento.get('consumo_diario_estimado_kg', float('nan')):,.1f} kg/día; "
                f"aves activas: {evento.get('aves_activas', 0):,.0f}.",
                "posible_causa": causa,
                "recomendacion": recomendacion,
                "calidad_datos": "completa",
            }
        )

    if not filas:
        return pd.DataFrame(columns=ALERT_COLUMNS)
    alertas = pd.DataFrame(filas)
    for columna in ALERT_COLUMNS:
        if columna not in alertas.columns:
            alertas[columna] = pd.NA
    return alertas[ALERT_COLUMNS]


# ----------------------------------------------------------------------
# Ciclo de vida
# ----------------------------------------------------------------------
def aplicar_ciclo_vida(alertas: pd.DataFrame, db: Warehouse, run_id: str) -> pd.DataFrame:
    """Asigna estados comparando con la corrida anterior registrada.

    Estados automáticos: nueva, persistente, recurrente, reabierta, resuelta;
    ``cambio_severidad`` registra subidas/bajadas entre corridas.
    """
    previas = db.leer_alertas()
    if previas.empty:
        return alertas

    previas = previas.loc[previas["run_id"].ne(run_id)]
    if previas.empty:
        return alertas

    ultimo_run = previas.sort_values("creado_en")["run_id"].iloc[-1]
    prev_activas = previas.loc[
        previas["run_id"].eq(ultimo_run) & previas["estado"].ne("resuelta")
    ]
    activas_prev = prev_activas.set_index("clave_seguimiento")
    apariciones = previas.groupby("clave_seguimiento")["run_id"].nunique()

    resultado = alertas.copy()
    estados, cambios = [], []
    for fila in resultado.itertuples():
        clave = fila.clave_seguimiento
        if clave in activas_prev.index:
            estados.append("persistente")
            prev_sev = activas_prev.loc[clave, "severidad"]
            if isinstance(prev_sev, pd.Series):
                prev_sev = prev_sev.iloc[-1]
            orden_prev = _ORDEN_SEV.get(str(prev_sev), 0)
            orden_act = _ORDEN_SEV.get(str(fila.severidad), 0)
            cambios.append(
                "subio" if orden_act > orden_prev else "bajo" if orden_act < orden_prev else ""
            )
        elif clave in apariciones.index:
            estados.append("recurrente" if int(apariciones[clave]) >= 2 else "reabierta")
            cambios.append("")
        else:
            estados.append("nueva")
            cambios.append("")
    resultado["estado"] = estados
    resultado["cambio_severidad"] = cambios

    # Alertas activas en la corrida anterior que ya no aparecen -> resueltas.
    claves_actuales = set(resultado["clave_seguimiento"])
    resueltas = prev_activas.loc[
        ~prev_activas["clave_seguimiento"].isin(claves_actuales)
    ].copy()
    if not resueltas.empty:
        resueltas["run_id"] = run_id
        resueltas["estado"] = "resuelta"
        resueltas["cambio_severidad"] = ""
        resueltas["creado_en"] = ahora_iso()
        resueltas = resueltas[ALERT_COLUMNS]
        if resultado.empty:
            resultado = resueltas.reset_index(drop=True)
        else:
            resultado = pd.concat([resultado, resueltas], ignore_index=True)
    return resultado


def procesar_alertas(
    scored: pd.DataFrame,
    weekly: pd.DataFrame,
    eventos: list[dict],
    config: ProjectConfig,
    db: Warehouse,
    run_id: str,
) -> pd.DataFrame:
    """Orquesta construcción, ciclo de vida y persistencia de alertas."""
    alertas = construir_alertas(scored, weekly, eventos, config, run_id)
    alertas = aplicar_ciclo_vida(alertas, db, run_id)
    if not alertas.empty:
        db.guardar_alertas(alertas)
    return alertas
