"""Consultas SQL de pagos a proveedores ("depósitos" del Excel)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal


def insertar_pago_proveedor(
    conexion: sqlite3.Connection,
    proveedor_id: int,
    fecha: str,
    monto: Decimal,
    forma_pago_id: int,
    cheque_entregado_id: int | None,
    referencia: str | None,
) -> int:
    cursor = conexion.execute(
        """
        INSERT INTO pagos_proveedor
            (proveedor_id, fecha, monto, forma_pago_id, cheque_entregado_id, referencia)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (proveedor_id, fecha, monto, forma_pago_id, cheque_entregado_id, referencia),
    )
    return cursor.lastrowid


def obtener_pago_proveedor(conexion: sqlite3.Connection, pago_id: int) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT * FROM pagos_proveedor WHERE id = ?", (pago_id,)
    ).fetchone()


def listar_pagos_proveedor(
    conexion: sqlite3.Connection,
    proveedor_id: int | None = None,
    mes: str | None = None,
) -> list[sqlite3.Row]:
    """``mes`` en formato 'YYYY-MM'. Sin filtros, devuelve todo."""
    condiciones = []
    parametros: list = []

    if proveedor_id is not None:
        condiciones.append("proveedor_id = ?")
        parametros.append(proveedor_id)
    if mes is not None:
        condiciones.append("fecha LIKE ?")
        parametros.append(f"{mes}%")

    sql = "SELECT * FROM pagos_proveedor"
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY fecha, id"

    return conexion.execute(sql, parametros).fetchall()
