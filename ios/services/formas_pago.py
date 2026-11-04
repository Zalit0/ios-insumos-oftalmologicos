"""Casos de uso de formas de pago (docs/PLAN.md: "Efectivo, transferencia
y cheque; configurable para sumar otras")."""

from __future__ import annotations

import sqlite3

from ios.data import formas_pago as datos

TIPOS_VALIDOS = {"efectivo", "banco", "cheque", "otro"}


def alta_forma_pago(conexion: sqlite3.Connection, nombre: str, tipo: str) -> int:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre de la forma de pago es obligatorio.")
    if tipo not in TIPOS_VALIDOS:
        raise ValueError(f"Tipo de forma de pago inválido: {tipo}")

    forma_id = datos.insertar_forma_pago(conexion, nombre, tipo)
    conexion.commit()
    return forma_id
