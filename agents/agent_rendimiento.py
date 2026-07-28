"""Agente 5: revisor de rendimiento y Big O.

Mide (no intuye): duración por etapa del último pipeline (desde el log) y
micro-benchmarks de escalado sobre las rutas críticas de ingesta y cobertura
con datos sintéticos de 1x/2x/4x para estimar el orden de crecimiento.
"""

from __future__ import annotations

import re
import time
from datetime import datetime

import numpy as np
import pandas as pd

from .base import ROOT, BaseAgent, farm_path

LOG = farm_path("logs", "pipeline.log")


def _kardex_sintetico(n: int) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    fechas = pd.date_range("2026-01-01", periods=max(n // 60, 1), freq="D")
    return pd.DataFrame(
        {
            "Material": rng.choice(["10007", "10008", "10009"], n),
            "Descripción material": "ALIMENTO",
            "Centro": "1217",
            "Almacén": "1100",
            "Lote": "L1",
            "Documento material": (5_000_000_000 + np.arange(n)).astype(str),
            "Posición doc.mat.": "1",
            "Ejerc.documento mat.": "2026",
            "Ctd.en UM entrada": -rng.uniform(100, 500, n).round(2),
            "Un.medida de entrada": "KG",
            "Ctd.en UMP": -rng.uniform(100, 500, n).round(2),
            "Unidad medida paral.": "KG",
            "Clase de movimiento": "261",
            "Texto clase de mov.": "Salida",
            "Fecha contabiliz.": rng.choice(fechas.strftime("%d.%m.%Y"), n),
            "Referencia": "",
            "Nombre del usuario": "BENCH",
            "Orden": "12000000001",
            "Centro receptor": "",
            "Clase de trans./eve.": "WA",
            "Indicador Debe/Haber": "H",
            "Cantidad": -rng.uniform(100, 500, n).round(2),
            "Texto cab.documento": "",
            "Texto": "",
            "Motivo movimiento": "",
        }
    )


class AgenteRendimiento(BaseAgent):
    nombre = "revisor_rendimiento"
    categoria = "performance"

    # ------------------------------------------------------------------
    def _etapas_del_log(self) -> None:
        if not LOG.exists():
            self.finding("low", "No existe logs/pipeline.log; sin medición de etapas.")
            return
        lineas = LOG.read_text(encoding="utf-8", errors="ignore").splitlines()
        patron = re.compile(
            r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?(\d{1,2}b?/11 .*|Pipeline completado)"
        )
        eventos: list[tuple[datetime, str]] = []
        for linea in lineas:
            m = patron.match(linea)
            if m:
                eventos.append(
                    (datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S"), m.group(2).strip())
                )
        # Última corrida completa: desde el último "1/11"
        inicios = [i for i, (_, e) in enumerate(eventos) if e.startswith("1/11")]
        if not inicios:
            self.finding("low", "El log no contiene una corrida completa reconocible.")
            return
        corrida = eventos[inicios[-1]:]
        duraciones: dict[str, float] = {}
        for (t0, etapa), (t1, _) in zip(corrida, corrida[1:]):
            duraciones[etapa] = (t1 - t0).total_seconds()
        total = sum(duraciones.values())
        self.metricas["etapas_ultima_corrida_seg"] = {
            k: round(v, 1) for k, v in duraciones.items()
        }
        self.metricas["pipeline_total_seg"] = round(total, 1)
        if total:
            peor = max(duraciones, key=duraciones.get)
            pct = duraciones[peor] / total
            nivel = "medium" if pct > 0.5 else "info"
            self.finding(
                nivel,
                f"Pipeline completo: {total:,.0f}s. Etapa dominante: '{peor}' "
                f"({duraciones[peor]:,.0f}s, {pct:.0%} del total).",
                file="logs/pipeline.log",
                impact="Define el techo del tiempo de respuesta tras cada carga.",
                recommendation=(
                    "Optimizar solo esta etapa si el tiempo total resulta inaceptable "
                    "para la operación; medir antes y después."
                ),
                confidence=0.9,
            )

    # ------------------------------------------------------------------
    def _benchmark_escalado(self) -> None:
        import sqlite3
        import sys
        import tempfile
        import tracemalloc

        sys.path.insert(0, str(ROOT / "src"))
        from granjas_anomalias.db import Warehouse
        from granjas_anomalias.ingestion import calcular_llaves_negocio, normalizar_mb51

        # Escalado ~1x/2x/5x/10x del kardex actual (~46.7k filas).
        resultados = []
        for n in (50_000, 100_000, 250_000, 500_000):
            df = _kardex_sintetico(n)
            tracemalloc.start()
            t0 = time.perf_counter()
            canonico = normalizar_mb51(df)
            t_norm = time.perf_counter() - t0
            _, pico = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            t0 = time.perf_counter()
            calcular_llaves_negocio(canonico)
            t_llaves = time.perf_counter() - t0
            resultados.append(
                {
                    "n": n,
                    "normalizar_s": t_norm,
                    "llaves_s": t_llaves,
                    "pico_memoria_mb": pico / 1024 / 1024,
                }
            )
        self.metricas["benchmark_ingesta"] = [
            {k: round(v, 3) if isinstance(v, float) else v for k, v in r.items()}
            for r in resultados
        ]
        razon_norm = resultados[-1]["normalizar_s"] / max(resultados[0]["normalizar_s"], 1e-9)
        razon_llaves = resultados[-1]["llaves_s"] / max(resultados[0]["llaves_s"], 1e-9)
        self.metricas["razon_tiempo_10x"] = {
            "normalizar": round(razon_norm, 2),
            "llaves": round(razon_llaves, 2),
        }
        for nombre, razon in ("normalizar_mb51", razon_norm), ("calcular_llaves", razon_llaves):
            if razon > 20:  # supralineal claro con 10x de datos
                self.finding(
                    "medium",
                    f"{nombre} escala supralinealmente: 10x datos -> {razon:.1f}x tiempo.",
                    file="src/granjas_anomalias/ingestion.py",
                    recommendation="Perfilar la función; puede haber operación O(n^2).",
                    confidence=0.75,
                )
            else:
                self.finding(
                    "info",
                    f"{nombre}: 10x datos -> {razon:.1f}x tiempo (~O(n)). 500k filas: "
                    f"{resultados[-1]['normalizar_s' if 'norm' in nombre else 'llaves_s']:.1f}s; "
                    f"pico memoria normalización 500k: {resultados[-1]['pico_memoria_mb']:.0f} MB.",
                    confidence=0.85,
                )

        # Inserción idempotente en SQLite (INSERT OR IGNORE por llave única).
        with tempfile.TemporaryDirectory() as tmp:
            wh = Warehouse(f"{tmp}/bench.db")
            df = _kardex_sintetico(100_000)
            canonico = normalizar_mb51(df)
            llaves, ocurrencia = calcular_llaves_negocio(canonico)
            canonico.insert(0, "llave_negocio", llaves)
            canonico["ocurrencia"] = ocurrencia
            canonico.insert(1, "carga_id", "bench")
            canonico.insert(2, "fuente", "MB51")
            canonico.insert(3, "hoja", "Data")
            t0 = time.perf_counter()
            wh.insertar_movimientos(canonico)
            t_ins = time.perf_counter() - t0
            t0 = time.perf_counter()
            wh.insertar_movimientos(canonico)  # reingesta: todo duplicado
            t_dup = time.perf_counter() - t0
        self.metricas["sqlite_insert_100k_s"] = round(t_ins, 2)
        self.metricas["sqlite_reingesta_100k_s"] = round(t_dup, 2)
        self.finding(
            "info",
            f"SQLite: insertar 100k movimientos {t_ins:.1f}s; reingesta idempotente del "
            f"mismo lote {t_dup:.1f}s (0 insertados).",
            confidence=0.9,
        )

        # Riesgos conocidos por diseño (hechos de código, no medición):
        self.finding(
            "low",
            "El pipeline reescribe todas las salidas (CSV + dashboard) en cada corrida "
            "aunque solo se agregue un día de datos: costo O(historial), no O(incremento).",
            file="src/granjas_anomalias/pipeline.py",
            impact="Con ~2 años de datos el recálculo completo tarda minutos, no segundos.",
            recommendation=(
                "Aceptable para operación diaria actual; si crece a varios centros, "
                "considerar recomputar solo ciclos activos."
            ),
            confidence=0.9,
        )
        self.finding(
            "low",
            "streamlit_app._ops_status lee todas las alertas de todas las corridas en cada "
            "rerun (db.leer_alertas() sin filtro).",
            file="streamlit_app.py",
            component="_ops_status",
            impact="Crece linealmente con corridas acumuladas; hoy es despreciable.",
            recommendation="Filtrar por última corrida en SQL cuando el historial crezca.",
            confidence=0.85,
        )

    def revisar(self) -> None:
        self._etapas_del_log()
        self._benchmark_escalado()
