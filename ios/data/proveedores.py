"""Consultas SQL de proveedores."""

from __future__ import annotations

import sqlite3


def insertar_proveedor(conexion: sqlite3.Connection, nombre: str, cuit: str | None) -> int:
    cursor = conexion.execute(
        "INSERT INTO proveedores (nombre, cuit) VALUES (?, ?)", (nombre, cuit)
    )
    return cursor.lastrowid


def actualizar_proveedor(conexion: sqlite3.Connection, proveedor_id: int, campos: dict) -> None:
    columnas = ", ".join(f"{columna} = ?" for columna in campos)
    valores = list(campos.values())
    conexion.execute(
        f"UPDATE proveedores SET {columnas} WHERE id = ?", (*valores, proveedor_id)
    )


def obtener_proveedor(conexion: sqlite3.Connection, proveedor_id: int) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT * FROM proveedores WHERE id = ?", (proveedor_id,)
    ).fetchone()


def listar_proveedores(conexion: sqlite3.Connection) -> list[sqlite3.Row]:
    return conexion.execute("SELECT * FROM proveedores ORDER BY nombre").fetchall()
