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
        padding: 0.8rem 1rem 0;
      }
      header, footer { visibility: hidden; }
      div[data-testid="stToolbar"] { display: none; }
      .stApp {
        background: #eef7fb;
      }

      div[data-testid="stHorizontalBlock"] {
        align-items: stretch;
      }

      .side-shell,
      .status-card,
      .result-card {
        border: 1px solid #bfe7f6;
        background: #ffffff;
        box-shadow: 0 14px 34px rgba(7, 75, 120, 0.08);
      }
      .side-shell {
        border-radius: 18px;
        padding: 1rem;
        margin-bottom: 0.85rem;
      }
      .side-eyebrow {
        color: #2c6b9b;
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0;
        text-transform: uppercase;
        margin-bottom: 0.35rem;
      }
      .side-title {
        color: #173f8a;
        font-size: 1.45rem;
        line-height: 1.08;
        font-weight: 850;
        margin: 0 0 0.45rem;
      }
      .side-copy {
        color: #2d5878;
        font-size: 0.94rem;
        line-height: 1.35;
        margin: 0;
      }
      .side-pill-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        margin-top: 0.85rem;
      }
      .side-pill {
        border: 1px solid #a9dff2;
        border-radius: 999px;
        color: #17458f;
        background: #f6fcff;
        font-size: 0.78rem;
        font-weight: 700;
        padding: 0.35rem 0.55rem;
      }
      .status-card,
      .result-card {
        border-radius: 14px;
        padding: 0.8rem 0.9rem;
        margin: 0.7rem 0;
      }
      .status-label {
        color: #2c6b9b;
        font-size: 0.78rem;
        font-weight: 800;
        margin: 0;
      }
      .status-value {
        color: #173f8a;
        font-size: 1rem;
        font-weight: 800;
        margin: 0.1rem 0 0;
      }
      .status-note {
        color: #2b5d88;
        font-size: 0.84rem;
        margin: 0.15rem 0 0;
      }
      .result-ok { color: #226b48; }
      .result-warn { color: #9a5a00; }
      .result-bad { color: #a23a3a; }
      .section-label {
        color: #173f8a;
        font-size: 0.95rem;
        font-weight: 850;
        margin: 0.8rem 0 0.35rem;
      }
      div[data-testid="stFileUploader"] {
        background: #ffffff;
        border: 1px solid #bfe7f6;
        border-radius: 16px;
        padding: 0.75rem;
        box-shadow: 0 10px 22px rgba(7, 75, 120, 0.06);
      }
      div[data-testid="stFileUploaderDropzone"] {
        border-color: #2aaee8;
        background: #f8fdff;
        min-height: 118px;
      }
      div[data-testid="stProgress"] > div > div > div {
        background-color: #16a6d7;
      }
      .stButton > button,
      .stDownloadButton > button {
        width: 100%;
        border-radius: 12px;
        border: 1px solid #17458f;
        background: #17458f;
        color: #ffffff;
        font-weight: 800;
      }
      .stButton > button:disabled {
        border-color: #c7d3e1;
        background: #e8eef5;
        color: #8794a6;
      }
      .dashboard-shell {
        max-width: 100%;
        margin: 0 auto;
        border-radius: 20px;
        overflow: hidden;
        background: #ffffff;
        box-shadow: 0 18px 42px rgba(7, 75, 120, 0.1);
      }
      .dashboard-heading {
        background: #ffffff;
        border: 1px solid #bfe7f6;
        border-radius: 18px;
        padding: 0.8rem 1rem;
        margin-bottom: 0.7rem;
        box-shadow: 0 10px 24px rgba(7, 75, 120, 0.07);
      }
      .dashboard-heading h2 {
        color: #173f8a;
        font-size: 1.2rem;
        font-weight: 850;
        margin: 0;
      }
      .dashboard-heading p {
        color: #2b5d88;
        margin: 0.15rem 0 0;
        font-size: 0.9rem;
      }
      @media (max-width: 900px) {
        .block-container { padding: 0.65rem; }
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
    st.markdown(
        """
        <div class="dashboard-heading">
          <h2>Dashboard productivo</h2>
          <p>Las alertas y controles operativos viven dentro del tablero HTML.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<div class="dashboard-shell">', unsafe_allow_html=True)
    if DASHBOARD_PATH.exists():
        components.html(
            DASHBOARD_PATH.read_text(encoding="utf-8"),
            height=1550,
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

upload_col, dashboard_col = st.columns([0.28, 0.72], gap="medium")

if config_error is not None:
    with upload_col:
        st.markdown(
            """
            <section class="side-shell">
              <div class="side-eyebrow">Carga SAP</div>
              <h1 class="side-title">No disponible</h1>
              <p class="side-copy">
                No se pudo cargar la configuracion. El tablero queda visible en modo consulta.
              </p>
            </section>
            """,
            unsafe_allow_html=True,
        )
        st.warning("La carga SAP queda deshabilitada.")
        st.code(str(config_error))
    with dashboard_col:
        _mostrar_dashboard()
    st.stop()

if db is None or config is None:
    with upload_col:
        st.markdown(
            """
            <section class="side-shell">
              <div class="side-eyebrow">Carga SAP</div>
              <h1 class="side-title">Modo consulta</h1>
              <p class="side-copy">
                Para activar la carga, la rama publicada debe incluir config/project.yml.
              </p>
            </section>
            """,
            unsafe_allow_html=True,
        )
    with dashboard_col:
        _mostrar_dashboard()
    st.stop()

from granjas_anomalias.ingestion import (  # noqa: E402
    ingerir_archivo,
    materializar_kardex_cache,
    validar_archivo,
)

with upload_col:
    st.markdown(
        """
        <section class="side-shell">
          <div class="side-eyebrow">Entrada de datos</div>
          <h1 class="side-title">Carga SAP</h1>
          <p class="side-copy">
            Sube exportaciones MB51. Al confirmar se recalculan indicadores,
            alertas integradas y el dashboard HTML.
          </p>
          <div class="side-pill-row">
            <span class="side-pill">MB51</span>
            <span class="side-pill">XLSX / XLS / CSV</span>
            <span class="side-pill">Pipeline completo</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    minimo, maximo = db.rango_existente(str(config.project["center_id"]))
    if minimo:
        st.markdown(
            f"""
            <div class="status-card">
              <p class="status-label">Historico cargado</p>
              <p class="status-value">Centro {config.project['center_id']}</p>
              <p class="status-note">{minimo} a {maximo}</p>
            </div>
            """,
            unsafe_allow_html=True,
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

    progress = st.progress(0, text="Esperando archivo SAP")
    archivos = st.file_uploader(
        "Selecciona o arrastra uno o varios archivos",
        type=["xlsx", "xls", "csv"],
        accept_multiple_files=True,
    )

    if archivos:
        progress.progress(10, text="Archivo recibido")
        incoming = config.root / config.ingestion.get("incoming_dir", "data/incoming")
        incoming.mkdir(parents=True, exist_ok=True)
        informes = []
        rutas = []
        total_archivos = max(len(archivos), 1)
        for index, archivo in enumerate(archivos, start=1):
            destino = incoming / archivo.name
            destino.write_bytes(archivo.getbuffer())
            rutas.append(destino)
            avance = 20 + int((index / total_archivos) * 30)
            progress.progress(avance, text=f"Validando {archivo.name}")
            informes.append(validar_archivo(destino, config, db))

        progress.progress(55, text="Validacion completada")
        st.markdown('<p class="section-label">Validacion</p>', unsafe_allow_html=True)
        resumen_df = pd.DataFrame([inf.resumen() for inf in informes])
        columnas_resumen = [
            c
            for c in ["archivo", "fuente", "valido", "n_registros", "fecha_min", "fecha_max"]
            if c in resumen_df.columns
        ]
        st.dataframe(resumen_df[columnas_resumen], width="stretch", hide_index=True)

        for informe, ruta in zip(informes, rutas):
            with st.expander(f"Detalle - {informe.archivo}", expanded=False):
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
        st.markdown(
            f"""
            <div class="result-card">
              <p class="status-label">Resultado de validacion</p>
              <p class="status-value {'result-ok' if validos else 'result-bad'}">
                {len(validos)} de {len(informes)} archivo(s) listos
              </p>
              <p class="status-note">Confirma para actualizar el dashboard.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
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
            progress.progress(65, text="Registrando movimientos")
            total_validos = max(len(validos), 1)
            for index, (informe, ruta) in enumerate(validos, start=1):
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
                avance = 65 + int((index / total_validos) * 15)
                progress.progress(avance, text=f"Procesado {ruta.name}")

            if ejecutar:
                try:
                    progress.progress(84, text="Materializando datos")
                    with st.spinner("Materializando kardex y ejecutando pipeline..."):
                        materializar_kardex_cache(db, config)
                        progress.progress(92, text="Regenerando dashboard HTML")
                        _ejecutar_pipeline()
                    progress.progress(100, text="Dashboard actualizado")
                    st.success("Pipeline completado. Dashboard actualizado.")
                    if resultados:
                        st.dataframe(pd.DataFrame(resultados), width="stretch", hide_index=True)
                    st.cache_resource.clear()
                except Exception:  # noqa: BLE001
                    progress.progress(100, text="El pipeline fallo")
                    st.error("El pipeline falló; revisa logs/pipeline.log.")
                    st.code(traceback.format_exc())
            elif resultados:
                progress.progress(100, text="Carga registrada")
                st.dataframe(pd.DataFrame(resultados), width="stretch", hide_index=True)

with dashboard_col:
    _mostrar_dashboard()
