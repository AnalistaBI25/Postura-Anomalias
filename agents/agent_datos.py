"""Agente 3: revisor de calidad de datos (kardex crudo + almacén SQLite)."""

from __future__ import annotations

import sqlite3

import pandas as pd

from .base import ROOT, BaseAgent

KARDEX_CACHE = ROOT / "data" / "cache" / "kardex_mb51_chencopo_2024_2026.csv"
WAREHOUSE = ROOT / "data" / "warehouse.db"
NO_CLASIFICADOS = ROOT / "reports" / "tables" / "03_movimientos_no_clasificados.csv"

LLAVES = ["Material", "Centro", "Almacén", "Clase de movimiento", "Fecha contabiliz."]


class AgenteDatos(BaseAgent):
    nombre = "revisor_datos"
    categoria = "calidad_datos"

    def revisar(self) -> None:
        if not KARDEX_CACHE.exists():
            self.finding(
                "high",
                f"No existe el kardex cache {KARDEX_CACHE.name}; no hay datos que validar.",
                recommendation="Ejecutar scripts/run_incremental.py --bootstrap.",
            )
            return

        df = pd.read_csv(KARDEX_CACHE, low_memory=False)
        self.metricas["filas_kardex_cache"] = int(len(df))
        self.metricas["columnas"] = int(len(df.columns))

        columnas = set(df.columns)
        llaves_presentes = [c for c in LLAVES if c in columnas]
        alias = {
            "Material": "material",
            "Centro": "centro",
            "Almacén": "almacen",
            "Clase de movimiento": "clase_movimiento",
            "Fecha contabiliz.": "fecha",
        }
        if len(llaves_presentes) < len(LLAVES):
            # El cache puede venir materializado desde SQLite con nombres canónicos.
            llaves_presentes = [alias[c] for c in LLAVES if alias[c] in columnas]

        nulos = {c: int(df[c].isna().sum()) for c in llaves_presentes}
        self.metricas["nulos_llaves"] = nulos
        con_nulos = {c: n for c, n in nulos.items() if n > 0}
        if con_nulos:
            severidad = "medium" if max(con_nulos.values()) < len(df) * 0.01 else "high"
            self.finding(
                severidad,
                f"Nulos en llaves: {con_nulos} de {len(df):,} filas.",
                file=str(KARDEX_CACHE.relative_to(ROOT)),
                impact="Registros sin llave no se pueden asignar a centro/material/fecha.",
                recommendation="Revisar la exportación SAP; el pipeline ya descarta filas sin fecha.",
            )
        else:
            self.finding("info", f"Sin nulos en llaves ({len(df):,} filas).", confidence=0.95)

        duplicados = int(df.duplicated().sum())
        self.metricas["duplicados_fila_completa"] = duplicados
        if duplicados:
            self.finding(
                "info",
                f"{duplicados} filas 100% idénticas en el kardex (posibles movimientos "
                "legítimos repetidos; la ingesta los conserva vía contador de ocurrencia).",
                confidence=0.7,
            )

        col_fecha = "Fecha contabiliz." if "Fecha contabiliz." in columnas else "fecha"
        fechas = pd.to_datetime(df[col_fecha], errors="coerce", format="mixed")
        invalidas = int(fechas.isna().sum())
        self.metricas["fechas_invalidas"] = invalidas
        if invalidas:
            self.finding(
                "medium",
                f"{invalidas} fechas no interpretables en {col_fecha}.",
                recommendation="El pipeline las descarta; confirmar que no sean sistemáticas.",
            )
        futuras = int((fechas > pd.Timestamp.today()).sum())
        if futuras:
            self.finding(
                "medium",
                f"{futuras} movimientos con fecha futura.",
                impact="Pueden distorsionar cobertura y tendencias.",
            )
        self.metricas["rango_fechas"] = [str(fechas.min()), str(fechas.max())]

        if NO_CLASIFICADOS.exists():
            nc = pd.read_csv(NO_CLASIFICADOS)
            self.metricas["combinaciones_no_clasificadas"] = int(len(nc))
            if len(nc):
                self.finding(
                    "medium",
                    f"{len(nc)} combinaciones SAP sin clasificar (reports/tables/03).",
                    file="reports/tables/03_movimientos_no_clasificados.csv",
                    impact="Movimientos fuera de consumo/producción hasta que negocio los valide.",
                    recommendation="Revisarlas con negocio antes de incorporarlas como regla.",
                    requires_business_validation=True,
                )

        if WAREHOUSE.exists():
            with sqlite3.connect(WAREHOUSE) as conn:
                movs = conn.execute("SELECT COUNT(*) FROM movimientos").fetchone()[0]
                cargas = conn.execute("SELECT COUNT(*) FROM cargas").fetchone()[0]
                rechazadas = conn.execute(
                    "SELECT COUNT(*) FROM cargas WHERE estado = 'RECHAZADO'"
                ).fetchone()[0]
            self.metricas["warehouse"] = {
                "movimientos": int(movs),
                "cargas": int(cargas),
                "cargas_rechazadas": int(rechazadas),
            }
            self.finding(
                "info",
                f"Almacén SQLite: {movs:,} movimientos, {cargas} cargas "
                f"({rechazadas} rechazadas).",
                confidence=0.95,
            )
        else:
            self.finding(
                "medium",
                "No existe data/warehouse.db: la ingesta incremental no se ha inicializado.",
                recommendation="python scripts/run_incremental.py --bootstrap",
            )
