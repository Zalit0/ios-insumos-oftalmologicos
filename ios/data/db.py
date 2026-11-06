"""Conexión a la base SQLite de IOS.

Guarda los importes y porcentajes como texto decimal (columna declarada
``DECIMAL_TEXT``, con afinidad TEXT para que SQLite no los convierta a
``REAL``) y los lee de vuelta como ``decimal.Decimal``, para no perder
precisión nunca (ver docs/PLAN.md, sección "Modelo de datos").
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from ios.data.migraciones import MIGRACIONES, aplicar_migraciones, version_actual

RUTA_BASE_POR_DEFECTO = Path(r"C:\ProgramData\IOS\ios.db")
VARIABLE_ENTORNO_RUTA = "IOS_DB_PATH"

sqlite3.register_adapter(Decimal, str)
sqlite3.register_converter("DECIMAL_TEXT", lambda valor: Decimal(valor.decode("utf-8")))


def ruta_base_de_datos() -> Path:
    """Ruta del archivo .db: la de la variable de entorno si está definida."""
    ruta_env = os.environ.get(VARIABLE_ENTORNO_RUTA)
    return Path(ruta_env) if ruta_env else RUTA_BASE_POR_DEFECTO


def _respaldar_antes_de_migrar(ruta: Path) -> Path:
    """Copia la base tal como está antes de aplicar ninguna migración
    pendiente — si una migración rompe algo en la PC de un cliente (un
    corte de luz a mitad de la copia de una tabla, un antivirus que traba
    un archivo), queda este archivo para poder volver atrás a mano
    (reemplazarlo por ``ios.db`` y reinstalar la versión anterior) sin
    haber perdido nada. Devuelve la ruta del backup creado."""
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = ruta.with_name(f"{ruta.stem}.bak-{marca}{ruta.suffix}")
    shutil.copy2(ruta, destino)
    return destino


def _conectar_sin_migrar(ruta: Path) -> sqlite3.Connection:
    conexion = sqlite3.connect(str(ruta), detect_types=sqlite3.PARSE_DECLTYPES)
    conexion.execute("PRAGMA foreign_keys = ON")
    conexion.row_factory = sqlite3.Row
    return conexion


def conectar(ruta: Path | str | None = None) -> sqlite3.Connection:
    """Abre (y crea si falta) la base de datos, con las migraciones aplicadas.

    Si ya existe un archivo y le falta aplicar alguna migración, lo
    respalda primero (``_respaldar_antes_de_migrar``): es el único momento
    en que el esquema cambia, así que es el único momento en que vale la
    pena pagar el costo de la copia."""
    ruta = Path(ruta) if ruta is not None else ruta_base_de_datos()
    ruta.parent.mkdir(parents=True, exist_ok=True)

    if ruta.exists():
        conexion = _conectar_sin_migrar(ruta)
        hay_migraciones_pendientes = version_actual(conexion) < len(MIGRACIONES)
        conexion.close()
        if hay_migraciones_pendientes:
            _respaldar_antes_de_migrar(ruta)

    conexion = _conectar_sin_migrar(ruta)
    aplicar_migraciones(conexion)

    return conexion
