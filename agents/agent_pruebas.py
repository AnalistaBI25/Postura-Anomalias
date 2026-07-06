"""Agente 8: ejecutor de pruebas (pytest + validadores del dashboard)."""

from __future__ import annotations

import re
import subprocess
import sys

from .base import ROOT, BaseAgent


def _correr(comando: list[str], timeout: int = 900) -> tuple[int, str]:
    r = subprocess.run(
        comando,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    return r.returncode, (r.stdout + "\n" + r.stderr)[-6000:]


class AgentePruebas(BaseAgent):
    nombre = "ejecutor_pruebas"
    categoria = "pruebas"

    def revisar(self) -> None:
        # pyproject define addopts="-q"; se neutraliza para que pytest imprima
        # la línea de resumen "N passed" que este agente necesita.
        codigo, salida = _correr(
            [
                sys.executable,
                "-m",
                "pytest",
                "-o",
                "addopts=",
                "-q",
                "--tb=short",
                "-p",
                "no:warnings",
            ]
        )
        m = re.search(r"(\d+) passed", salida)
        fallos = re.search(r"(\d+) failed", salida)
        self.metricas["pytest"] = {
            "exit_code": codigo,
            "passed": int(m.group(1)) if m else None,
            "failed": int(fallos.group(1)) if fallos else 0,
        }
        if codigo == 0:
            self.finding(
                "info",
                f"pytest: {m.group(1) if m else '?'} pruebas pasan (exit 0).",
                confidence=0.98,
            )
        else:
            self.finding(
                "critical",
                f"pytest falló (exit {codigo}). Detalle:\n{salida[-1500:]}",
                impact="Regresiones activas; no apto para PR.",
                recommendation="Corregir antes de continuar.",
                confidence=0.98,
            )

        for script, nombre in [
            ("scripts/validar_dashboard_payload.py", "payload"),
            ("scripts/validar_dashboard_html.py", "html"),
        ]:
            if not (ROOT / script).exists():
                continue
            codigo, salida = _correr([sys.executable, script], timeout=300)
            self.metricas[f"validador_{nombre}"] = codigo
            if codigo == 0:
                self.finding("info", f"Validador de {nombre} del dashboard: OK.", confidence=0.95)
            else:
                self.finding(
                    "high",
                    f"Validador de {nombre} falló (exit {codigo}): {salida[-800:]}",
                    file=script,
                    recommendation="Regenerar el dashboard y revisar el payload.",
                    confidence=0.9,
                )
