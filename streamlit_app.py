from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components


DASHBOARD_PATH = Path(__file__).parent / "reports" / "dashboard.html"


st.set_page_config(
    page_title="Dashboard BI Productivo",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
      .block-container {
        max-width: 100%;
        padding: 0;
      }
      header, footer {
        visibility: hidden;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

if not DASHBOARD_PATH.exists():
    st.error("No se encontro reports/dashboard.html en el despliegue.")
    st.stop()

dashboard_html = DASHBOARD_PATH.read_text(encoding="utf-8")
components.html(dashboard_html, height=1400, scrolling=True)
