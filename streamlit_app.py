"""Host Streamlit del dashboard productivo.

Streamlit se usa solo como backend/host: recibe archivos SAP, ejecuta el
pipeline y muestra el dashboard HTML autocontenido generado por el proyecto.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))

CONFIG_PATH = ROOT / "config" / "project.yml"
DASHBOARD_PATH = ROOT / "reports" / "dashboard.html"

st.set_page_config(
    page_title="BI Anomalías Avícolas",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .block-container {
        max-width: 100%;
        padding: 0.75rem 1.5rem 0;
      }
      header, footer { visibility: hidden; }
      div[data-testid="stToolbar"] { display: none; }

      .upload-shell {
        max-width: 1180px;
        margin: 0 auto 1rem;
        padding: 1rem 1.25rem;
        border: 1px solid #bfe7f6;
        border-radius: 18px;
        background: linear-gradient(180deg, #f8fdff 0%, #eefaff 100%);
        box-shadow: 0 14px 38px rgba(7, 75, 120, 0.08);
      }
      .upload-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 1rem;
        flex-wrap: wrap;
        margin-bottom: 0.75rem;
      }
      .upload-title {
        margin: 0;
        color: #173f8a;
        font-size: 1.35rem;
        font-weight: 800;
      }
      .upload-subtitle {
        margin: 0.15rem 0 0;
        color: #2b5d88;
        font-size: 0.95rem;
      }
      .upload-badge {
        color: #17458f;
        background: #ffffff;
        border: 1px solid #9bdaf2;
        border-radius: 999px;
        padding: 0.45rem 0.75rem;
        font-weight: 700;
        white-space: nowrap;
      }
      div[data-testid="stFileUploader"] {
        padding: 0.35rem 0 0;
      }
      div[data-testid="stFileUploaderDropzone"] {
        border-color: #2aaee8;
        background: #ffffff;
      }
      .dashboard-shell {
        max-width: 100%;
        margin: 0 auto;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def _cargar_config():
    from granjas_anomalias.config import load_config

    return load_config(CONFIG_PATH)


def _warehouse(config) -> Any:
    from granjas_anomalias.db import Warehouse

    return Warehouse(config.root / config.ingestion.get("db_path", "data/warehouse.db"))


def _ejecutar_pipeline() -> dict:
    from granjas_anomalias.pipeline import run_pipeline

    return run_pipeline(CONFIG_PATH)


def _mostrar_dashboard() -> None:
    st.markdown('<div class="dashboard-shell">', unsafe_allow_html=True)
    if DASHBOARD_PATH.exists():
        components.html(
            DASHBOARD_PATH.read_text(encoding="utf-8"),
            height=1400,
            scrolling=True,
        )
    else:
        st.info(
            "Aún no existe reports/dashboard.html. Sube un archivo SAP y ejecuta "
            "el pipeline, o corre `python -m granjas_anomalias.cli run --config "
            "config/project.yml`."
        )
    st.markdown("</div>", unsafe_allow_html=True)


config = None
db = None
config_error = None
if CONFIG_PATH.exists():
    try:
        config = _cargar_config()
        db = _warehouse(config)
    except Exception as exc:  # noqa: BLE001
        config_error = exc

st.markdown(
    """
    <section class="upload-shell">
      <div class="upload-head">
        <div>
          <h1 class="upload-title">Carga SAP</h1>
          <p class="upload-subtitle">
            Sube exportaciones MB51; al confirmar se recalcula el dashboard HTML.
          </p>
        </div>
        <div class="upload-badge">Dashboard productivo</div>
      </div>
    </section>
    """,
    unsafe_allow_html=True,
)

if config_error is not None:
    st.warning(
        "No se pudo cargar config/project.yml. Se muestra solo el dashboard "
        "publicado; la carga SAP queda deshabilitada."
    )
    st.code(str(config_error))
    _mostrar_dashboard()
    st.stop()

if db is None or config is None:
    st.info(
        "Modo dashboard publicado: config/project.yml no está versionado. "
        "La carga SAP se habilita cuando existe ese archivo."
    )
    _mostrar_dashboard()
    st.stop()

from granjas_anomalias.ingestion import (  # noqa: E402
    ingerir_archivo,
    materializar_kardex_cache,
    validar_archivo,
)

with st.container():
    minimo, maximo = db.rango_existente(str(config.project["center_id"]))
    if minimo:
        st.info(
            f"Histórico cargado para el centro {config.project['center_id']}: "
            f"{minimo} a {maximo}."
        )
    else:
        st.warning(
            "El almacén incremental está vacío. Inicializa el histórico desde el "
            "kardex configurado antes de cargar incrementos."
        )
        if st.button("Inicializar histórico desde config"):
            kardex_path = config.resolve("kardex_excel")
            with st.spinner(f"Ingiriendo {kardex_path.name}..."):
                resumen = ingerir_archivo(kardex_path, config, db, usuario="bootstrap")
            st.success(f"{resumen.estado}: {resumen.mensaje}")
            st.rerun()

    archivos = st.file_uploader(
        "Selecciona o arrastra uno o varios archivos",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
    )

    if archivos:
        incoming = config.root / config.ingestion.get("incoming_dir", "data/incoming")
        incoming.mkdir(parents=True, exist_ok=True)
        informes = []
        rutas = []
        for archivo in archivos:
            destino = incoming / archivo.name
            destino.write_bytes(archivo.getbuffer())
            rutas.append(destino)
            informes.append(validar_archivo(destino, config, db))

        st.markdown("### 1 · Validación")
        resumen_df = pd.DataFrame([inf.resumen() for inf in informes])
        st.dataframe(resumen_df, width="stretch")

        for informe, ruta in zip(informes, rutas):
            with st.expander(f"Vista previa — {informe.archivo}", expanded=False):
                if informe.errores:
                    st.error("; ".join(informe.errores))
                if informe.advertencias:
                    st.warning("; ".join(informe.advertencias))
                if informe.granularidad:
                    st.json(informe.granularidad)
                if informe.valido and informe.fuente == "MB51":
                    try:
                        if ruta.suffix.lower() == ".csv":
                            vista = pd.read_csv(ruta, nrows=20)
                        else:
                            vista = pd.read_excel(
                                ruta, sheet_name=informe.hoja or 0, nrows=20
                            )
                        st.dataframe(vista, width="stretch")
                    except Exception as exc:  # noqa: BLE001
                        st.warning(f"No se pudo generar vista previa: {exc}")

        errores_df = resumen_df.loc[~resumen_df["valido"]]
        if not errores_df.empty:
            st.download_button(
                "Descargar reporte de errores (CSV)",
                errores_df.to_csv(index=False).encode("utf-8-sig"),
                file_name="reporte_errores_carga.csv",
                mime="text/csv",
            )

        validos = [(inf, r) for inf, r in zip(informes, rutas) if inf.valido]
        ejecutar = st.checkbox(
            "Ejecutar pipeline completo al confirmar",
            value=True,
            help="Recalcula indicadores, alertas integradas y dashboard HTML.",
        )
        if st.button(
            f"Confirmar carga de {len(validos)} archivo(s) válido(s)",
            disabled=not validos,
        ):
            resultados = []
            for informe, ruta in validos:
                with st.spinner(f"Procesando {ruta.name}..."):
                    resumen = ingerir_archivo(ruta, config, db, usuario="dashboard")
                resultados.append(
                    {
                        "archivo": ruta.name,
                        "estado": resumen.estado,
                        "insertados": resumen.insertados,
                        "omitidos_duplicados": resumen.omitidos_duplicados,
                        "detalle": resumen.mensaje,
                    }
                )
            st.markdown("### Resultado de la ingesta")
            st.dataframe(pd.DataFrame(resultados), width="stretch")

            if ejecutar:
                try:
                    with st.spinner("Materializando kardex y ejecutando pipeline..."):
                        materializar_kardex_cache(db, config)
                        _ejecutar_pipeline()
                    st.success("Pipeline completado. Dashboard actualizado.")
                    st.cache_resource.clear()
                except Exception:  # noqa: BLE001
                    st.error("El pipeline falló; revisa logs/pipeline.log.")
                    st.code(traceback.format_exc())

_mostrar_dashboard()
