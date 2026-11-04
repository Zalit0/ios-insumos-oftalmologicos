"""IVA de un mes elegido, con el detalle de comprobantes y compras
(docs/PLAN.md, "Reportes y dashboard"). ``mes`` en formato 'YYYY-MM'."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from ios.data import comprobantes as datos_comprobantes
from ios.data import compras as datos_compras


@dataclass
class DetalleIvaMes:
    comprobantes: list[sqlite3.Row]
    compras: list[sqlite3.Row]
    iva_venta: Decimal
    iva_compra: Decimal
    iva_deuda: Decimal


def detalle_iva_del_mes(conexion: sqlite3.Connection, mes: str) -> DetalleIvaMes:
    comprobantes = datos_comprobantes.listar_comprobantes(conexion, mes=mes, estado="vigente")
    compras = datos_compras.listar_compras(conexion, mes=mes)

    iva_venta = sum((c["iva_discriminado"] for c in comprobantes), Decimal(0))
    iva_compra = sum((c["iva"] for c in compras), Decimal(0))

    return DetalleIvaMes(
        comprobantes=comprobantes,
        compras=compras,
        iva_venta=iva_venta,
        iva_compra=iva_compra,
        iva_deuda=iva_venta - iva_compra,
    )
