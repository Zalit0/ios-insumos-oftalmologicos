"""Flujo de caja en un período: ingresos y egresos por día y por
categoría, con el saldo acumulado (docs/PLAN.md, "Reportes y dashboard").
``fecha_desde``/``fecha_hasta`` en formato 'YYYY-MM-DD', inclusive."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class FilaFlujoDiario:
    fecha: str
    ingresos: Decimal
    egresos: Decimal
    saldo_del_dia: Decimal
    saldo_acumulado: Decimal


def _movimientos_del_periodo(
    conexion: sqlite3.Connection, fecha_desde: str, fecha_hasta: str
) -> list[sqlite3.Row]:
    return conexion.execute(
        """
        SELECT m.*, c.nombre AS categoria_nombre FROM movimientos_caja m
        LEFT JOIN categorias_caja c ON c.id = m.categoria_id
        WHERE date(m.fecha_hora) BETWEEN ? AND ?
        ORDER BY m.fecha_hora
        """,
        (fecha_desde, fecha_hasta),
    ).fetchall()


def flujo_de_caja_diario(
    conexion: sqlite3.Connection, fecha_desde: str, fecha_hasta: str
) -> list[FilaFlujoDiario]:
    totales_por_dia: dict[str, dict[str, Decimal]] = {}
    for movimiento in _movimientos_del_periodo(conexion, fecha_desde, fecha_hasta):
        dia = movimiento["fecha_hora"][:10]
        totales = totales_por_dia.setdefault(dia, {"ingresos": Decimal(0), "egresos": Decimal(0)})
        clave = "ingresos" if movimiento["tipo"] == "ingreso" else "egresos"
        totales[clave] += movimiento["monto"]

    filas = []
    saldo_acumulado = Decimal(0)
    for dia in sorted(totales_por_dia):
        totales = totales_por_dia[dia]
        saldo_del_dia = totales["ingresos"] - totales["egresos"]
        saldo_acumulado += saldo_del_dia
        filas.append(FilaFlujoDiario(
            fecha=dia,
            ingresos=totales["ingresos"],
            egresos=totales["egresos"],
            saldo_del_dia=saldo_del_dia,
            saldo_acumulado=saldo_acumulado,
        ))
    return filas


def flujo_de_caja_por_categoria(
    conexion: sqlite3.Connection, fecha_desde: str, fecha_hasta: str
) -> dict[str, dict[str, Decimal]]:
    totales: dict[str, dict[str, Decimal]] = {}
    for movimiento in _movimientos_del_periodo(conexion, fecha_desde, fecha_hasta):
        categoria = movimiento["categoria_nombre"] or movimiento["origen"]
        fila = totales.setdefault(categoria, {"ingresos": Decimal(0), "egresos": Decimal(0)})
        clave = "ingresos" if movimiento["tipo"] == "ingreso" else "egresos"
        fila[clave] += movimiento["monto"]
    return totales
