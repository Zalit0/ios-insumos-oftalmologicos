"""Consultas SQL para el resumen de un mes (docs/PLAN.md, etapa 8;
equivalente a la hoja TOTALES). ``mes`` siempre en formato 'YYYY-MM'."""

from __future__ import annotations

import sqlite3
from decimal import Decimal


def _montos(conexion: sqlite3.Connection, sql: str, parametros: tuple) -> list[Decimal]:
    return [fila["monto"] for fila in conexion.execute(sql, parametros).fetchall()]


def montos_finales_vigentes_del_mes(conexion: sqlite3.Connection, mes: str) -> list[Decimal]:
    return _montos(
        conexion,
        "SELECT monto_final AS monto FROM comprobantes "
        "WHERE estado = 'vigente' AND fecha LIKE ?",
        (f"{mes}%",),
    )


def ivas_venta_vigentes_del_mes(conexion: sqlite3.Connection, mes: str) -> list[Decimal]:
    return _montos(
        conexion,
        "SELECT iva_discriminado AS monto FROM comprobantes "
        "WHERE estado = 'vigente' AND fecha LIKE ?",
        (f"{mes}%",),
    )


def montos_aplicados_a_comprobantes_del_mes(
    conexion: sqlite3.Connection, mes: str
) -> list[Decimal]:
    """Montos aplicados a comprobantes con fecha en el mes, sin importar la
    fecha del recibo que los cubrió."""
    return _montos(
        conexion,
        """
        SELECT ap.monto_aplicado AS monto FROM aplicaciones_pago ap
        JOIN comprobantes c ON c.id = ap.comprobante_id
        JOIN recibos r ON r.id = ap.recibo_id
        WHERE c.estado = 'vigente' AND r.estado = 'vigente' AND c.fecha LIKE ?
        """,
        (f"{mes}%",),
    )


def montos_compras_del_mes(conexion: sqlite3.Connection, mes: str) -> list[Decimal]:
    return _montos(
        conexion, "SELECT monto AS monto FROM compras WHERE fecha LIKE ?", (f"{mes}%",)
    )


def ivas_compra_del_mes(conexion: sqlite3.Connection, mes: str) -> list[Decimal]:
    return _montos(
        conexion, "SELECT iva AS monto FROM compras WHERE fecha LIKE ?", (f"{mes}%",)
    )


def montos_pagos_proveedor_del_mes(conexion: sqlite3.Connection, mes: str) -> list[Decimal]:
    return _montos(
        conexion, "SELECT monto AS monto FROM pagos_proveedor WHERE fecha LIKE ?", (f"{mes}%",)
    )


def montos_finales_vigentes_hasta(conexion: sqlite3.Connection, fecha_corte: str) -> list[Decimal]:
    """Para la deuda total a una fecha (docs/AJUSTES_V1.1.md, etapa 6.3)."""
    return _montos(
        conexion,
        "SELECT monto_final AS monto FROM comprobantes WHERE estado = 'vigente' AND fecha <= ?",
        (fecha_corte,),
    )


def montos_recibos_vigentes_hasta(conexion: sqlite3.Connection, fecha_corte: str) -> list[Decimal]:
    """Para la deuda total a una fecha (docs/AJUSTES_V1.1.md, etapa 6.3)."""
    return _montos(
        conexion,
        "SELECT monto_total AS monto FROM recibos WHERE estado = 'vigente' AND fecha <= ?",
        (fecha_corte,),
    )
