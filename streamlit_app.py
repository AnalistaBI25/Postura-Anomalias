"""Host Streamlit invisible para el dashboard HTML/JS.

Toda la experiencia visible vive en un componente HTML/CSS/JS. Streamlit solo
recibe el archivo SAP cargado desde ese componente, ejecuta el pipeline Python y
devuelve el dashboard HTML actualizado.
"""

from __future__ import annotations

import base64
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

CONFIG_PATH = ROOT / "config" / "project.yml"
SHELL_COMPONENT_DIR = ROOT / "streamlit_components" / "dashboard_shell"

st.set_page_config(
    page_title="BI Anomalías Avícolas",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .block-container { max-width: 100%; padding: 0; }
      header, footer, div[data-testid="stToolbar"] { visibility: hidden; }
      .stApp { background: #eef7fb; }
      iframe[title*="dashboard_shell"] {
        display: block;
        width: 100%;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

dashboard_shell = components.declare_component(
    "dashboard_shell",
    path=str(SHELL_COMPONENT_DIR),
)


@st.cache_resource
def _cargar_config():
    from granjas_anomalias.config import load_config

    return load_config(CONFIG_PATH)


def _warehouse(config) -> Any:
    from granjas_anomalias.db import Warehouse

    return Warehouse(config.resolve_ingestion("db_path", "data/warehouse.db"))


def _ejecutar_pipeline() -> dict:
    from granjas_anomalias.pipeline import run_pipeline

    return run_pipeline(CONFIG_PATH)


def _dashboard_html(config: Any | None) -> str:
    if config is not None:
        dashboard_path = config.resolve("reports_dir") / "dashboard.html"
        if dashboard_path.exists():
            return dashboard_path.read_text(encoding="utf-8")
    return """
    <!doctype html>
    <html lang="es">
    <body style="font-family:Arial,sans-serif;background:#f2fbfe;color:#173f8a;margin:0;padding:32px">
      <h1>Dashboard pendiente</h1>
      <p>Sube un archivo SAP y ejecuta el pipeline para generar el dashboard de esta granja.</p>
    </body>
    </html>
    """


def _history_status(config: Any | None, db: Any | None) -> dict[str, Any]:
    if config is None or db is None:
        return {"ready": False}
    minimo, maximo = db.rango_existente(str(config.project["center_id"]))
    return {
        "ready": True,
        "farm_id": config.farm_id,
        "center_id": str(config.project["center_id"]),
        "farm_name": str(config.project.get("farm_name", "")),
        "min_date": minimo,
        "max_date": maximo,
    }


def _model_status(config: Any | None) -> dict[str, Any]:
    if config is None:
        return {"ready": False, "mode": "readonly"}
    lifecycle = config.raw.get("model_lifecycle", {}) or {}
    model_path = config.resolve_model_lifecycle(
        "active_model_path",
        "models/isolation_forest_consumo.joblib",
    )
    metadata_path = config.resolve_model_lifecycle(
        "metadata_path",
        "models/isolation_forest_metadata.json",
    )
    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}
    return {
        "ready": True,
        "mode": str(lifecycle.get("mode", "train")),
        "model_exists": model_path.exists(),
        "metadata_exists": metadata_path.exists(),
        "version": str(metadata.get("model_version") or lifecycle.get("active_model_version", "")),
        "generated_at": str(metadata.get("generated_at", "")),
        "approval_status": str(metadata.get("approval_status") or lifecycle.get("approval_status", "")),
        "artifact": model_path.name,
    }


def _ops_status(config: Any | None, db: Any | None) -> dict[str, Any]:
    if config is None or db is None:
        return {"ready": False, "model": _model_status(config), "metrics": {}, "alerts": []}

    cargas = db.listar_cargas()
    ejecuciones = db.listar_ejecuciones(5)
    alertas = db.leer_alertas()
    revisiones = db.leer_revisiones()
    if not alertas.empty:
        alertas = alertas.sort_values("creado_en", ascending=False)
    recientes = []
    for _, row in alertas.head(30).iterrows():
        clave = str(row.get("clave_seguimiento", ""))
        if not clave:
            continue
        recientes.append(
            {
                "clave": clave,
                "label": " | ".join(
                    part
                    for part in [
                        str(row.get("fecha_inicial", "") or row.get("fecha_final", "")),
                        str(row.get("caseta", "") or row.get("almacen", "")),
                        str(row.get("familia", "")),
                        str(row.get("severidad", "")),
                    ]
                    if part
                ),
            }
        )
    metrics = {
        "cargas": int(len(cargas)),
        "rechazadas": int(cargas["estado"].eq("RECHAZADO").sum()) if "estado" in cargas else 0,
        "registros_nuevos": int(cargas["n_insertados"].fillna(0).sum()) if "n_insertados" in cargas else 0,
        "alertas": int(len(alertas)),
        "revisadas": int(len(revisiones)),
        "ultima_ejecucion": str(ejecuciones.iloc[0].get("resultado", "")) if not ejecuciones.empty else "",
    }
    return {
        "ready": True,
        "model": _model_status(config),
        "metrics": metrics,
        "alerts": recientes,
    }


def _decode_upload(file_info: dict[str, Any]) -> bytes:
    data = str(file_info.get("data", ""))
    encoded = data.split(",", 1)[1] if "," in data else data
    return base64.b64decode(encoded)


def _summarize_validation(informes: list[Any]) -> list[dict[str, Any]]:
    rows = []
    for informe in informes:
        resumen = informe.resumen()
        rows.append(
            {
                "archivo": resumen.get("archivo", ""),
                "fuente": resumen.get("fuente", ""),
                "valido": bool(resumen.get("valido", False)),
                "n_registros": int(resumen.get("n_registros", 0) or 0),
                "fecha_min": resumen.get("fecha_min", ""),
                "fecha_max": resumen.get("fecha_max", ""),
                "errores": list(getattr(informe, "errores", []) or []),
                "advertencias": list(getattr(informe, "advertencias", []) or []),
            }
        )
    return rows


def _process_upload_event(event: dict[str, Any], config: Any, db: Any) -> dict[str, Any]:
    from granjas_anomalias.ingestion import (
        ingerir_archivo,
        materializar_kardex_cache,
    )

    files = list(event.get("files") or [])
    if not files:
        return {
            "stage": "error",
            "progress": 100,
            "title": "Sin archivo",
            "message": "No se recibió ningún archivo desde el dashboard.",
        }

    max_files = int(config.ingestion.get("max_files_per_upload", 1) or 1)
    if len(files) > max_files:
        return {
            "stage": "validation_error",
            "progress": 100,
            "title": "Solo un archivo SAP",
            "message": (
                "Sube unicamente el crudo principal MB51. "
                "La logica, reglas y modelo se aplican despues en Python."
            ),
            "validations": [],
            "results": [],
        }

    incoming = config.resolve_ingestion("incoming_dir", "data/incoming")
    incoming.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    file_info = files[0]
    safe_name = Path(str(file_info.get("name") or "archivo_sap")).name
    destino = incoming / safe_name
    destino.write_bytes(_decode_upload(file_info))

    accepted_source = str(config.ingestion.get("accepted_upload_source", "MB51")).upper()
    resumen = ingerir_archivo(
        destino,
        config,
        db,
        usuario="dashboard",
        solo_mb51=accepted_source == "MB51",
    )
    informes = [resumen.informe] if resumen.informe is not None else []
    validations = _summarize_validation(informes)
    if resumen.estado == "RECHAZADO":
        return {
            "stage": "validation_error",
            "progress": 100,
            "title": "Validación detenida",
            "message": resumen.mensaje or "El archivo no cumple el formato esperado para MB51.",
            "validations": validations,
            "results": [],
        }

    execute_pipeline = bool(event.get("executePipeline", True))
    results = [
        {
            "archivo": destino.name,
            "estado": resumen.estado,
            "insertados": resumen.insertados,
            "omitidos_duplicados": resumen.omitidos_duplicados,
            "detalle": resumen.mensaje,
        }
    ]

    if execute_pipeline and resumen.insertados:
        materializar_kardex_cache(db, config)
        _ejecutar_pipeline()
        title = "Dashboard actualizado"
        message = "La carga fue procesada y el HTML fue regenerado correctamente."
    elif execute_pipeline:
        title = "Sin registros nuevos"
        message = (
            "El archivo ya estaba cargado o no agrego movimientos nuevos; "
            "se conserva el dashboard actual."
        )
    else:
        title = "Carga registrada"
        message = "Los movimientos válidos fueron registrados sin regenerar el dashboard."

    return {
        "stage": "complete",
        "progress": 100,
        "title": title,
        "message": message,
        "duration_seconds": round(time.perf_counter() - started, 2),
        "validations": validations,
        "results": results,
    }


def _process_review_event(event: dict[str, Any], db: Any) -> dict[str, Any]:
    review = event.get("review") or {}
    clave = str(review.get("clave") or "").strip()
    estado = str(review.get("estado") or "").strip().upper()
    usuario = str(review.get("usuario") or "dashboard").strip() or "dashboard"
    comentario = str(review.get("comentario") or "").strip()
    estados_validos = {"CONFIRMADA", "FALSO_POSITIVO", "PROBLEMA_DE_DATOS", "DESCARTADA"}
    if not clave:
        return {
            "stage": "error",
            "progress": 100,
            "title": "Selecciona una alerta",
            "message": "Elige una clave de seguimiento para registrar la revision.",
            "validations": [],
            "results": [],
        }
    if estado not in estados_validos:
        return {
            "stage": "error",
            "progress": 100,
            "title": "Estado no valido",
            "message": f"Usa uno de: {', '.join(sorted(estados_validos))}.",
            "validations": [],
            "results": [],
        }
    db.guardar_revision(clave, estado, comentario=comentario, usuario=usuario)
    return {
        "stage": "complete",
        "progress": 100,
        "title": "Revision guardada",
        "message": f"{clave} quedo como {estado}.",
        "validations": [],
        "results": [{"archivo": clave, "estado": estado, "insertados": 0}],
    }


config = None
db = None
config_error = None
if CONFIG_PATH.exists():
    try:
        config = _cargar_config()
        db = _warehouse(config)
    except Exception as exc:  # noqa: BLE001
        config_error = exc

if "dashboard_shell_status" not in st.session_state:
    st.session_state.dashboard_shell_status = {
        "stage": "idle",
        "progress": 0,
        "title": "Esperando crudo SAP MB51",
        "message": "Sube un solo MB51; Python normaliza, valida y ejecuta scoring.",
        "validations": [],
        "results": [],
    }
if config_error is not None:
    st.session_state.dashboard_shell_status = {
        "stage": "config_error",
        "progress": 0,
        "title": "Carga no disponible",
        "message": str(config_error),
        "validations": [],
        "results": [],
    }
elif config is None or db is None:
    st.session_state.dashboard_shell_status = {
        "stage": "readonly",
        "progress": 0,
        "title": "Modo consulta",
        "message": "Incluye config/project.yml en la rama publicada para activar la carga SAP.",
        "validations": [],
        "results": [],
    }

component_value = dashboard_shell(
    dashboard_html=_dashboard_html(config),
    status=st.session_state.dashboard_shell_status,
    history=_history_status(config, db),
    ops=_ops_status(config, db),
    config_ready=bool(config is not None and db is not None),
    key="dashboard_shell",
    default=None,
)

if isinstance(component_value, dict):
    event_id = str(component_value.get("eventId", ""))
    if event_id and event_id != st.session_state.get("dashboard_shell_last_event_id"):
        st.session_state.dashboard_shell_last_event_id = event_id
        if config is None or db is None:
            st.session_state.dashboard_shell_status = {
                "stage": "error",
                "progress": 100,
                "title": "Carga no disponible",
                "message": "La configuración del proyecto no está disponible.",
                "validations": [],
                "results": [],
            }
        else:
            try:
                action = str(component_value.get("action", "upload"))
                if action == "save_review":
                    st.session_state.dashboard_shell_status = _process_review_event(component_value, db)
                else:
                    st.session_state.dashboard_shell_status = _process_upload_event(
                        component_value,
                        config,
                        db,
                    )
            except Exception as exc:  # noqa: BLE001
                st.session_state.dashboard_shell_status = {
                    "stage": "error",
                    "progress": 100,
                    "title": "Error al procesar la carga",
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                    "validations": [],
                    "results": [],
                }
        st.rerun()
