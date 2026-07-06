"""Ingesta incremental e idempotente de exportaciones SAP.

El formato de carga oficial es el kardex MB51 exportado directamente desde
SAP (misma estructura que ``kardex_mb51_*.xlsx``, hoja ``Data``). Los libros
de trabajo mensuales por granja (hojas 1..31, Mortalidad, Prod. huevo) no son
exportaciones directas y se rechazan con motivo explícito.

Alcance actual: granjas con un único almacén de alimento (pueden tener varias
casetas). Ver docs/preguntas_pendientes.md.
"""

from __future__ import annotations

import hashlib
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import ProjectConfig
from .db import Warehouse
from .utils import clean_key, normalize_text, parse_dates, parse_sap_number

VERSION_INGESTA = "1.0.0"

EXTENSIONES_VALIDAS = {".xlsx", ".xls", ".csv"}

# Columnas mínimas (normalizadas) para reconocer un MB51 directo de SAP.
_MB51_MINIMAS = {
    "material",
    "centro",
    "almacen",
    "clase_de_movimiento",
    "fecha_contabiliz",
}

# Mapa de nombres de origen normalizados -> nombre canónico del almacén lógico.
ALIAS_CANONICOS = {
    "material": "material",
    "descripcion_material": "descripcion_material",
    "centro": "centro",
    "almacen": "almacen",
    "lote": "lote",
    "documento_material": "documento_material",
    "posicion_doc_mat": "posicion_documento",
    "ejerc_documento_mat": "ejercicio_documento",
    "ctd_en_um_entrada": "cantidad_um_entrada",
    "un_medida_de_entrada": "unidad_medida_entrada",
    "ctd_en_ump": "cantidad_ump",
    "unidad_medida_paral": "unidad_medida_paralela",
    "clase_de_movimiento": "clase_movimiento",
    "texto_clase_de_mov": "texto_clase_movimiento",
    "fecha_contabiliz": "fecha",
    "referencia": "referencia",
    "nombre_del_usuario": "usuario",
    "orden": "orden",
    "centro_receptor": "centro_receptor",
    "clase_de_trans_eve": "clase_transaccion_evento",
    "indicador_debe_haber": "indicador_debe_haber",
    "cantidad": "cantidad",
    "texto_cab_documento": "texto_cabecera",
    "texto": "texto_posicion",
    "motivo_movimiento": "motivo_movimiento",
}

# Columnas del almacén lógico de movimientos (mismo orden que db.movimientos,
# sin llave_negocio/carga_id/fuente/hoja/fila_original/ocurrencia/creado_en).
COLUMNAS_MOVIMIENTO = [
    "centro",
    "almacen",
    "material",
    "descripcion_material",
    "lote",
    "documento_material",
    "posicion_documento",
    "ejercicio_documento",
    "clase_movimiento",
    "texto_clase_movimiento",
    "clase_transaccion_evento",
    "indicador_debe_haber",
    "fecha",
    "cantidad_um_entrada",
    "unidad_medida_entrada",
    "cantidad_ump",
    "unidad_medida_paralela",
    "cantidad",
    "orden",
    "referencia",
    "centro_receptor",
    "usuario",
    "texto_cabecera",
    "texto_posicion",
    "motivo_movimiento",
]

_CAMPOS_LLAVE = [
    "centro",
    "almacen",
    "material",
    "fecha",
    "clase_movimiento",
    "clase_transaccion_evento",
    "indicador_debe_haber",
    "documento_material",
    "posicion_documento",
    "ejercicio_documento",
    "orden",
    "lote",
    "cantidad_um_entrada",
    "cantidad",
]


@dataclass
class InformeValidacion:
    archivo: str
    hash_sha256: str = ""
    tamano_bytes: int = 0
    extension: str = ""
    fuente: str = "DESCONOCIDA"
    hoja: str = ""
    hojas: list[str] = field(default_factory=list)
    valido: bool = False
    errores: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    n_registros: int = 0
    fecha_min: str = ""
    fecha_max: str = ""
    granularidad: dict = field(default_factory=dict)
    centros: list[str] = field(default_factory=list)
    almacenes: list[str] = field(default_factory=list)
    materiales: list[str] = field(default_factory=list)
    duplicado_de: str | None = None
    traslape: str = ""

    def resumen(self) -> dict:
        return {
            "archivo": self.archivo,
            "fuente": self.fuente,
            "hoja": self.hoja,
            "valido": self.valido,
            "n_registros": self.n_registros,
            "fecha_min": self.fecha_min,
            "fecha_max": self.fecha_max,
            "granularidad": self.granularidad.get("granularidad", ""),
            "centros": ", ".join(self.centros),
            "almacenes": ", ".join(self.almacenes[:15]),
            "n_materiales": len(self.materiales),
            "duplicado_de": self.duplicado_de or "",
            "traslape": self.traslape,
            "errores": "; ".join(self.errores),
            "advertencias": "; ".join(self.advertencias),
        }


