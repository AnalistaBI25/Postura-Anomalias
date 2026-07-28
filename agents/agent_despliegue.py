"""Agente 9: revisor de despliegue y reproducibilidad."""

from __future__ import annotations

import importlib
import re
import sys

from .base import ROOT, BaseAgent, farm_path

IMPORT_POR_PAQUETE = {
    "pandas": "pandas",
    "numpy": "numpy",
    "openpyxl": "openpyxl",
    "xlrd": "xlrd",
    "pyyaml": "yaml",
    "scikit-learn": "sklearn",
    "joblib": "joblib",
    "matplotlib": "matplotlib",
    "plotly": "plotly",
    "jinja2": "jinja2",
    "nbformat": "nbformat",
    "pytest": "pytest",
    "streamlit": "streamlit",
}

REQUERIDOS_ARRANQUE = [
    "streamlit_app.py",
    "config/project.yml",
    "streamlit_components/dashboard_shell/index.html",
    "requirements.txt",
]


class AgenteDespliegue(BaseAgent):
    nombre = "revisor_despliegue"
    categoria = "despliegue"

    def revisar(self) -> None:
        # 1) Dependencias declaradas vs importables
        requisitos = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        paquetes = [re.split(r"[<>=!\[]", linea.strip())[0].lower() for linea in requisitos if linea.strip()]
        faltantes = []
        for paquete in paquetes:
            modulo = IMPORT_POR_PAQUETE.get(paquete, paquete)
            try:
                importlib.import_module(modulo)
            except ImportError:
                faltantes.append(paquete)
        self.metricas["dependencias_declaradas"] = paquetes
        self.metricas["dependencias_no_importables"] = faltantes
        if faltantes:
            self.finding(
                "high",
                f"Dependencias declaradas que no importan en este entorno: {faltantes}.",
                file="requirements.txt",
                recommendation="pip install -r requirements.txt en el entorno de despliegue.",
            )
        else:
            self.finding(
                "info",
                f"Las {len(paquetes)} dependencias de requirements.txt importan correctamente "
                f"(python {sys.version.split()[0]}).",
                confidence=0.95,
            )

        # 2) Archivos necesarios para el arranque del deploy
        for archivo in REQUERIDOS_ARRANQUE:
            if not (ROOT / archivo).exists():
                self.finding(
                    "high",
                    f"Falta {archivo}, requerido para `streamlit run streamlit_app.py`.",
                    file=archivo,
                )
        if farm_path("reports", "dashboard.html").exists():
            self.finding(
                "info",
                "reports/dashboard.html presente: la app abre en modo consulta aunque la "
                "primera corrida del pipeline no se haya ejecutado en el servidor.",
                confidence=0.9,
            )

        # 3) Fallback sin PyYAML (arranque en Streamlit Cloud)
        config_src = (ROOT / "src" / "granjas_anomalias" / "config.py").read_text(encoding="utf-8")
        if "_parse_simple_yaml" in config_src:
            self.finding(
                "info",
                "config.py incluye un parser YAML de respaldo si PyYAML no está instalado "
                "(evita bloqueo del arranque en la nube). PyYAML sigue fijado en requirements.",
                file="src/granjas_anomalias/config.py",
                confidence=0.9,
            )

        # 4) Configuración de Streamlit
        cfg = ROOT / ".streamlit" / "config.toml"
        if not cfg.exists():
            self.finding(
                "low",
                "No existe .streamlit/config.toml: el límite de carga usa el default de "
                "Streamlit (200 MB), mayor que el max_file_mb=100 validado en la ingesta.",
                recommendation=(
                    "Crear .streamlit/config.toml con maxUploadSize=100 para rechazar "
                    "archivos grandes antes de transferirlos."
                ),
                confidence=0.85,
            )

        # 5) Rollback y persistencia
        if farm_path("outputs", "history").exists():
            self.finding(
                "info",
                "Existe outputs/history/<año>/<mes>/run_* con manifiestos por ejecución "
                "(evidencia para rollback de resultados).",
                confidence=0.85,
            )
        self.finding(
            "medium",
            "En Streamlit Community Cloud el sistema de archivos es efímero: "
            "data/warehouse.db y reports/dashboard.html regenerados se pierden en cada "
            "reinicio del contenedor; solo persiste lo commiteado en la rama.",
            impact="Las cargas y revisiones hechas en la nube no sobreviven reinicios.",
            recommendation=(
                "Para validación es aceptable (documentarlo al usuario). Para producción: "
                "servidor propio o volumen persistente."
            ),
            requires_business_validation=True,
            confidence=0.9,
        )
