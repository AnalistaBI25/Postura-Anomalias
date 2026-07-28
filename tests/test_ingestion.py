from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from granjas_anomalias.config import ProjectConfig
from granjas_anomalias.db import Warehouse
from granjas_anomalias.ingestion import (
    analizar_granularidad,
    ingerir_archivo,
    materializar_kardex_cache,
    validar_archivo,
)
from granjas_anomalias.normalize import normalize_kardex


# ============================================================
# Fixtures
# ============================================================
@pytest.fixture()
def config(tmp_path: Path) -> ProjectConfig:
    return ProjectConfig(
        root=tmp_path,
        raw={
            "project": {
                "farm_id": "test-farm",
                "center_id": "1217",
                "farm_name": "GRANJA TEST",
                "analysis_start": "2026-01-01",
                "analysis_end": None,
            },
            "paths": {"kardex_cache_csv": "data/cache/kardex.csv"},
            "sap": {"bird_material": "20019", "feed_warehouse": "1100"},
            "ingestion": {"db_path": "data/warehouse.db", "max_file_mb": 50},
            "outputs": {},
        },
    )


@pytest.fixture()
def db(tmp_path: Path) -> Warehouse:
    return Warehouse(tmp_path / "data" / "warehouse.db")


def crear_mb51(
    path: Path,
    fechas: list[str],
    material: str = "10007",
    cantidad: float = -320.0,
    documento_base: int = 5000000000,
    filas_extra: int = 0,
) -> Path:
    filas = []
    for i, fecha in enumerate(fechas):
        filas.append(
            {
                "Material": material,
                "Descripción material": "ALIMENTO FASE 1",
                "Centro": "1217",
                "Almacén": "1100",
                "Lote": "L1",
                "Documento material": str(documento_base + i),
                "Posición doc.mat.": "1",
                "Ejerc.documento mat.": "2026",
                "Ctd.en UM entrada": cantidad,
                "Un.medida de entrada": "KG",
                "Ctd.en UMP": cantidad,
                "Unidad medida paral.": "KG",
                "Clase de movimiento": "261",
                "Texto clase de mov.": "Salida",
                "Fecha contabiliz.": fecha,
                "Referencia": "",
                "Nombre del usuario": "TEST",
                "Orden": "12000000001",
                "Centro receptor": "",
                "Clase de trans./eve.": "WA",
                "Indicador Debe/Haber": "H",
                "Cantidad": cantidad,
                "Texto cab.documento": "",
                "Texto": "",
                "Motivo movimiento": "",
            }
        )
    df = pd.DataFrame(filas)
    if filas_extra:
        df = pd.concat([df, df.head(filas_extra)], ignore_index=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, sheet_name="Data", index=False)
    return path


# ============================================================
# Granularidad
# ============================================================
def test_granularidad_diaria():
    fechas = pd.Series(pd.date_range("2026-05-01", "2026-05-10", freq="D"))
    info = analizar_granularidad(fechas)
    assert info["granularidad"] == "diaria"
    assert info["fecha_min"] == "2026-05-01"
    assert info["fecha_max"] == "2026-05-10"
    assert info["dias_faltantes"] == 0
    assert info["n_dias"] == 10


def test_granularidad_semanal_y_faltantes():
    fechas = pd.Series(pd.date_range("2026-01-04", periods=6, freq="7D"))
    info = analizar_granularidad(fechas)
    assert info["granularidad"] == "semanal"
    assert info["dias_faltantes"] > 0


def test_granularidad_sin_fechas():
    info = analizar_granularidad(pd.Series([None, None]))
    assert info["granularidad"] == "sin_fechas"


def test_granularidad_fechas_futuras():
    futuro = pd.Timestamp.today().normalize() + pd.Timedelta(days=30)
    fechas = pd.Series([futuro, futuro + pd.Timedelta(days=1)])
    info = analizar_granularidad(fechas)
    assert info["fechas_futuras"] == 2


# ============================================================
# Validación
# ============================================================
def test_validacion_mb51_ok(tmp_path: Path, config: ProjectConfig, db: Warehouse):
    archivo = crear_mb51(tmp_path / "in" / "mb51.xlsx", ["01.05.2026", "02.05.2026"])
    informe = validar_archivo(archivo, config, db)
    assert informe.valido
    assert informe.fuente == "MB51"
    assert informe.hoja == "Data"
    assert informe.n_registros == 2
    assert informe.centros == ["1217"]
    assert informe.almacenes == ["1100"]


