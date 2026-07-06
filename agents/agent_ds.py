"""Agente 4: revisor de Data Science.

Recalcula de forma independiente los agregados clave desde el kardex crudo
(sin usar classify/daily/stock) y los compara contra las salidas del pipeline
y el payload del dashboard. Un desfase mayor a la tolerancia es un hallazgo.
"""

from __future__ import annotations

import json
import sys

import pandas as pd

from .base import ROOT, BaseAgent

sys.path.insert(0, str(ROOT / "src"))

from granjas_anomalias.config import load_config  # noqa: E402
from granjas_anomalias.utils import parse_dates, parse_sap_number  # noqa: E402

CACHE = ROOT / "data" / "cache" / "kardex_mb51_chencopo_2024_2026.csv"
PROCESSED = ROOT / "data" / "processed"
PAYLOAD = ROOT / "reports" / "dashboard_payload_debug.json"

TOL_REL = 0.01  # 1% de tolerancia relativa


def _pct(a: float, b: float) -> float:
    return abs(a - b) / max(abs(b), 1e-9)


class AgenteDS(BaseAgent):
    nombre = "revisor_ds"
    categoria = "data_science"

    # ------------------------------------------------------------------
    def _comparar(
        self,
        nombre: str,
        independiente: float,
        pipeline: float,
        contexto: str,
        severidad_desvio: str = "high",
    ) -> None:
        desvio = _pct(independiente, pipeline)
        self.metricas[nombre] = {
            "independiente": round(independiente, 2),
            "pipeline": round(pipeline, 2),
            "desvio_relativo": round(desvio, 6),
        }
        if desvio > TOL_REL:
            self.finding(
                severidad_desvio,
                f"{nombre}: recálculo independiente {independiente:,.2f} vs pipeline "
                f"{pipeline:,.2f} (desvío {desvio:.2%}). {contexto}",
                impact="El KPI mostrado podría no corresponder al kardex fuente.",
                recommendation="Revisar reglas de clasificación/asignación involucradas.",
                confidence=0.85,
            )
        else:
            self.finding(
                "info",
                f"{nombre} validado: {independiente:,.2f} vs {pipeline:,.2f} "
                f"(desvío {desvio:.4%}). {contexto}",
                confidence=0.9,
            )

    # ------------------------------------------------------------------
    def revisar(self) -> None:
        if not CACHE.exists():
            self.finding("high", "No existe el kardex cache; sin base para validar.")
            return
        config = load_config(ROOT / "config" / "project.yml")
        sap = config.sap

        raw = pd.read_csv(CACHE, low_memory=False)
        columnas = {c: c for c in raw.columns}
        # Soporta cache original SAP o cache canónico materializado desde SQLite.
        if "Material" in columnas:
            col = {
                "material": "Material",
                "centro": "Centro",
                "almacen": "Almacén",
                "mov": "Clase de movimiento",
                "evento": "Clase de trans./eve.",
                "fecha": "Fecha contabiliz.",
                "qty_ump": "Ctd.en UMP",
                "um_ump": "Unidad medida paral.",
                "qty_ent": "Ctd.en UM entrada",
            }
        else:
            col = {
                "material": "material",
                "centro": "centro",
                "almacen": "almacen",
                "mov": "clase_movimiento",
                "evento": "clase_transaccion_evento",
                "fecha": "fecha",
                "qty_ump": "cantidad_ump",
                "um_ump": "unidad_medida_paralela",
                "qty_ent": "cantidad_um_entrada",
            }

        df = pd.DataFrame(
            {
                "material": raw[col["material"]].astype(str).str.strip(),
                "centro": raw[col["centro"]].astype(str).str.strip(),
                "almacen": raw[col["almacen"]].astype(str).str.strip(),
                "mov": raw[col["mov"]].astype(str).str.strip(),
                "evento": raw[col["evento"]].astype(str).str.strip().str.upper(),
                "fecha": parse_dates(raw[col["fecha"]]),
                "qty_ump": raw[col["qty_ump"]].map(parse_sap_number),
                "um_ump": raw[col["um_ump"]].astype(str).str.upper().str.strip(),
                "qty_ent": raw[col["qty_ent"]].map(parse_sap_number),
            }
        )
        df["kg"] = df["qty_ump"].where(df["um_ump"].eq("KG"), df["qty_ent"])

        inicio = pd.Timestamp(config.project["analysis_start"]) - pd.Timedelta(days=30)
        df = df.loc[df["fecha"].notna() & df["fecha"].ge(inicio)]

        # 1) Volumen y dimensiones vs kardex normalizado (01)
        k01 = pd.read_csv(
            ROOT / "data" / "interim" / "01_kardex_normalizado_clasificado.csv",
            low_memory=False,
        )
        self._comparar(
            "filas_ventana_analisis",
            float(len(df)),
            float(len(k01)),
            "Filas dentro de la ventana de análisis.",
        )
        self.metricas["dimensiones"] = {
            "centros": int(df["centro"].nunique()),
            "almacenes": int(df["almacen"].nunique()),
            "materiales": int(df["material"].nunique()),
            "fecha_min": str(df["fecha"].min().date()),
            "fecha_max": str(df["fecha"].max().date()),
        }

        feed = set(map(str, sap["feed_materials"].keys()))
        huevos = set(map(str, sap.get("normal_egg_materials", [])))
        subprod = set(map(str, sap.get("subproduct_materials", [])))
        aves = str(sap["bird_material"])

        # 2) Consumo neto de alimento (261/262 WA) vs stock global (09).
        #    La serie de stock inicia en el ancla MB5B, no en la preventana de
        #    análisis: se alinean las ventanas antes de comparar.
        s09 = pd.read_csv(PROCESSED / "09_stock_alimento_diario_global.csv")
        inicio_stock = pd.Timestamp(s09["fecha"].min())
        en_stock = df["fecha"].ge(inicio_stock)
        es_feed = df["material"].isin(feed)
        consumo_indep = -float(
            df.loc[
                en_stock & es_feed & df["mov"].isin(["261", "262"]) & df["evento"].eq("WA"),
                "kg",
            ].sum()
        )
        self._comparar(
            "consumo_neto_alimento_kg",
            consumo_indep,
            float(s09["consumo_neto_calculado_kg"].sum()),
            f"261 menos 262 (WA) de alimento desde el ancla MB5B ({inicio_stock.date()}).",
        )

        # 3) Entradas netas de alimento (101/102 WE) vs stock global (09)
        entradas_indep = float(
            df.loc[
                en_stock & es_feed & df["mov"].isin(["101", "102"]) & df["evento"].eq("WE"),
                "kg",
            ].sum()
        )
        self._comparar(
            "entradas_netas_alimento_kg",
            entradas_indep,
            float(s09["entradas_netas_kg"].sum()),
            f"101 menos 102 (WE) de alimento desde el ancla MB5B ({inicio_stock.date()}).",
        )

        # 4) Producción vs línea diaria (06): la línea asigna por orden de ciclo,
        #    por lo que la diferencia legítima es producción fuera de ciclos.
        d06 = pd.read_csv(PROCESSED / "06_linea_diaria_ciclos.csv", low_memory=False)
        prod_indep = float(
            df.loc[df["material"].isin(huevos) & df["mov"].isin(["101", "102"]) & df["evento"].eq("WF"), "kg"].sum()
        ) + float(
            df.loc[df["material"].isin(subprod) & df["mov"].isin(["531", "532"]) & df["evento"].eq("WA"), "kg"].sum()
        )
        prod_pipeline = float(d06["produccion_real_kg_dia"].sum())
        cobertura_prod = prod_pipeline / max(prod_indep, 1e-9)
        self.metricas["produccion"] = {
            "kardex_kg": round(prod_indep, 1),
            "linea_diaria_kg": round(prod_pipeline, 1),
            "fraccion_asignada_a_ciclos": round(cobertura_prod, 4),
        }
        if cobertura_prod > 1.001:
            self.finding(
                "high",
                f"La línea diaria registra más producción ({prod_pipeline:,.0f} kg) que el "
                f"kardex ({prod_indep:,.0f} kg): posible doble conteo.",
                confidence=0.85,
            )
        elif cobertura_prod < 0.95:
            self.finding(
                "medium",
                f"{(1 - cobertura_prod):.1%} de la producción del kardex no está asignada a "
                "ciclos detectados (fuera de ventana u órdenes no vigentes).",
                impact="KPIs por ciclo no incluyen esa producción; el total global sí existe en SAP.",
                recommendation="Confirmar si corresponde a ciclos previos al inicio del análisis.",
                requires_business_validation=True,
                confidence=0.7,
            )
        else:
            self.finding(
                "info",
                f"Producción asignada a ciclos: {cobertura_prod:.2%} del kardex "
                f"({prod_pipeline:,.0f} de {prod_indep:,.0f} kg).",
                confidence=0.9,
            )

        # 5) Mortalidad (aves 261/262 WR, unidades) vs línea diaria. La línea
        #    solo asigna mortalidad dentro de ciclos detectados: se compara en
        #    la ventana cubierta por la línea y el resto se reporta como
        #    mortalidad fuera de ciclos (informativo).
        es_ave = df["material"].eq(aves)
        mort_rows = df.loc[es_ave & df["mov"].isin(["261", "262"]) & df["evento"].eq("WR")]
        ventana_ini = pd.Timestamp(d06["fecha"].min())
        ventana_fin = pd.Timestamp(d06["fecha"].max())
        mort_en_ventana = -float(
            mort_rows.loc[mort_rows["fecha"].between(ventana_ini, ventana_fin), "qty_ent"].sum()
        )
        mort_total = -float(mort_rows["qty_ent"].sum())
        mort_pipeline = float(d06["mortalidad_dia"].sum())
        self._comparar(
            "mortalidad_aves_en_ventana_ciclos",
            mort_en_ventana,
            mort_pipeline,
            f"261 menos 262 (WR) de aves entre {ventana_ini.date()} y {ventana_fin.date()}.",
            severidad_desvio="medium",
        )
        if mort_total > mort_en_ventana:
            self.finding(
                "info",
                f"{mort_total - mort_en_ventana:,.0f} aves de mortalidad quedan fuera de la "
                "ventana de ciclos detectados (histórico previo al análisis).",
                confidence=0.8,
            )

        # 6) Consistencia diaria (06) vs semanal (07)
        w07 = pd.read_csv(PROCESSED / "07_resumen_semanal_ciclos.csv")
        self._comparar(
            "consumo_diario_vs_semanal_kg",
            float(d06["consumo_real_kg_dia"].sum()),
            float(w07["consumo_real_kg"].sum()),
            "La agregación semanal debe conservar el total diario.",
        )
        self._comparar(
            "produccion_diaria_vs_semanal_kg",
            float(d06["produccion_real_kg_dia"].sum()),
            float(w07["produccion_real_kg"].sum()),
            "La agregación semanal debe conservar el total diario.",
        )

        # 7) ICA semanal: la definición documentada usa consumo y producción
        #    PRODUCTIVOS (excluye consumo preproductivo en la semana de arranque).
        ev = w07.loc[
            w07.get("es_ica_evaluable", pd.Series(False, index=w07.index)).fillna(False)
            & w07["produccion_productiva_kg"].gt(0)
        ].copy()
        if not ev.empty:
            recalculado = ev["consumo_productivo_kg"] / ev["produccion_productiva_kg"]
            desvio_max = float((recalculado - ev["ica_real"]).abs().max())
            self.metricas["ica_semanal_desvio_max"] = round(desvio_max, 6)
            if desvio_max > 0.01:
                self.finding(
                    "high",
                    f"ICA semanal no reproduce consumo_productivo/produccion_productiva "
                    f"(desvío máx {desvio_max:.4f}).",
                    recommendation="Revisar el cálculo de ica_real en daily.py.",
                    confidence=0.85,
                )
            else:
                self.finding(
                    "info",
                    f"ICA semanal reproducible en {len(ev)} semanas evaluables como "
                    f"consumo_productivo/produccion_productiva (desvío máx {desvio_max:.6f}).",
                    confidence=0.9,
                )

        # 8) Payload del dashboard vs stock global (consistencia frontend)
        if PAYLOAD.exists():
            payload = json.loads(PAYLOAD.read_text(encoding="utf-8"))
            daily = payload.get("shared_store", {}).get("daily", {})
            if isinstance(daily, list) and daily:
                # Lista de registros -> localizar la columna de stock.
                daily = pd.DataFrame(daily).to_dict("list")
            series_stock = None
            if isinstance(daily, dict):
                candidatas = [c for c in daily if "stock" in str(c).lower()]
                for clave in ("stock_global_kg", "stock_kg", "stock", *candidatas):
                    if clave in daily:
                        series_stock = daily[clave]
                        break
            if series_stock is not None:
                ultimo_payload = float(pd.Series(series_stock).dropna().iloc[-1])
                ultimo_pipeline = float(
                    s09.sort_values("fecha")["stock_global_kg"].iloc[-1]
                )
                self._comparar(
                    "stock_final_dashboard_kg",
                    ultimo_payload,
                    ultimo_pipeline,
                    "Última fecha del stock global en el payload vs CSV 09.",
                )
            else:
                self.finding(
                    "low",
                    "No se localizó la serie de stock en shared_store.daily; validación de "
                    f"payload parcial (claves: {list(daily)[:12] if isinstance(daily, dict) else type(daily)}).",
                    confidence=0.6,
                )
        else:
            self.finding(
                "low",
                "No existe reports/dashboard_payload_debug.json; sin validación de payload.",
            )