@dataclass
class ResumenIngesta:
    carga_id: str
    estado: str
    insertados: int = 0
    omitidos_duplicados: int = 0
    informe: InformeValidacion | None = None
    mensaje: str = ""


# ----------------------------------------------------------------------
# Utilidades básicas
# ----------------------------------------------------------------------
def calcular_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        for bloque in iter(lambda: fh.read(1 << 20), b""):
            sha.update(bloque)
    return sha.hexdigest()


def analizar_granularidad(fechas: pd.Series) -> dict:
    """Deriva granularidad y cobertura temporal real desde los datos."""
    fechas = pd.to_datetime(fechas, errors="coerce").dropna().dt.normalize()
    if fechas.empty:
        return {"granularidad": "sin_fechas", "n_dias": 0}
    unicas = fechas.drop_duplicates().sort_values()
    fecha_min, fecha_max = unicas.iloc[0], unicas.iloc[-1]
    calendario = pd.date_range(fecha_min, fecha_max, freq="D")
    faltantes = calendario.difference(pd.DatetimeIndex(unicas))
    hoy = pd.Timestamp.today().normalize()

    if len(unicas) == 1:
        granularidad = "diaria"
    else:
        brecha_mediana = unicas.diff().dropna().dt.days.median()
        if brecha_mediana <= 1.5:
            granularidad = "diaria"
        elif 5 <= brecha_mediana <= 9:
            granularidad = "semanal"
        elif 25 <= brecha_mediana <= 35:
            granularidad = "mensual"
        else:
            granularidad = "irregular"

    semanas = fechas.dt.to_period("W-SUN").astype(str).unique()
    meses = fechas.dt.to_period("M").astype(str).unique()
    return {
        "granularidad": granularidad,
        "fecha_min": str(fecha_min.date()),
        "fecha_max": str(fecha_max.date()),
        "n_dias": int(unicas.size),
        "n_dias_calendario": int(calendario.size),
        "dias_faltantes": int(faltantes.size),
        "semanas_incluidas": int(len(semanas)),
        "meses_incluidos": sorted(meses.tolist()),
        "anios_incluidos": sorted(fechas.dt.year.unique().tolist()),
        "fechas_futuras": int((fechas > hoy).sum()),
        "periodo_parcial_inicio": str(fecha_min.date()) if fecha_min.weekday() != 0 else "",
        "periodo_parcial_fin": str(fecha_max.date()) if fecha_max < hoy else "",
    }


def _normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    renombres = {}
    for columna in df.columns:
        clave = normalize_text(columna)
        renombres[columna] = ALIAS_CANONICOS.get(clave, clave)
    return df.rename(columns=renombres)


def _detectar_fuente_hoja(columnas_normalizadas: set[str]) -> str:
    if _MB51_MINIMAS.issubset(columnas_normalizadas):
        return "MB51"
    if {"semana_edad", "consumo_de_alimento_ave_dia"} & columnas_normalizadas or (
        "semana_edad" in columnas_normalizadas
    ):
        return "ESTANDAR"
    return "DESCONOCIDA"


def detectar_fuente(path: Path) -> tuple[str, str, list[str]]:
    """Devuelve (fuente, hoja_datos, hojas) inspeccionando el contenido."""
    if path.suffix.lower() == ".csv":
        encabezado = pd.read_csv(path, nrows=0)
        columnas = {normalize_text(c) for c in encabezado.columns}
        return _detectar_fuente_hoja(columnas), "", []

    xl = pd.ExcelFile(path)
    hojas = list(xl.sheet_names)

    numericas = [h for h in hojas if str(h).strip().isdigit()]
    if len(numericas) >= 20 and any(h in hojas for h in ("Mortalidad", "Prod. huevo")):
        return "REPORTE_MENSUAL_NO_SOPORTADO", "", hojas

    if "Organizacion" in hojas and "materiales" in hojas:
        return "ORGANIZACION", "Organizacion", hojas

    # Se prefiere la hoja "Data" (convención SAP local); si no, se inspecciona
    # cada hoja hasta reconocer un formato conocido.
    candidatas = (["Data"] if "Data" in hojas else []) + [h for h in hojas if h != "Data"]
    for hoja in candidatas:
        try:
            muestra = xl.parse(hoja, nrows=5)
        except Exception:
            continue
        columnas = {normalize_text(c) for c in muestra.columns}
        fuente = _detectar_fuente_hoja(columnas)
        if fuente == "MB51":
            return "MB51", hoja, hojas
        if fuente == "ESTANDAR" and normalize_text(hoja) in {"estandar_sap", "estandar"}:
            return "ESTANDAR", hoja, hojas

    if "mb5b" in normalize_text(path.name) or "stock_inicial" in normalize_text(path.name):
        return "MB5B", hojas[0] if hojas else "", hojas
    return "DESCONOCIDA", "", hojas