def test_validacion_rechaza_columnas_faltantes(tmp_path: Path, config, db):
    df = pd.DataFrame({"Material": ["10007"], "Centro": ["1217"]})
    archivo = tmp_path / "malo.xlsx"
    df.to_excel(archivo, sheet_name="Data", index=False)
    informe = validar_archivo(archivo, config, db)
    assert not informe.valido
    assert any("No se reconoció la fuente" in e for e in informe.errores)


def test_validacion_rechaza_extension(tmp_path: Path, config, db):
    archivo = tmp_path / "algo.txt"
    archivo.write_text("hola", encoding="utf-8")
    informe = validar_archivo(archivo, config, db)
    assert not informe.valido


def test_validacion_rechaza_vacio(tmp_path: Path, config, db):
    archivo = tmp_path / "vacio.xlsx"
    pd.DataFrame(
        columns=[
            "Material",
            "Centro",
            "Almacén",
            "Clase de movimiento",
            "Fecha contabiliz.",
        ]
    ).to_excel(archivo, sheet_name="Data", index=False)
    informe = validar_archivo(archivo, config, db)
    assert not informe.valido
    assert any("no contiene registros" in e for e in informe.errores)


def test_validacion_rechaza_reporte_mensual(tmp_path: Path, config, db):
    archivo = tmp_path / "reporte_mensual.xlsx"
    with pd.ExcelWriter(archivo) as writer:
        pd.DataFrame({"x": [1]}).to_excel(writer, sheet_name="Mortalidad", index=False)
        for dia in range(1, 26):
            pd.DataFrame({"x": [dia]}).to_excel(writer, sheet_name=str(dia), index=False)
    informe = validar_archivo(archivo, config, db)
    assert not informe.valido
    assert informe.fuente == "REPORTE_MENSUAL_NO_SOPORTADO"


# ============================================================
# Ingesta idempotente y traslapes
# ============================================================
def test_ingesta_idempotente(tmp_path: Path, config, db):
    archivo = crear_mb51(tmp_path / "in" / "mb51.xlsx", ["01.05.2026", "02.05.2026"])
    primera = ingerir_archivo(archivo, config, db)
    assert primera.estado == "PROCESADO"
    assert primera.insertados == 2

    segunda = ingerir_archivo(archivo, config, db)
    assert segunda.estado == "SIN_REGISTROS_NUEVOS"
    assert segunda.insertados == 0
    assert segunda.omitidos_duplicados == 2
    assert segunda.informe.duplicado_de == primera.carga_id


def test_traslape_inserta_solo_nuevos(tmp_path: Path, config, db):
    fechas_a = [f"{d:02d}.05.2026" for d in range(1, 8)]
    archivo_a = crear_mb51(tmp_path / "a.xlsx", fechas_a)
    ingerir_archivo(archivo_a, config, db)

    # El archivo B repite los días 5-7 (mismos documentos) y agrega 8-10.
    fechas_b = [f"{d:02d}.05.2026" for d in range(5, 11)]
    archivo_b = crear_mb51(tmp_path / "b.xlsx", fechas_b, documento_base=5000000004)
    resumen = ingerir_archivo(archivo_b, config, db)
    assert resumen.insertados == 3
    assert resumen.omitidos_duplicados == 3
    assert "traslape" in (resumen.informe.traslape or "").lower()


def test_duplicados_legitimos_dentro_de_archivo(tmp_path: Path, config, db):
    # Dos filas idénticas en el mismo archivo son movimientos legítimos.
    archivo = crear_mb51(tmp_path / "dup.xlsx", ["01.05.2026"], filas_extra=1)
    resumen = ingerir_archivo(archivo, config, db)
    assert resumen.insertados == 2


def test_rechazo_queda_registrado(tmp_path: Path, config, db):
    archivo = tmp_path / "malo.xlsx"
    pd.DataFrame({"Material": ["10007"]}).to_excel(archivo, sheet_name="Data", index=False)
    resumen = ingerir_archivo(archivo, config, db)
    assert resumen.estado == "RECHAZADO"
    cargas = db.listar_cargas()
    assert (cargas["estado"] == "RECHAZADO").any()
    assert cargas.loc[cargas["estado"] == "RECHAZADO", "motivo_rechazo"].iloc[0]


def test_materializar_cache_compatible_con_normalize(tmp_path: Path, config, db):
    archivo = crear_mb51(tmp_path / "in" / "mb51.xlsx", ["01.05.2026", "02.05.2026"])
    ingerir_archivo(archivo, config, db)
    cache = materializar_kardex_cache(db, config)
    assert cache.exists()

    crudo = pd.read_csv(cache, low_memory=False)
    normalizado = normalize_kardex(crudo, config)
    assert len(normalizado) == 2
    assert normalizado["cantidad_kg"].tolist() == [-320.0, -320.0]
    assert str(normalizado["fecha"].dt.date.min()) == "2026-05-01"
