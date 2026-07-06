"""Capa de persistencia SQLite del proyecto.

Guarda el registro de cargas de archivos SAP, el histórico deduplicado de
movimientos, las ejecuciones del pipeline y el historial de alertas con su
ciclo de vida. Los archivos crudos nunca se modifican: aquí solo vive la
representación lógica y la trazabilidad.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS esquema (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS cargas (
    id TEXT PRIMARY KEY,
    nombre_original TEXT NOT NULL,
    nombre_interno TEXT,
    hash_sha256 TEXT NOT NULL,
    tamano_bytes INTEGER,
    extension TEXT,
    fuente TEXT,
    hojas TEXT,
    fecha_min TEXT,
    fecha_max TEXT,
    granularidad TEXT,
    n_registros INTEGER,
    n_insertados INTEGER,
    n_omitidos_duplicados INTEGER,
    centros TEXT,
    almacenes TEXT,
    materiales TEXT,
    estado TEXT NOT NULL,
    motivo_rechazo TEXT,
    traslape TEXT,
    usuario TEXT,
    version_pipeline TEXT,
    run_id TEXT,
    fecha_carga TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cargas_hash ON cargas(hash_sha256);

CREATE TABLE IF NOT EXISTS movimientos (
    llave_negocio TEXT PRIMARY KEY,
    carga_id TEXT NOT NULL,
    fuente TEXT,
    hoja TEXT,
    fila_original INTEGER,
    centro TEXT,
    almacen TEXT,
    material TEXT,
    descripcion_material TEXT,
    lote TEXT,
    documento_material TEXT,
    posicion_documento TEXT,
    ejercicio_documento TEXT,
    clase_movimiento TEXT,
    texto_clase_movimiento TEXT,
    clase_transaccion_evento TEXT,
    indicador_debe_haber TEXT,
    fecha TEXT,
    cantidad_um_entrada REAL,
    unidad_medida_entrada TEXT,
    cantidad_ump REAL,
    unidad_medida_paralela TEXT,
    cantidad REAL,
    orden TEXT,
    referencia TEXT,
    centro_receptor TEXT,
    usuario TEXT,
    texto_cabecera TEXT,
    texto_posicion TEXT,
    motivo_movimiento TEXT,
    ocurrencia INTEGER DEFAULT 1,
    creado_en TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mov_centro_fecha ON movimientos(centro, fecha);
CREATE INDEX IF NOT EXISTS idx_mov_carga ON movimientos(carga_id);

CREATE TABLE IF NOT EXISTS ejecuciones (
    run_id TEXT PRIMARY KEY,
    iniciado_en TEXT NOT NULL,
    terminado_en TEXT,
    config TEXT,
    version_pipeline TEXT,
    resultado TEXT,
    detalle TEXT
);

CREATE TABLE IF NOT EXISTS alertas (
    alerta_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    clave_seguimiento TEXT NOT NULL,
    familia TEXT,
    tipo TEXT,
    tipo_resultado TEXT,
    granularidad TEXT,
    fecha_inicial TEXT,
    fecha_final TEXT,
    semana TEXT,
    mes TEXT,
    granja TEXT,
    centro TEXT,
    almacen TEXT,
    caseta TEXT,
    material TEXT,
    cycle_id TEXT,
    edad_semana REAL,
    poblacion REAL,
    valor_real REAL,
    valor_esperado REAL,
    diferencia REAL,
    diferencia_pct REAL,
    capas TEXT,
    n_capas INTEGER,
    score REAL,
    severidad TEXT,
    cambio_severidad TEXT,
    motivo TEXT,
    evidencia TEXT,
    posible_causa TEXT,
    recomendacion TEXT,
    calidad_datos TEXT,
    estado TEXT,
    archivo_fuente TEXT,
    creado_en TEXT NOT NULL,
    PRIMARY KEY (alerta_id, run_id)
);

CREATE INDEX IF NOT EXISTS idx_alertas_run ON alertas(run_id);
CREATE INDEX IF NOT EXISTS idx_alertas_clave ON alertas(clave_seguimiento);

CREATE TABLE IF NOT EXISTS alertas_revision (
    clave_seguimiento TEXT PRIMARY KEY,
    estado_manual TEXT NOT NULL,
    comentario TEXT,
    usuario TEXT,
    actualizado_en TEXT NOT NULL
);
"""


