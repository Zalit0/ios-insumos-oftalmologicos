"""Consultas SQL del catálogo de tipos de cristal (plan de detalle de
comprobantes, etapa 1)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal


def insertar_tipo_cristal(
    conexion: sqlite3.Connection,
    nombre: str,
    precio_lista: Decimal,
    categoria: str | None = None,
    vendido_por: str = "par",
    requiere_graduacion: bool = True,
    reponible: bool = True,
) -> int:
    cursor = conexion.execute(
        "INSERT INTO tipos_cristal "
        "(nombre, categoria, precio_lista, vendido_por, requiere_graduacion, reponible, activo) "
        "VALUES (?, ?, ?, ?, ?, ?, 1)",
        (nombre, categoria, precio_lista, vendido_por, int(requiere_graduacion), int(reponible)),
    )
    return cursor.lastrowid


def actualizar_tipo_cristal(conexion: sqlite3.Connection, tipo_id: int, campos: dict) -> None:
    columnas = ", ".join(f"{columna} = ?" for columna in campos)
    valores = list(campos.values())
    conexion.execute(f"UPDATE tipos_cristal SET {columnas} WHERE id = ?", (*valores, tipo_id))


def obtener_tipo_cristal(conexion: sqlite3.Connection, tipo_id: int) -> sqlite3.Row | None:
    return conexion.execute("SELECT * FROM tipos_cristal WHERE id = ?", (tipo_id,)).fetchone()


def listar_tipos_cristal(
    conexion: sqlite3.Connection, incluir_inactivos: bool = False
) -> list[sqlite3.Row]:
    if incluir_inactivos:
        return conexion.execute("SELECT * FROM tipos_cristal ORDER BY nombre").fetchall()
    return conexion.execute(
        "SELECT * FROM tipos_cristal WHERE activo = 1 ORDER BY nombre"
    ).fetchall()
