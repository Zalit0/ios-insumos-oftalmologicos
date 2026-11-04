"""Consultas SQL de tipos de comprobante (configurable; viene cargado RTO)."""

from __future__ import annotations

import sqlite3


def insertar_tipo_comprobante(
    conexion: sqlite3.Connection, nombre: str, abreviatura: str
) -> int:
    cursor = conexion.execute(
        "INSERT INTO tipos_comprobante (nombre, abreviatura, activo) VALUES (?, ?, 1)",
        (nombre, abreviatura),
    )
    return cursor.lastrowid


def actualizar_tipo_comprobante(
    conexion: sqlite3.Connection, tipo_id: int, campos: dict
) -> None:
    columnas = ", ".join(f"{columna} = ?" for columna in campos)
    valores = list(campos.values())
    conexion.execute(
        f"UPDATE tipos_comprobante SET {columnas} WHERE id = ?", (*valores, tipo_id)
    )


def obtener_tipo_comprobante(conexion: sqlite3.Connection, tipo_id: int) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT * FROM tipos_comprobante WHERE id = ?", (tipo_id,)
    ).fetchone()


def listar_tipos_comprobante(
    conexion: sqlite3.Connection, incluir_inactivos: bool = False
) -> list[sqlite3.Row]:
    if incluir_inactivos:
        return conexion.execute("SELECT * FROM tipos_comprobante ORDER BY nombre").fetchall()
    return conexion.execute(
        "SELECT * FROM tipos_comprobante WHERE activo = 1 ORDER BY nombre"
    ).fetchall()
