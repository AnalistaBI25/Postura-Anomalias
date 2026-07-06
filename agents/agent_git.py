"""Agente 2: revisor de repositorio y Git (solo lectura)."""

from __future__ import annotations

import subprocess

from .base import ROOT, BaseAgent

RAMA_ESPERADA = "deploy-dashboard-chencopo"

ARCHIVOS_SENSIBLES = [
    ("config/project.yml", "Configuración con identificadores reales (centro, materiales, almacenes)."),
    ("reports/dashboard.html", "Dashboard con payload de datos operativos reales embebido."),
    ("data/warehouse.db", "Base operacional con movimientos reales."),
    (".env", "Variables de entorno."),
]


def _git(*args: str) -> str:
    resultado = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return resultado.stdout.strip()


class AgenteGit(BaseAgent):
    nombre = "revisor_git"
    categoria = "repositorio"

    def revisar(self) -> None:
        rama = _git("branch", "--show-current")
        self.metricas["rama"] = rama
        if rama != RAMA_ESPERADA:
            self.finding(
                "high",
                f"Rama activa '{rama}', se esperaba '{RAMA_ESPERADA}'.",
                impact="La revisión podría estar evaluando código equivocado.",
                recommendation=f"git checkout {RAMA_ESPERADA}",
                confidence=0.99,
            )
        else:
            self.finding(
                "info",
                f"Rama activa correcta: {rama}.",
                confidence=0.99,
            )

        sucio = _git("status", "--porcelain")
        self.metricas["arbol_limpio"] = not bool(sucio)
        if sucio:
            self.finding(
                "medium",
                f"Árbol de trabajo con cambios sin commitear:\n{sucio[:800]}",
                impact="La validación no correspondería a lo publicado.",
                recommendation="Commitear o descartar antes de validar el despliegue.",
            )

        pendientes = _git("log", "--oneline", f"origin/{RAMA_ESPERADA}..HEAD")
        if pendientes:
            self.finding(
                "medium",
                f"Commits locales sin push: {pendientes.splitlines()[:5]}",
                recommendation="git push origin " + RAMA_ESPERADA,
            )
        else:
            self.finding("info", "La rama local está sincronizada con origin.", confidence=0.95)

        vs_main = _git("diff", "main...HEAD", "--stat")
        n_archivos = len(vs_main.splitlines()) - 1 if vs_main else 0
        self.metricas["archivos_cambiados_vs_main"] = max(n_archivos, 0)

        trackeados = set(_git("ls-files").splitlines())
        for archivo, motivo in ARCHIVOS_SENSIBLES:
            if archivo in trackeados:
                self.finding(
                    "high",
                    f"Archivo sensible versionado: {archivo}. {motivo}",
                    file=archivo,
                    impact="Si el repositorio es público, expone datos internos.",
                    recommendation=(
                        "Confirmar visibilidad del repositorio; si es público, hacerlo "
                        "privado o retirar el archivo del índice y del historial."
                    ),
                    requires_business_validation=True,
                    confidence=0.95,
                )

        manifests = [f for f in trackeados if f.startswith("outputs/")]
        if manifests:
            self.finding(
                "medium",
                f"Artefactos generados versionados en outputs/: {manifests}. Contienen "
                "rutas absolutas locales (incluye nombre de usuario del equipo).",
                impact="Ruido de diffs en cada corrida y fuga menor de información local.",
                recommendation="Agregar outputs/ a .gitignore y retirarlos del índice.",
                confidence=0.9,
            )
