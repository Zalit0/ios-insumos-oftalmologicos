"""Migraciones de esquema basadas en ``PRAGMA user_version``.

Cada migración es un paso numerado (1, 2, 3...) que se aplica una sola vez.
Al abrir la base, ``aplicar_migraciones`` corre, en orden, las que falten
entre la versión actual y la última disponible.
"""

from __future__ import annotations

import sqlite3

from ios.data.esquema import (
    MIGRACION_1_DATOS_INICIALES,
    MIGRACION_1_ESQUEMA,
    MIGRACION_2_ESQUEMA,
    MIGRACION_3_ESQUEMA,
    MIGRACION_4_ESQUEMA,
    MIGRACION_5_ESQUEMA,
)

# Lista ordenada de migraciones: la posición N (1-based) es la versión N.
# Agregar una migración nueva = agregar un elemento al final de esta lista,
# nunca modificar las que ya existen.
MIGRACIONES: list[str] = [
    MIGRACION_1_ESQUEMA + MIGRACION_1_DATOS_INICIALES,
    MIGRACION_2_ESQUEMA,
    MIGRACION_3_ESQUEMA,
    MIGRACION_4_ESQUEMA,
    MIGRACION_5_ESQUEMA,
]


def version_actual(conexion: sqlite3.Connection) -> int:
    return conexion.execute("PRAGMA user_version").fetchone()[0]


def aplicar_migraciones(conexion: sqlite3.Connection) -> None:
    version = version_actual(conexion)

    for numero, script in enumerate(MIGRACIONES[version:], start=version + 1):
        conexion.executescript(script)
        conexion.execute(f"PRAGMA user_version = {numero}")
        conexion.commit()