# ----------------------------------------------------------------------
# Normalización canónica de MB51
# ----------------------------------------------------------------------
def normalizar_mb51(df: pd.DataFrame) -> pd.DataFrame:
    """Convierte un MB51 crudo al esquema canónico del almacén lógico."""
    df = _normalizar_columnas(df.copy())
    df["fila_original"] = np.arange(2, len(df) + 2)  # 1 = encabezado en Excel

    for columna in COLUMNAS_MOVIMIENTO:
        if columna not in df.columns:
            df[columna] = pd.NA

    for columna in [
        "centro",
        "almacen",
        "material",
        "lote",
        "documento_material",
        "posicion_documento",
        "ejercicio_documento",
        "orden",
        "centro_receptor",
        "referencia",
    ]:
        df[columna] = df[columna].map(clean_key).astype("string")

    df["clase_movimiento"] = df["clase_movimiento"].map(clean_key).astype("string").str.upper()
    df["clase_transaccion_evento"] = (
        df["clase_transaccion_evento"].astype("string").str.strip().str.upper()
    )
    df["indicador_debe_haber"] = (
        df["indicador_debe_haber"].astype("string").str.strip().str.upper()
    )
    df["fecha"] = parse_dates(df["fecha"]).dt.strftime("%Y-%m-%d")

    for columna in ["cantidad_um_entrada", "cantidad_ump", "cantidad"]:
        df[columna] = df[columna].map(parse_sap_number)

    return df[COLUMNAS_MOVIMIENTO + ["fila_original"]]