def ahora_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Warehouse:
    """Acceso al almacén SQLite del proyecto."""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(_SCHEMA)
            existe = conn.execute("SELECT COUNT(*) FROM esquema").fetchone()[0]
            if not existe:
                conn.execute("INSERT INTO esquema(version) VALUES (?)", (SCHEMA_VERSION,))

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Cargas
    # ------------------------------------------------------------------
    def hash_ya_cargado(self, hash_sha256: str) -> str | None:
        """Devuelve el id de la carga previa con el mismo hash, si existe."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT id FROM cargas WHERE hash_sha256 = ? AND estado != 'RECHAZADO' LIMIT 1",
                (hash_sha256,),
            ).fetchone()
        return row["id"] if row else None

    def registrar_carga(self, registro: dict[str, Any]) -> None:
        registro = dict(registro)
        registro.setdefault("fecha_carga", ahora_iso())
        columnas = ", ".join(registro.keys())
        marcadores = ", ".join("?" for _ in registro)
        with self.connect() as conn:
            conn.execute(
                f"INSERT OR REPLACE INTO cargas ({columnas}) VALUES ({marcadores})",
                list(registro.values()),
            )

    def actualizar_carga(self, carga_id: str, cambios: dict[str, Any]) -> None:
        asignaciones = ", ".join(f"{k} = ?" for k in cambios)
        with self.connect() as conn:
            conn.execute(
                f"UPDATE cargas SET {asignaciones} WHERE id = ?",
                [*cambios.values(), carga_id],
            )

    def listar_cargas(self) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query(
                "SELECT * FROM cargas ORDER BY fecha_carga DESC", conn
            )

    # ------------------------------------------------------------------
    # Movimientos
    # ------------------------------------------------------------------
    def insertar_movimientos(self, movimientos: pd.DataFrame) -> tuple[int, int]:
        """Inserta movimientos de forma idempotente.

        Devuelve (insertados, omitidos_por_duplicado). La llave de negocio
        ya viene calculada en la columna ``llave_negocio``.
        """
        if movimientos.empty:
            return 0, 0
        batch_size = 5_000
        df = movimientos.copy()
        df["creado_en"] = ahora_iso()
        columnas = list(df.columns)
        marcadores = ", ".join("?" for _ in columnas)
        sql = (
            f"INSERT OR IGNORE INTO movimientos ({', '.join(columnas)}) "
            f"VALUES ({marcadores})"
        )
        insertados = 0
        with self.connect() as conn:
            lote = []
            for fila in df.itertuples(index=False, name=None):
                lote.append(tuple(None if pd.isna(v) else v for v in fila))
                if len(lote) >= batch_size:
                    antes = conn.total_changes
                    conn.executemany(sql, lote)
                    insertados += conn.total_changes - antes
                    lote.clear()
            if lote:
                antes = conn.total_changes
                conn.executemany(sql, lote)
                insertados += conn.total_changes - antes
        return insertados, len(df) - insertados

    def rango_existente(self, centro: str | None = None) -> tuple[str | None, str | None]:
        """Rango de fechas ya cargado, opcionalmente filtrado por centro."""
        query = "SELECT MIN(fecha), MAX(fecha) FROM movimientos"
        params: tuple[Any, ...] = ()
        if centro:
            query += " WHERE centro = ?"
            params = (centro,)
        with self.connect() as conn:
            row = conn.execute(query, params).fetchone()
        return row[0], row[1]

    def leer_movimientos(self, centro: str | None = None) -> pd.DataFrame:
        query = "SELECT * FROM movimientos"
        params: tuple[Any, ...] = ()
        if centro:
            query += " WHERE centro = ?"
            params = (centro,)
        query += " ORDER BY fecha, centro, almacen, material"
        with self.connect() as conn:
            return pd.read_sql_query(query, conn, params=params)

    # ------------------------------------------------------------------
    # Ejecuciones
    # ------------------------------------------------------------------
    def iniciar_ejecucion(self, run_id: str, config: str, version: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO ejecuciones (run_id, iniciado_en, config, version_pipeline) "
                "VALUES (?, ?, ?, ?)",
                (run_id, ahora_iso(), config, version),
            )

    def cerrar_ejecucion(self, run_id: str, resultado: str, detalle: str = "") -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE ejecuciones SET terminado_en = ?, resultado = ?, detalle = ? WHERE run_id = ?",
                (ahora_iso(), resultado, detalle, run_id),
            )

    def ultima_ejecucion_con_alertas(self, excluir_run_id: str | None = None) -> str | None:
        query = (
            "SELECT run_id FROM alertas "
            "WHERE (? IS NULL OR run_id != ?) "
            "ORDER BY creado_en DESC LIMIT 1"
        )
        with self.connect() as conn:
            row = conn.execute(query, (excluir_run_id, excluir_run_id)).fetchone()
        return row["run_id"] if row else None

    # ------------------------------------------------------------------
    # Alertas
    # ------------------------------------------------------------------
    def guardar_alertas(self, alertas: pd.DataFrame) -> int:
        if alertas.empty:
            return 0
        df = alertas.copy()
        if "creado_en" not in df.columns:
            df["creado_en"] = ahora_iso()
        columnas = list(df.columns)
        marcadores = ", ".join("?" for _ in columnas)
        sql = (
            f"INSERT OR REPLACE INTO alertas ({', '.join(columnas)}) "
            f"VALUES ({marcadores})"
        )
        registros = [
            tuple(None if pd.isna(v) else v for v in fila)
            for fila in df.itertuples(index=False, name=None)
        ]
        with self.connect() as conn:
            conn.executemany(sql, registros)
        return len(df)

    def leer_alertas(self, run_id: str | None = None) -> pd.DataFrame:
        query = "SELECT * FROM alertas"
        params: tuple[Any, ...] = ()
        if run_id:
            query += " WHERE run_id = ?"
            params = (run_id,)
        with self.connect() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def historial_alerta(self, clave_seguimiento: str) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query(
                "SELECT * FROM alertas WHERE clave_seguimiento = ? ORDER BY creado_en",
                conn,
                params=(clave_seguimiento,),
            )

    # ------------------------------------------------------------------
    # Revisión manual de alertas
    # ------------------------------------------------------------------
    def guardar_revision(
        self,
        clave_seguimiento: str,
        estado_manual: str,
        comentario: str = "",
        usuario: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO alertas_revision "
                "(clave_seguimiento, estado_manual, comentario, usuario, actualizado_en) "
                "VALUES (?, ?, ?, ?, ?)",
                (clave_seguimiento, estado_manual, comentario, usuario, ahora_iso()),
            )

    def leer_revisiones(self) -> pd.DataFrame:
        with self.connect() as conn:
            return pd.read_sql_query("SELECT * FROM alertas_revision", conn)
