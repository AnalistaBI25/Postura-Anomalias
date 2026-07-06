"""Agente 7: revisor CRUD y seguridad (solo lectura)."""

from __future__ import annotations

import re
import subprocess
import urllib.request

from .base import ROOT, BaseAgent

PATRONES_SECRETO = re.compile(
    r"(api[_-]?key|secret|token|password|contrase|aws_access|private[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}",
    re.IGNORECASE,
)


def _git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return r.stdout.strip()


class AgenteSeguridad(BaseAgent):
    nombre = "revisor_seguridad"
    categoria = "seguridad"

    def revisar(self) -> None:
        # 1) Visibilidad del repositorio remoto
        remoto = _git("remote", "get-url", "origin")
        publico = None
        if "github.com" in remoto:
            url = remoto.replace(".git", "").replace("git@github.com:", "https://github.com/")
            try:
                with urllib.request.urlopen(url, timeout=6) as resp:  # noqa: S310
                    publico = resp.status == 200
            except Exception:  # noqa: BLE001 - 404 u offline
                publico = False
        self.metricas["repo_publico"] = publico

        trackeados = set(_git("ls-files").splitlines())
        sensibles = [
            a
            for a in ("config/project.yml", "reports/dashboard.html")
            if a in trackeados
        ]
        if publico and sensibles:
            self.finding(
                "critical",
                f"El repositorio {remoto} es PÚBLICO y versiona {sensibles} con datos "
                "operativos reales (centro, materiales, órdenes, lotes y consumo embebidos).",
                impact="Exposición de información interna de la empresa a cualquier persona.",
                recommendation=(
                    "Hacer el repositorio privado (Streamlit Cloud soporta repos privados) "
                    "o retirar estos archivos del índice e historial (git filter-repo) antes "
                    "del PR a main."
                ),
                requires_business_validation=True,
                confidence=0.95,
            )
        elif sensibles:
            self.finding(
                "medium",
                f"Repositorio privado pero versiona datos reales: {sensibles}.",
                recommendation="Confirmar que el acceso al repo esté restringido al equipo.",
                requires_business_validation=True,
            )

        # 2) Secretos en archivos versionados
        hallazgos_secretos = []
        for archivo in trackeados:
            ruta = ROOT / archivo
            if ruta.suffix.lower() in {".py", ".yml", ".yaml", ".toml", ".md", ".txt", ".json"}:
                try:
                    texto = ruta.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue
                for m in PATRONES_SECRETO.finditer(texto):
                    fragmento = m.group(0)[:60]
                    if "example" in archivo or "EXAMPLE" in fragmento:
                        continue
                    hallazgos_secretos.append(f"{archivo}: {fragmento}")
        self.metricas["candidatos_secreto"] = len(hallazgos_secretos)
        if hallazgos_secretos:
            self.finding(
                "high",
                "Posibles secretos en archivos versionados: "
                + "; ".join(hallazgos_secretos[:5]),
                recommendation="Mover a variables de entorno / st.secrets y rotar credenciales.",
                confidence=0.6,
            )
        else:
            self.finding("info", "Sin patrones de credenciales en archivos versionados.", confidence=0.7)

        # 3) Superficie de la app Streamlit
        app = (ROOT / "streamlit_app.py").read_text(encoding="utf-8")
        if "st.secrets" not in app and "password" not in app.lower():
            self.finding(
                "high",
                "La app Streamlit no tiene autenticación: cualquiera con la URL puede "
                "cargar archivos, ejecutar el pipeline y registrar revisiones.",
                file="streamlit_app.py",
                impact="Escrituras anónimas en SQLite y consumo de cómputo del despliegue.",
                recommendation=(
                    "Para el despliegue de validación: mantener la URL restringida o activar "
                    "un token simple (st.secrets) antes de aceptar eventos de carga/revisión."
                ),
                requires_business_validation=True,
                confidence=0.9,
            )
        if "traceback.format_exc" in app:
            self.finding(
                "low",
                "La app devuelve el traceback completo al frontend en errores de carga.",
                file="streamlit_app.py",
                component="_process_upload_event",
                impact="Revela rutas internas y estructura del código al usuario.",
                recommendation="Registrar el traceback en logs y mostrar mensaje genérico.",
                confidence=0.9,
            )
        if 'Path(str(file_info.get("name"' in app and ".name" in app:
            self.finding(
                "info",
                "La carga sanea el nombre de archivo con Path(...).name (mitiga path "
                "traversal) y valida extensión/tamaño en la ingesta.",
                file="streamlit_app.py",
                confidence=0.85,
            )

        # 4) CRUD y auditoría
        db_src = (ROOT / "src" / "granjas_anomalias" / "db.py").read_text(encoding="utf-8")
        tiene_auditoria = "revision_eventos" in db_src or "leer_revision_eventos" in db_src
        if tiene_auditoria:
            self.finding(
                "info",
                "La revisión de alertas usa borrado lógico con auditoría de eventos "
                "(quién, cuándo, valor anterior/nuevo) en SQLite.",
                file="src/granjas_anomalias/db.py",
                confidence=0.85,
            )
        else:
            self.finding(
                "medium",
                "No se encontró bitácora de eventos de revisión (auditoría).",
                file="src/granjas_anomalias/db.py",
                recommendation="Registrar cada cambio de estado con usuario y timestamp.",
            )
        if "usuario" in app and "reviewUser" in (
            (ROOT / "streamlit_components" / "dashboard_shell" / "index.html").read_text(
                encoding="utf-8", errors="ignore"
            )
        ):
            self.finding(
                "low",
                "El usuario de la revisión es texto libre del formulario (no identidad "
                "verificada).",
                file="streamlit_components/dashboard_shell/index.html",
                impact="La auditoría registra lo que el usuario declare.",
                recommendation="Aceptable en validación; ligar a autenticación en producción.",
                requires_business_validation=True,
                confidence=0.9,
            )

        # 5) Datos crudos inmutables
        ingestion = (ROOT / "src" / "granjas_anomalias" / "ingestion.py").read_text(
            encoding="utf-8"
        )
        if "shutil.copy2" in ingestion and "raw" in ingestion:
            self.finding(
                "info",
                "Los archivos crudos se copian de forma inmutable (data/raw/cargas) y las "
                "operaciones CRUD nunca modifican el kardex original.",
                file="src/granjas_anomalias/ingestion.py",
                confidence=0.9,
            )