def calcular_llaves_negocio(df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Llave estable por registro: campos de negocio + ocurrencia dentro de su grupo.

    La ocurrencia permite conservar movimientos legítimamente idénticos dentro
    de un mismo archivo y, a la vez, deduplicar entre archivos traslapados.
    """
    base = (
        df[_CAMPOS_LLAVE]
        .astype("string")
        .fillna("")
        .agg("|".join, axis=1)
    )
    ocurrencia = base.groupby(base).cumcount() + 1
    llaves = (base + "|" + ocurrencia.astype(str)).map(
        lambda s: hashlib.sha256(s.encode("utf-8")).hexdigest()
    )
    return llaves, ocurrencia


# ----------------------------------------------------------------------
# Validación
# ----------------------------------------------------------------------
def validar_archivo(
    path: str | Path,
    config: ProjectConfig,
    db: Warehouse | None = None,
) -> InformeValidacion:
    path = Path(path)
    informe = InformeValidacion(archivo=path.name)

    if not path.exists():
        informe.errores.append("El archivo no existe.")
        return informe

    informe.tamano_bytes = path.stat().st_size
    informe.extension = path.suffix.lower()
    if informe.extension not in EXTENSIONES_VALIDAS:
        informe.errores.append(
            f"Extensión no soportada: {informe.extension}. Válidas: {sorted(EXTENSIONES_VALIDAS)}"
        )
        return informe

    max_mb = float(config.ingestion.get("max_file_mb", 100))
    if informe.tamano_bytes > max_mb * 1024 * 1024:
        informe.errores.append(f"El archivo excede el máximo de {max_mb:.0f} MB.")
        return informe

    informe.hash_sha256 = calcular_hash(path)
    if db is not None:
        informe.duplicado_de = db.hash_ya_cargado(informe.hash_sha256)
        if informe.duplicado_de:
            informe.advertencias.append(
                f"Archivo idéntico ya cargado (carga {informe.duplicado_de}); "
                "reprocesarlo no duplicará movimientos."
            )

    try:
        fuente, hoja, hojas = detectar_fuente(path)
    except Exception as exc:  # archivo corrupto o ilegible
        informe.errores.append(f"No fue posible leer el archivo: {exc}")
        return informe
    informe.fuente, informe.hoja, informe.hojas = fuente, hoja, hojas

    if fuente == "REPORTE_MENSUAL_NO_SOPORTADO":
        informe.errores.append(
            "Libro de trabajo mensual (hojas 1..31). No es una exportación directa "
            "de SAP: exporta MB51 con la variante documentada en docs/EXTRACCION_DATOS_SAP.md."
        )
        return informe
    if fuente == "DESCONOCIDA":
        informe.errores.append(
            "No se reconoció la fuente. Se esperan columnas MB51 "
            "(Material, Centro, Almacén, Clase de movimiento, Fecha contabiliz., ...)."
        )
        return informe
    if fuente in {"ESTANDAR", "ORGANIZACION", "MB5B"}:
        informe.valido = True
        informe.advertencias.append(
            f"Fuente {fuente}: se registra como maestro de referencia; "
            "sustituye el archivo configurado en config/project.yml para usarlo."
        )
        return informe

    # --- MB51 ---
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, low_memory=False)
    else:
        df = pd.read_excel(path, sheet_name=hoja or 0)

    if df.empty:
        informe.errores.append("El archivo no contiene registros.")
        return informe

    columnas = {normalize_text(c) for c in df.columns}
    faltantes = sorted(_MB51_MINIMAS - columnas)
    if faltantes:
        informe.errores.append(f"Faltan columnas obligatorias MB51: {faltantes}")
        return informe
    opcionales = {"documento_material", "orden", "indicador_debe_haber", "clase_de_trans_eve"}
    for columna in sorted(opcionales - columnas):
        informe.advertencias.append(f"Columna recomendada ausente: {columna}")

    canonico = normalizar_mb51(df)
    informe.n_registros = len(canonico)

    fechas = pd.to_datetime(canonico["fecha"], errors="coerce")
    if fechas.notna().sum() == 0:
        informe.errores.append("Ninguna fecha de contabilización es válida.")
        return informe
    sin_fecha = int(fechas.isna().sum())
    if sin_fecha:
        informe.advertencias.append(f"{sin_fecha} registros sin fecha válida (se omiten).")

    informe.granularidad = analizar_granularidad(fechas)
    informe.fecha_min = informe.granularidad.get("fecha_min", "")
    informe.fecha_max = informe.granularidad.get("fecha_max", "")
    if informe.granularidad.get("fechas_futuras", 0):
        informe.advertencias.append(
            f"{informe.granularidad['fechas_futuras']} registros con fecha futura."
        )

    informe.centros = sorted(canonico["centro"].dropna().unique().tolist())
    informe.almacenes = sorted(canonico["almacen"].dropna().unique().tolist())
    informe.materiales = sorted(canonico["material"].dropna().unique().tolist())

    feed_warehouse = str(config.sap.get("feed_warehouse", ""))
    if feed_warehouse and feed_warehouse not in informe.almacenes:
        informe.advertencias.append(
            f"El almacén de alimento configurado ({feed_warehouse}) no aparece en el archivo."
        )

    if db is not None and informe.centros:
        for centro in informe.centros:
            minimo, maximo = db.rango_existente(centro)
            if minimo and maximo and informe.fecha_min and informe.fecha_max:
                if informe.fecha_min <= maximo and informe.fecha_max >= minimo:
                    informe.traslape = (
                        f"Centro {centro}: traslape con lo cargado ({minimo} a {maximo}); "
                        "solo se insertarán registros nuevos."
                    )

    informe.valido = True
    return informe


# ----------------------------------------------------------------------
# Ingesta
# ----------------------------------------------------------------------
def _copiar_inmutable(path: Path, config: ProjectConfig, carga_id: str) -> Path:
    destino_dir = config.root / config.ingestion.get("raw_archive_dir", "data/raw/cargas")
    destino_dir.mkdir(parents=True, exist_ok=True)
    destino = destino_dir / f"{carga_id}_{path.name}"
    if not destino.exists():
        shutil.copy2(path, destino)
    return destino


def ingerir_archivo(
    path: str | Path,
    config: ProjectConfig,
    db: Warehouse,
    usuario: str = "",
    run_id: str = "",
    solo_mb51: bool = False,
) -> ResumenIngesta:
    """Valida, registra e inserta (idempotente) un archivo SAP."""
    path = Path(path)
    informe = validar_archivo(path, config, db)
    carga_id = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6]
    if solo_mb51 and informe.valido and informe.fuente != "MB51":
        informe.valido = False
        informe.errores.append(
            "Esta carga solo acepta el archivo crudo SAP MB51 principal. "
            "Los maestros y reportes auxiliares deben quedar en config/project.yml."
        )

    registro_base = {
        "id": carga_id,
        "nombre_original": path.name,
        "hash_sha256": informe.hash_sha256,
        "tamano_bytes": informe.tamano_bytes,
        "extension": informe.extension,
        "fuente": informe.fuente,
        "hojas": ", ".join(map(str, informe.hojas)),
        "fecha_min": informe.fecha_min,
        "fecha_max": informe.fecha_max,
        "granularidad": informe.granularidad.get("granularidad", ""),
        "n_registros": informe.n_registros,
        "centros": ", ".join(informe.centros),
        "almacenes": ", ".join(informe.almacenes[:30]),
        "materiales": ", ".join(informe.materiales[:60]),
        "traslape": informe.traslape,
        "usuario": usuario,
        "version_pipeline": VERSION_INGESTA,
        "run_id": run_id,
    }

    if not informe.valido:
        rechazados = config.root / config.ingestion.get("rejected_dir", "data/rejected")
        rechazados.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(path, rechazados / f"{carga_id}_{path.name}")
        except OSError:
            pass
        db.registrar_carga(
            registro_base
            | {"estado": "RECHAZADO", "motivo_rechazo": "; ".join(informe.errores)}
        )
        return ResumenIngesta(
            carga_id=carga_id,
            estado="RECHAZADO",
            informe=informe,
            mensaje="; ".join(informe.errores),
        )

    destino = _copiar_inmutable(path, config, carga_id)
    registro_base["nombre_interno"] = destino.name

    if informe.fuente in {"ESTANDAR", "ORGANIZACION", "MB5B"}:
        db.registrar_carga(registro_base | {"estado": "REGISTRADO_MAESTRO"})
        return ResumenIngesta(
            carga_id=carga_id,
            estado="REGISTRADO_MAESTRO",
            informe=informe,
            mensaje="Maestro registrado; no genera movimientos.",
        )

    # MB51: normalizar e insertar solo lo nuevo.
    if path.suffix.lower() == ".csv":
        crudo = pd.read_csv(path, low_memory=False)
    else:
        crudo = pd.read_excel(path, sheet_name=informe.hoja or 0)
    canonico = normalizar_mb51(crudo)
    canonico = canonico.loc[pd.to_datetime(canonico["fecha"], errors="coerce").notna()].copy()

    llaves, ocurrencia = calcular_llaves_negocio(canonico)
    canonico.insert(0, "llave_negocio", llaves)
    canonico["ocurrencia"] = ocurrencia
    canonico.insert(1, "carga_id", carga_id)
    canonico.insert(2, "fuente", informe.fuente)
    canonico.insert(3, "hoja", informe.hoja)

    insertados, omitidos = db.insertar_movimientos(canonico)
    estado = "PROCESADO" if insertados else "SIN_REGISTROS_NUEVOS"
    db.registrar_carga(
        registro_base
        | {
            "estado": estado,
            "n_insertados": insertados,
            "n_omitidos_duplicados": omitidos,
        }
    )
    mensaje = f"{insertados} movimientos nuevos; {omitidos} ya existentes omitidos."
    return ResumenIngesta(
        carga_id=carga_id,
        estado=estado,
        insertados=insertados,
        omitidos_duplicados=omitidos,
        informe=informe,
        mensaje=mensaje,
    )


def materializar_kardex_cache(db: Warehouse, config: ProjectConfig) -> Path:
    """Escribe el kardex combinado del centro configurado como cache del pipeline.

    El pipeline existente (``io.load_kardex``) consume este CSV; así la ingesta
    incremental alimenta las 11 etapas sin modificar su lógica.
    """
    centro = str(config.project["center_id"])
    movimientos = db.leer_movimientos(centro=centro)
    if movimientos.empty:
        raise ValueError(
            f"No hay movimientos en el almacén lógico para el centro {centro}. "
            "Carga primero el histórico MB51."
        )
    columnas = COLUMNAS_MOVIMIENTO + ["fila_original", "carga_id", "llave_negocio"]
    presentes = [c for c in columnas if c in movimientos.columns]
    destino = config.resolve("kardex_cache_csv")
    destino.parent.mkdir(parents=True, exist_ok=True)
    movimientos[presentes].to_csv(destino, index=False, encoding="utf-8-sig")
    return destino
