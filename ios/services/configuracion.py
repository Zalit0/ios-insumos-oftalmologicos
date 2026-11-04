"""Casos de uso de configuración: IVA, comisión, número inicial de recibo
y redondeo (docs/PLAN.md, "Pantallas")."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from ios.data import configuracion as datos

CAMPOS_VALIDOS = {"iva_pct", "comision_pct", "numero_inicial_recibo", "redondeo_decimales"}


def obtener_configuracion(conexion: sqlite3.Connection) -> sqlite3.Row:
    return datos.obtener_configuracion(conexion)


def actualizar_configuracion(conexion: sqlite3.Connection, **campos) -> None:
    desconocidos = set(campos) - CAMPOS_VALIDOS
    if desconocidos:
        raise ValueError(f"Campo de configuración desconocido: {', '.join(desconocidos)}")

    if "iva_pct" in campos and campos["iva_pct"] < 0:
        raise ValueError("El IVA no puede ser negativo.")
    if "comision_pct" in campos and campos["comision_pct"] < 0:
        raise ValueError("La comisión no puede ser negativa.")
    if "numero_inicial_recibo" in campos and campos["numero_inicial_recibo"] < 1:
        raise ValueError("El número inicial de recibo tiene que ser mayor a cero.")
    if "redondeo_decimales" in campos and campos["redondeo_decimales"] < 0:
        raise ValueError("El redondeo no puede tener una cantidad negativa de decimales.")

    datos.actualizar_configuracion(conexion, campos)
    conexion.commit()
