"""Consultas SQL de clientes y sucursales. Sin lógica de negocio: eso vive
en ios/services/clientes.py."""

from __future__ import annotations

import sqlite3
from decimal import Decimal


def insertar_cliente(
    conexion: sqlite3.Connection,
    nombre: str,
    cuit: str | None,
    telefono: str | None,
    direccion: str | None,
    localidad: str | None,
    descuento_default: Decimal,
    con_iva_default: bool,
    es_particular: bool,
) -> int:
    cursor = conexion.execute(
        """
        INSERT INTO clientes
            (nombre, cuit, telefono, direccion, localidad,
             descuento_default, con_iva_default, es_particular, activo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            nombre,
            cuit,
            telefono,
            direccion,
            localidad,
            descuento_default,
            int(con_iva_default),
            int(es_particular),
        ),
    )
    return cursor.lastrowid


def actualizar_cliente(conexion: sqlite3.Connection, cliente_id: int, campos: dict) -> None:
    columnas = ", ".join(f"{columna} = ?" for columna in campos)
    valores = list(campos.values())
    conexion.execute(
        f"UPDATE clientes SET {columnas} WHERE id = ?", (*valores, cliente_id)
    )


def marcar_cliente_activo(conexion: sqlite3.Connection, cliente_id: int, activo: bool) -> None:
    conexion.execute(
        "UPDATE clientes SET activo = ? WHERE id = ?", (int(activo), cliente_id)
    )


def obtener_cliente(conexion: sqlite3.Connection, cliente_id: int) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT * FROM clientes WHERE id = ?", (cliente_id,)
    ).fetchone()


def obtener_cliente_por_nombre(conexion: sqlite3.Connection, nombre: str) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT * FROM clientes WHERE nombre = ? COLLATE NOCASE", (nombre,)
    ).fetchone()


def obtener_sucursal_por_nombre(
    conexion: sqlite3.Connection, cliente_id: int, nombre: str
) -> sqlite3.Row | None:
    """Busca una sucursal de ``cliente_id`` por nombre (sin distinguir
    mayúsculas), activa o no: evita crear una sucursal duplicada si ya
    existe de una carga anterior (docs/AJUSTES_V1.1.md, Importar desde
    Excel — reimportación)."""
    return conexion.execute(
        "SELECT * FROM sucursales WHERE cliente_id = ? AND nombre = ? COLLATE NOCASE",
        (cliente_id, nombre),
    ).fetchone()


def listar_clientes(
    conexion: sqlite3.Connection, incluir_inactivos: bool = False
) -> list[sqlite3.Row]:
    if incluir_inactivos:
        return conexion.execute("SELECT * FROM clientes ORDER BY nombre").fetchall()
    return conexion.execute(
        "SELECT * FROM clientes WHERE activo = 1 ORDER BY nombre"
    ).fetchall()


def insertar_sucursal(conexion: sqlite3.Connection, cliente_id: int, nombre: str) -> int:
    cursor = conexion.execute(
        "INSERT INTO sucursales (cliente_id, nombre) VALUES (?, ?)",
        (cliente_id, nombre),
    )
    return cursor.lastrowid


def actualizar_sucursal(conexion: sqlite3.Connection, sucursal_id: int, nombre: str) -> None:
    conexion.execute(
        "UPDATE sucursales SET nombre = ? WHERE id = ?", (nombre, sucursal_id)
    )


def marcar_sucursal_activa(conexion: sqlite3.Connection, sucursal_id: int, activo: bool) -> None:
    conexion.execute(
        "UPDATE sucursales SET activo = ? WHERE id = ?", (int(activo), sucursal_id)
    )


def obtener_sucursal(conexion: sqlite3.Connection, sucursal_id: int) -> sqlite3.Row | None:
    return conexion.execute("SELECT * FROM sucursales WHERE id = ?", (sucursal_id,)).fetchone()


def listar_sucursales(
    conexion: sqlite3.Connection, cliente_id: int, incluir_inactivas: bool = False
) -> list[sqlite3.Row]:
    if incluir_inactivas:
        return conexion.execute(
            "SELECT * FROM sucursales WHERE cliente_id = ? ORDER BY id", (cliente_id,)
        ).fetchall()
    return conexion.execute(
        "SELECT * FROM sucursales WHERE cliente_id = ? AND activo = 1 ORDER BY id", (cliente_id,)
    ).fetchall()


def contar_sucursales_activas(conexion: sqlite3.Connection, cliente_id: int) -> int:
    return conexion.execute(
        "SELECT COUNT(*) AS n FROM sucursales WHERE cliente_id = ? AND activo = 1", (cliente_id,)
    ).fetchone()["n"]
