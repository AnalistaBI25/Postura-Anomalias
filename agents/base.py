"""Base del sistema de agentes: hallazgos estructurados y ejecución trazable.

Reglas de operación (Fase 1, solo lectura):
- Objetivo limitado por agente, entradas explícitas, salida estructurada.
- Los agentes citan archivos/líneas, separan hechos de recomendaciones e
  indican confianza. No modifican código ni datos.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from granjas_anomalias.config import ProjectConfig, load_config  # noqa: E402

CONFIG_PATH = ROOT / "config" / "project.yml"

SEVERIDADES = ("info", "low", "medium", "high", "critical")


def active_config() -> ProjectConfig:
    return load_config(CONFIG_PATH)


def farm_path(*parts: str) -> Path:
    return active_config().farm_root.joinpath(*parts)


@dataclass
class Finding:
    agent: str
    finding_id: str
    severity: str
    category: str
    file: str = ""
    component: str = ""
    evidence: str = ""
    impact: str = ""
    recommendation: str = ""
    requires_business_validation: bool = False
    confidence: float = 0.8
    status: str = "open"

    def __post_init__(self) -> None:
        if self.severity not in SEVERIDADES:
            raise ValueError(f"Severidad inválida: {self.severity}")


class BaseAgent:
    """Agente de solo lectura. Subclases implementan ``revisar()``."""

    nombre: str = "base"
    categoria: str = "general"
    modo: str = "solo_lectura"

    def __init__(self) -> None:
        self._contador = 0
        self.findings: list[Finding] = []
        self.metricas: dict[str, Any] = {}
        self.error: str = ""

    # ------------------------------------------------------------------
    def finding(
        self,
        severity: str,
        evidence: str,
        *,
        category: str | None = None,
        file: str = "",
        component: str = "",
        impact: str = "",
        recommendation: str = "",
        requires_business_validation: bool = False,
        confidence: float = 0.8,
    ) -> Finding:
        self._contador += 1
        prefijo = self.nombre.upper().replace("_", "")[:6]
        hallazgo = Finding(
            agent=self.nombre,
            finding_id=f"{prefijo}-{self._contador:03d}",
            severity=severity,
            category=category or self.categoria,
            file=file,
            component=component,
            evidence=evidence,
            impact=impact,
            recommendation=recommendation,
            requires_business_validation=requires_business_validation,
            confidence=confidence,
        )
        self.findings.append(hallazgo)
        return hallazgo

    # ------------------------------------------------------------------
    def revisar(self) -> None:  # pragma: no cover - abstracto
        raise NotImplementedError

    def ejecutar(self) -> dict[str, Any]:
        inicio = time.perf_counter()
        iniciado = datetime.now().isoformat(timespec="seconds")
        try:
            self.revisar()
            resultado = "OK"
        except Exception:  # noqa: BLE001 - el agente no debe ocultar errores
            self.error = traceback.format_exc()
            resultado = "ERROR"
        return {
            "agent": self.nombre,
            "modo": self.modo,
            "iniciado_en": iniciado,
            "duracion_segundos": round(time.perf_counter() - inicio, 2),
            "resultado": resultado,
            "error": self.error,
            "metricas": self.metricas,
            "n_hallazgos": len(self.findings),
            "hallazgos": [asdict(f) for f in self.findings],
        }


def guardar_reporte(reporte: dict[str, Any], directorio: Path) -> Path:
    directorio.mkdir(parents=True, exist_ok=True)
    destino = directorio / f"{reporte['agent']}.json"
    destino.write_text(
        json.dumps(reporte, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    return destino
