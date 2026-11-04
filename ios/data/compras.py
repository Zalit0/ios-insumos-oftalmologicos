"""Consultas SQL de compras (facturas de proveedores)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal


def insertar_compra(
    conexion: sqlite3.Connection,
    proveedor_id: int,
    fecha: str,
    numero_factura: str,
    monto: Decimal,
    iva: Decimal,
    tasa_iva: Decimal,
    iva_manual: bool,
) -> int:
    cursor = conexion.execute(
        """
        INSERT INTO compras (proveedor_id, fecha, numero_factura, monto, iva, tasa_iva, iva_manual)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (proveedor_id, fecha, numero_factura, monto, iva, tasa_iva, int(iva_manual)),
    )
    return cursor.lastrowid


def obtener_compra(conexion: sqlite3.Connection, compra_id: int) -> sqlite3.Row | None:
    return conexion.execute("SELECT * FROM compras WHERE id = ?", (compra_id,)).fetchone()


def listar_compras(
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

    sql = "SELECT * FROM compras"
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY fecha, id"

    return conexion.execute(sql, parametros).fetchall()
