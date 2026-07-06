"""Agente 10: revisor documental."""

from __future__ import annotations

from .base import ROOT, BaseAgent

DOCS_REQUERIDOS = [
    "README.md",
    "docs/arquitectura.md",
    "docs/fuentes_datos.md",
    "docs/diccionario_datos.md",
    "docs/reglas_negocio.md",
    "docs/ejecucion_dashboard.md",
    "docs/data_science.md",
    "docs/ui_ux.md",
    "docs/operaciones_crud.md",
    "docs/rendimiento_big_o.md",
    "docs/pruebas_rendimiento.md",
    "docs/agentes_arquitectura.md",
    "docs/agentes_evaluacion.md",
    "docs/pruebas.md",
    "docs/seguridad.md",
    "docs/despliegue.md",
    "docs/monitoreo_metricas.md",
    "docs/limitaciones.md",
    "docs/plan_mejoras.md",
    "docs/checklist_produccion.md",
    "docs/entregable_final.md",
]

# Documentos existentes que ya cubren un tema con otro nombre.
EQUIVALENTES = {
    "docs/arquitectura.md": ["docs/ARQUITECTURA.md", "docs/architecture.md"],
    "docs/diccionario_datos.md": ["docs/DICCIONARIO_DATOS.md", "docs/data_dictionary.md"],
    "docs/fuentes_datos.md": ["docs/EXTRACCION_DATOS_SAP.md"],
    "docs/reglas_negocio.md": ["docs/REGLAS_MOVIMIENTOS_SAP.md", "docs/DECISIONES_PROYECTO.md"],
    "docs/ejecucion_dashboard.md": ["docs/MANUAL_USUARIO.md", "docs/runbook.md"],
    "docs/entregable_final.md": ["docs/ENTREGABLE_FINAL_PROYECTO.md"],
}


class AgenteDocumental(BaseAgent):
    nombre = "revisor_documental"
    categoria = "documentacion"

    def revisar(self) -> None:
        faltantes, cubiertos = [], []
        for doc in DOCS_REQUERIDOS:
            if (ROOT / doc).exists():
                cubiertos.append(doc)
                continue
            equivalentes = [e for e in EQUIVALENTES.get(doc, []) if (ROOT / e).exists()]
            if equivalentes:
                cubiertos.append(f"{doc} (cubierto por {equivalentes[0]})")
            else:
                faltantes.append(doc)
        self.metricas["documentos_cubiertos"] = len(cubiertos)
        self.metricas["documentos_faltantes"] = faltantes
        if faltantes:
            self.finding(
                "medium",
                f"Documentos requeridos sin crear: {faltantes}",
                recommendation="Crear los documentos con contenido basado en evidencia.",
                confidence=0.95,
            )
        else:
            self.finding(
                "info",
                f"Los {len(DOCS_REQUERIDOS)} documentos requeridos existen o están "
                "cubiertos por un equivalente.",
                confidence=0.95,
            )

        # Afirmaciones sin evidencia: el entregable no debe declarar probado lo no probado.
        entregable = ROOT / "docs" / "entregable_final.md"
        if not entregable.exists():
            entregable = ROOT / "docs" / "ENTREGABLE_FINAL_PROYECTO.md"
        if entregable.exists():
            texto = entregable.read_text(encoding="utf-8", errors="ignore").lower()
            if "produccion" in texto and "listo para produccion" in texto.replace("ó", "o"):
                self.finding(
                    "low",
                    f"{entregable.name} declara preparación para producción; verificar que "
                    "cada afirmación tenga evidencia adjunta.",
                    file=str(entregable.relative_to(ROOT)),
                    confidence=0.6,
                )
