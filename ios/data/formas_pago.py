"""Consultas SQL de formas de pago."""

from __future__ import annotations

import sqlite3


def obtener_forma_pago_por_nombre(conexion: sqlite3.Connection, nombre: str) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT * FROM formas_pago WHERE nombre = ? COLLATE NOCASE", (nombre,)
    ).fetchone()


def insertar_forma_pago(conexion: sqlite3.Connection, nombre: str, tipo: str) -> int:
    cursor = conexion.execute(
        "INSERT INTO formas_pago (nombre, tipo, activo) VALUES (?, ?, 1)", (nombre, tipo)
    )
    return cursor.lastrowid


def listar_formas_pago(conexion: sqlite3.Connection, incluir_inactivas: bool = False) -> list:
    if incluir_inactivas:
        return conexion.execute("SELECT * FROM formas_pago ORDER BY nombre").fetchall()
    return conexion.execute(
        "SELECT * FROM formas_pago WHERE activo = 1 ORDER BY nombre"
    ).fetchall()
