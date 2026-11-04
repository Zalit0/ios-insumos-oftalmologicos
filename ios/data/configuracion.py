"""Consultas SQL de configuración (fila única, id = 1)."""

from __future__ import annotations

import sqlite3


def obtener_configuracion(conexion: sqlite3.Connection) -> sqlite3.Row:
    return conexion.execute("SELECT * FROM configuracion WHERE id = 1").fetchone()


def actualizar_configuracion(conexion: sqlite3.Connection, campos: dict) -> None:
    columnas = ", ".join(f"{columna} = ?" for columna in campos)
    valores = list(campos.values())
    conexion.execute(f"UPDATE configuracion SET {columnas} WHERE id = 1", valores)
