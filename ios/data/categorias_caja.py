"""Consultas SQL de categorías de caja (gastos, retiros, aportes...)."""

from __future__ import annotations

import sqlite3


def insertar_categoria(conexion: sqlite3.Connection, nombre: str, tipo: str) -> int:
    cursor = conexion.execute(
        "INSERT INTO categorias_caja (nombre, tipo, activo) VALUES (?, ?, 1)", (nombre, tipo)
    )
    return cursor.lastrowid


def actualizar_categoria(conexion: sqlite3.Connection, categoria_id: int, campos: dict) -> None:
    columnas = ", ".join(f"{columna} = ?" for columna in campos)
    valores = list(campos.values())
    conexion.execute(
        f"UPDATE categorias_caja SET {columnas} WHERE id = ?", (*valores, categoria_id)
    )


def obtener_categoria(conexion: sqlite3.Connection, categoria_id: int) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT * FROM categorias_caja WHERE id = ?", (categoria_id,)
    ).fetchone()


def listar_categorias(
    conexion: sqlite3.Connection, incluir_inactivas: bool = False
) -> list[sqlite3.Row]:
    if incluir_inactivas:
        return conexion.execute("SELECT * FROM categorias_caja ORDER BY nombre").fetchall()
    return conexion.execute(
        "SELECT * FROM categorias_caja WHERE activo = 1 ORDER BY nombre"
    ).fetchall()
