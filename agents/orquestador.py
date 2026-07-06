"""Agente 1: orquestador del sistema de revisión (Fase 1, solo lectura).

Ejecuta a los agentes en orden, consolida hallazgos, detecta contradicciones
simples y genera el reporte en ``reports/agentes/<timestamp>/``.

Uso:
    python -m agents.orquestador [--skip pruebas rendimiento ...]

El orquestador NO modifica código, NO hace push/merge y NO borra datos.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime

from .agent_datos import AgenteDatos
from .agent_despliegue import AgenteDespliegue
from .agent_documental import AgenteDocumental
from .agent_ds import AgenteDS
from .agent_git import AgenteGit
from .agent_pruebas import AgentePruebas
from .agent_rendimiento import AgenteRendimiento
from .agent_seguridad import AgenteSeguridad
from .base import ROOT, guardar_reporte

ORDEN_SEVERIDAD = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

AGENTES = {
    "git": AgenteGit,
    "datos": AgenteDatos,
    "ds": AgenteDS,
    "rendimiento": AgenteRendimiento,
    "seguridad": AgenteSeguridad,
    "pruebas": AgentePruebas,
    "despliegue": AgenteDespliegue,
    "documental": AgenteDocumental,
}


def _detectar_contradicciones(hallazgos: list[dict]) -> list[str]:
    contradicciones = []
    criticos = [h for h in hallazgos if h["severity"] in ("critical", "high")]
    pruebas_ok = any(
        h["agent"] == "ejecutor_pruebas" and h["severity"] == "info" for h in hallazgos
    )
    if pruebas_ok and criticos:
        contradicciones.append(
            "Las pruebas automatizadas pasan, pero existen hallazgos critical/high: "
            "las pruebas actuales no cubren esos riesgos (seguridad/despliegue)."
        )
    return contradicciones


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip", nargs="*", default=[], choices=sorted(AGENTES))
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    salida = ROOT / "reports" / "agentes" / timestamp
    reportes, hallazgos = [], []

    for clave, cls in AGENTES.items():
        if clave in args.skip:
            continue
        agente = cls()
        print(f"== Ejecutando {agente.nombre} (modo {agente.modo})")
        reporte = agente.ejecutar()
        guardar_reporte(reporte, salida)
        reportes.append(reporte)
        hallazgos.extend(reporte["hallazgos"])
        print(
            f"   {reporte['resultado']} | {reporte['n_hallazgos']} hallazgos "
            f"| {reporte['duracion_segundos']}s"
        )

    hallazgos.sort(key=lambda h: (ORDEN_SEVERIDAD.get(h["severity"], 9), h["agent"]))
    contradicciones = _detectar_contradicciones(hallazgos)
    consolidado = {
        "generado_en": datetime.now().isoformat(timespec="seconds"),
        "fase_agentes": "1-solo-lectura",
        "agentes_ejecutados": [r["agent"] for r in reportes],
        "errores_agentes": [r["agent"] for r in reportes if r["resultado"] != "OK"],
        "por_severidad": {
            sev: sum(1 for h in hallazgos if h["severity"] == sev)
            for sev in ORDEN_SEVERIDAD
        },
        "contradicciones": contradicciones,
        "hallazgos": hallazgos,
    }
    (salida / "hallazgos_consolidados.json").write_text(
        json.dumps(consolidado, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    lineas = [
        "# Revisión por agentes — resumen",
        "",
        f"- Generado: {consolidado['generado_en']}  ",
        f"- Fase: {consolidado['fase_agentes']} (sin permisos de escritura sobre código/datos)  ",
        f"- Agentes: {', '.join(consolidado['agentes_ejecutados'])}  ",
        f"- Severidades: {consolidado['por_severidad']}",
        "",
    ]
    if contradicciones:
        lineas += ["## Contradicciones detectadas", ""]
        lineas += [f"- {c}" for c in contradicciones] + [""]
    lineas += ["## Hallazgos (ordenados por severidad)", ""]
    lineas += [
        "| ID | Sev | Agente | Evidencia | Recomendación |",
        "|---|---|---|---|---|",
    ]
    for h in hallazgos:
        if h["severity"] == "info":
            continue
        evidencia = h["evidence"].replace("\n", " ")[:160]
        recomendacion = h["recommendation"].replace("\n", " ")[:120]
        lineas.append(
            f"| {h['finding_id']} | {h['severity']} | {h['agent']} | {evidencia} | {recomendacion} |"
        )
    lineas += [
        "",
        "## Validaciones en verde (info)",
        "",
    ]
    for h in hallazgos:
        if h["severity"] == "info":
            lineas.append(f"- [{h['finding_id']}] {h['evidence'].splitlines()[0][:180]}")
    (salida / "resumen.md").write_text("\n".join(lineas), encoding="utf-8")

    print(f"\nReporte consolidado: {salida}")
    print(f"Severidades: {consolidado['por_severidad']}")
    if contradicciones:
        print("Contradicciones:", *contradicciones, sep="\n - ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
