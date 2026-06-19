from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import ProjectConfig
from .utils import save_csv


def build_quality_outputs(
    kardex: pd.DataFrame,
    organization: pd.DataFrame,
    standard: pd.DataFrame,
    config: ProjectConfig,
) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    tables = config.resolve("tables_dir")

    quality_rows = []
    for source, df in [
        ("kardex_mb51", kardex),
        ("organizacion", organization),
        ("politica", standard),
    ]:
        quality_rows.append(
            {
                "fuente": source,
                "registros": len(df),
                "columnas": len(df.columns),
                "duplicados_fila_completa": int(df.duplicated().sum()),
                "porcentaje_nulos_promedio": round(float(df.isna().mean().mean() * 100), 3),
            }
        )
    quality = pd.DataFrame(quality_rows)
    outputs["calidad_fuentes"] = save_csv(quality, tables / "01_calidad_fuentes.csv")

    catalog = (
        kardex.groupby(
            [
                "bloque_material",
                "material",
                "descripcion_material",
                "almacen",
                "clase_movimiento",
                "clase_transaccion_evento",
                "rol_movimiento",
            ],
            dropna=False,
        )
        .agg(
            registros=("material", "size"),
            fecha_min=("fecha", "min"),
            fecha_max=("fecha", "max"),
            cantidad_abs_total=("cantidad_abs", "sum"),
        )
        .reset_index()
        .sort_values("registros", ascending=False)
    )
    outputs["catalogo_movimientos"] = save_csv(
        catalog, tables / "02_catalogo_movimientos_sap.csv"
    )

    unknown = catalog.loc[catalog["rol_movimiento"].eq("NO_CLASIFICADO")].copy()
    outputs["movimientos_no_clasificados"] = save_csv(
        unknown, tables / "03_movimientos_no_clasificados.csv"
    )

    key_nulls = pd.DataFrame(
        [
            {
                "campo": field,
                "nulos": int(kardex[field].isna().sum()),
                "porcentaje": round(float(kardex[field].isna().mean() * 100), 3),
            }
            for field in ["fecha", "centro", "almacen", "material", "lote", "orden"]
            if field in kardex.columns
        ]
    )
    outputs["nulos_llaves"] = save_csv(key_nulls, tables / "04_nulos_llaves_sap.csv")

    report = f"""# Calidad de datos

- Registros MB51 procesados: **{len(kardex):,}**
- Periodo: **{kardex['fecha'].min().date()} a {kardex['fecha'].max().date()}**
- Combinaciones SAP catalogadas: **{len(catalog):,}**
- Combinaciones no clasificadas: **{len(unknown):,}**
- Semanas de política: **{standard['semana_edad'].min()} a {standard['semana_edad'].max()}**

## Criterio de aceptación

Las combinaciones no clasificadas no se eliminan. Se exportan para validación con negocio y solo se convierten en una nueva regla cuando existe evidencia operativa.

## Archivos de auditoría

- `reports/tables/01_calidad_fuentes.csv`
- `reports/tables/02_catalogo_movimientos_sap.csv`
- `reports/tables/03_movimientos_no_clasificados.csv`
- `reports/tables/04_nulos_llaves_sap.csv`
"""
    report_path = config.root / "reports" / "CALIDAD_DATOS.md"
    report_path.write_text(report, encoding="utf-8")
    outputs["reporte_calidad"] = report_path
    return outputs


def build_labeling_template(anomalies: pd.DataFrame, config: ProjectConfig) -> Path:
    columns = [
        "fecha",
        "cycle_id",
        "centro",
        "caseta",
        "lote",
        "orden_operativa",
        "edad_semana",
        "fase_alimento_principal",
        "consumo_real_kg_dia",
        "consumo_estandar_kg_dia",
        "score_anomalia",
        "severidad",
        "motivo_anomalia",
    ]
    template = anomalies.loc[:, [c for c in columns if c in anomalies.columns]].head(300).copy()
    template["etiqueta_validada"] = "PENDIENTE"
    template["tipo_causa"] = ""
    template["comentario_operacion"] = ""
    template["usuario_validador"] = ""
    template["fecha_validacion"] = ""
    return save_csv(template, config.resolve("tables_dir") / "05_plantilla_validacion_anomalias.csv")
