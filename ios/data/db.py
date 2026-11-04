"""Conexión a la base SQLite de IOS.

Guarda los importes y porcentajes como texto decimal (columna declarada
``DECIMAL_TEXT``, con afinidad TEXT para que SQLite no los convierta a
``REAL``) y los lee de vuelta como ``decimal.Decimal``, para no perder
precisión nunca (ver docs/PLAN.md, sección "Modelo de datos").
"""

from __future__ import annotations

import os
import sqlite3
from decimal import Decimal
from pathlib import Path

from ios.data.migraciones import aplicar_migraciones

RUTA_BASE_POR_DEFECTO = Path(r"C:\ProgramData\IOS\ios.db")
VARIABLE_ENTORNO_RUTA = "IOS_DB_PATH"

sqlite3.register_adapter(Decimal, str)
sqlite3.register_converter("DECIMAL_TEXT", lambda valor: Decimal(valor.decode("utf-8")))


def ruta_base_de_datos() -> Path:
    """Ruta del archivo .db: la de la variable de entorno si está definida."""
    ruta_env = os.environ.get(VARIABLE_ENTORNO_RUTA)
    return Path(ruta_env) if ruta_env else RUTA_BASE_POR_DEFECTO


def conectar(ruta: Path | str | None = None) -> sqlite3.Connection:
    """Abre (y crea si falta) la base de datos, con las migraciones aplicadas."""
    ruta = Path(ruta) if ruta is not None else ruta_base_de_datos()
    ruta.parent.mkdir(parents=True, exist_ok=True)

    conexion = sqlite3.connect(str(ruta), detect_types=sqlite3.PARSE_DECLTYPES)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.row_factory = sqlite3.Row

    aplicar_migraciones(conexion)

    return conexion
