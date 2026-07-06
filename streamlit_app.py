"""Punto de entrada Streamlit del proyecto.

Pestañas:
- Dashboard: el HTML autocontenido generado por el pipeline (sin cambios).
- Carga SAP: subir exportaciones MB51 crudas, validarlas, confirmarlas y
  procesarlas de forma incremental e idempotente.
- Alertas: revisión de alertas consolidadas con estados manuales persistentes.
- Historial: registro de cargas y ejecuciones.

Ejecutar con: ``streamlit run streamlit_app.py``
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

ESTADOS_MANUALES = ["PENDIENTE", "CONFIRMADA", "FALSO_POSITIVO", "PROBLEMA_DE_DATOS"]

st.set_page_config(
    page_title="BI Anomalías Avícolas",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .block-container { max-width: 100%; padding-top: 1rem; }
      header, footer { visibility: hidden; }
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


# ----------------------------------------------------------------------
# Pestañas
# ----------------------------------------------------------------------
config = None
db = None
config_error = None
if CONFIG_PATH.exists():
    try:
        config = _cargar_config()
        db = _warehouse(config)
    except Exception as exc:  # noqa: BLE001
        config_error = exc

tabs = st.tabs(
    ["📊 Dashboard", "📤 Carga SAP", "🚨 Alertas", "🗂️ Historial"]
    if db is not None
    else ["📊 Dashboard"]
)
tab_dash = tabs[0]
if db is not None:
    tab_carga, tab_alertas, tab_historial = tabs[1:]

# ---------------------------------------------------------------- Dashboard
with tab_dash:
    if config_error is not None:
        st.warning(
            "No se pudo cargar config/project.yml. Se muestra solo el dashboard "
            "publicado; las funciones de carga y alertas quedan deshabilitadas."
        )
        st.code(str(config_error))
    elif not CONFIG_PATH.exists():
        st.info(
            "Modo dashboard publicado: config/project.yml no está versionado. "
            "Las funciones de carga SAP, alertas e historial se habilitan en el "
            "entorno local cuando existe ese archivo."
        )

    if DASHBOARD_PATH.exists():
        components.html(
            DASHBOARD_PATH.read_text(encoding="utf-8"), height=1400, scrolling=True
        )
    else:
        st.info(
            "Aún no existe reports/dashboard.html. Carga un archivo en la pestaña "
            "'Carga SAP' y ejecuta el pipeline, o corre "
            "`python -m granjas_anomalias.cli run --config config/project.yml`."
        )

if db is None or config is None:
    st.stop()

from granjas_anomalias.ingestion import (  # noqa: E402
    ingerir_archivo,
    materializar_kardex_cache,
    validar_archivo,
)

# ---------------------------------------------------------------- Carga SAP
with tab_carga:
    st.subheader("Carga de exportaciones SAP (MB51 crudo)")
    st.caption(
        "Formato soportado: exportación directa de MB51 (misma estructura que el "
        "kardex del proyecto, hoja 'Data'). Los archivos crudos se conservan "
        "intactos; recargar un archivo o un periodo traslapado no duplica movimientos."
    )

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
        if st.button("Inicializar histórico desde config (kardex configurado)"):
            kardex_path = config.resolve("kardex_excel")
            with st.spinner(f"Ingiriendo {kardex_path.name}…"):
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
        st.markdown("### 2 · Confirmación")
        ejecutar = st.checkbox(
            "Ejecutar pipeline completo al confirmar (recalcula indicadores, "
            "anomalías, alertas y dashboard)",
            value=True,
        )
        if st.button(f"Confirmar carga de {len(validos)} archivo(s) válido(s)", disabled=not validos):
            resultados = []
            for informe, ruta in validos:
                with st.spinner(f"Procesando {ruta.name}…"):
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
            st.markdown("### 3 · Resultado de la ingesta")
            st.dataframe(pd.DataFrame(resultados), width="stretch")

            if ejecutar:
                try:
                    with st.spinner("Materializando kardex y ejecutando pipeline…"):
                        materializar_kardex_cache(db, config)
                        _ejecutar_pipeline()
                    st.success("Pipeline completado. Dashboard y alertas actualizados.")
                    st.cache_resource.clear()
                except Exception:  # noqa: BLE001
                    st.error("El pipeline falló; revisa logs/pipeline.log.")
                    st.code(traceback.format_exc())

# ---------------------------------------------------------------- Alertas
with tab_alertas:
    st.subheader("Alertas consolidadas")
    todas = db.leer_alertas()
    if todas.empty:
        st.info("Aún no hay alertas registradas. Ejecuta el pipeline al menos una vez.")
    else:
        ultimo_run = todas.sort_values("creado_en")["run_id"].iloc[-1]
        vigentes = todas.loc[todas["run_id"].eq(ultimo_run)].copy()
        revisiones = db.leer_revisiones()
        if not revisiones.empty:
            vigentes = vigentes.merge(
                revisiones[["clave_seguimiento", "estado_manual", "comentario"]],
                on="clave_seguimiento",
                how="left",
            )
        else:
            vigentes["estado_manual"] = pd.NA
            vigentes["comentario"] = pd.NA
        vigentes["estado_manual"] = vigentes["estado_manual"].fillna("PENDIENTE")
        vigentes["comentario"] = vigentes["comentario"].fillna("")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            filtro_sev = st.multiselect(
                "Severidad", sorted(vigentes["severidad"].dropna().unique().tolist())
            )
        with c2:
            filtro_fam = st.multiselect(
                "Familia", sorted(vigentes["familia"].dropna().unique().tolist())
            )
        with c3:
            filtro_estado = st.multiselect(
                "Estado", sorted(vigentes["estado"].dropna().unique().tolist())
            )
        with c4:
            filtro_tr = st.multiselect(
                "Tipo de resultado",
                sorted(vigentes["tipo_resultado"].dropna().unique().tolist()),
            )

        vista = vigentes
        if filtro_sev:
            vista = vista.loc[vista["severidad"].isin(filtro_sev)]
        if filtro_fam:
            vista = vista.loc[vista["familia"].isin(filtro_fam)]
        if filtro_estado:
            vista = vista.loc[vista["estado"].isin(filtro_estado)]
        if filtro_tr:
            vista = vista.loc[vista["tipo_resultado"].isin(filtro_tr)]

        resumen_cols = st.columns(5)
        for etiqueta, cuenta, col in [
            ("Críticas", (vista["severidad"] == "critica").sum(), resumen_cols[0]),
            ("Altas", (vista["severidad"] == "alta").sum(), resumen_cols[1]),
            ("Nuevas", (vista["estado"] == "nueva").sum(), resumen_cols[2]),
            ("Persistentes", (vista["estado"] == "persistente").sum(), resumen_cols[3]),
            ("Resueltas", (vista["estado"] == "resuelta").sum(), resumen_cols[4]),
        ]:
            col.metric(etiqueta, int(cuenta))

        columnas_vista = [
            "severidad",
            "estado",
            "familia",
            "tipo",
            "tipo_resultado",
            "caseta",
            "material",
            "cycle_id",
            "fecha_inicial",
            "fecha_final",
            "valor_real",
            "valor_esperado",
            "diferencia_pct",
            "capas",
            "n_capas",
            "motivo",
            "recomendacion",
            "estado_manual",
            "comentario",
            "clave_seguimiento",
        ]
        editable = st.data_editor(
            vista[columnas_vista],
            width="stretch",
            hide_index=True,
            disabled=[c for c in columnas_vista if c not in ("estado_manual", "comentario")],
            column_config={
                "estado_manual": st.column_config.SelectboxColumn(
                    "Revisión manual", options=ESTADOS_MANUALES
                ),
                "comentario": st.column_config.TextColumn("Comentario"),
                "clave_seguimiento": None,
            },
            key="editor_alertas",
        )
        if st.button("Guardar revisiones manuales"):
            guardadas = 0
            for _, fila in editable.iterrows():
                original = vigentes.loc[
                    vigentes["clave_seguimiento"].eq(fila["clave_seguimiento"])
                ].iloc[0]
                if (
                    fila["estado_manual"] != original["estado_manual"]
                    or fila["comentario"] != original["comentario"]
                ):
                    db.guardar_revision(
                        fila["clave_seguimiento"],
                        str(fila["estado_manual"]),
                        str(fila["comentario"]),
                        usuario="dashboard",
                    )
                    guardadas += 1
            st.success(f"{guardadas} revisión(es) guardada(s).")

        st.download_button(
            "Descargar alertas filtradas (CSV)",
            vista.to_csv(index=False).encode("utf-8-sig"),
            file_name="alertas_filtradas.csv",
            mime="text/csv",
        )

# ---------------------------------------------------------------- Historial
with tab_historial:
    st.subheader("Historial de cargas")
    cargas = db.listar_cargas()
    if cargas.empty:
        st.info("No hay cargas registradas.")
    else:
        st.dataframe(cargas, width="stretch")

    st.subheader("Ejecuciones del pipeline")
    with db.connect() as conn:
        ejecuciones = pd.read_sql_query(
            "SELECT * FROM ejecuciones ORDER BY iniciado_en DESC", conn
        )
    if ejecuciones.empty:
        st.info("No hay ejecuciones registradas.")
    else:
        st.dataframe(ejecuciones, width="stretch")
