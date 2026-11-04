"""Reporte "Gastos de caja chica" (docs/AJUSTES_V1.1.md, etapa 6.2, D4):
los egresos manuales de caja (gastos y retiros) entre dos fechas, con
subtotal por categoría."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from ios.data import caja as datos_caja
from ios.data import categorias_caja as datos_categorias
from ios.data import formas_pago as datos_formas_pago

SIN_CATEGORIA = "(sin categoría)"


@dataclass
class FilaGasto:
    movimiento_id: int
    fecha: str
    categoria_nombre: str
    concepto: str
    forma_pago_nombre: str
    monto: Decimal


@dataclass
class SubtotalCategoria:
    categoria_id: int | None
    nombre: str
    monto: Decimal


@dataclass
class GastosCajaChica:
    filas: list[FilaGasto]
    subtotales_por_categoria: list[SubtotalCategoria]
    total: Decimal


def gastos_de_caja_chica(
    conexion: sqlite3.Connection,
    fecha_desde: str,
    fecha_hasta: str,
    categoria_id: int | None = None,
    forma_pago_id: int | None = None,
) -> GastosCajaChica:
    movimientos = datos_caja.listar_egresos_manuales(
        conexion, fecha_desde, fecha_hasta, categoria_id=categoria_id, forma_pago_id=forma_pago_id
    )

    nombres_categoria = {c["id"]: c["nombre"] for c in datos_categorias.listar_categorias(
        conexion, incluir_inactivas=True
    )}
    nombres_forma_pago = {f["id"]: f["nombre"] for f in datos_formas_pago.listar_formas_pago(
        conexion, incluir_inactivas=True
    )}

    filas = []
    montos_por_categoria: dict[int | None, Decimal] = {}
    for movimiento in movimientos:
        categoria_nombre = nombres_categoria.get(movimiento["categoria_id"], SIN_CATEGORIA)
        filas.append(
            FilaGasto(
                movimiento_id=movimiento["id"],
                fecha=movimiento["fecha_hora"][:10],
                categoria_nombre=categoria_nombre,
                concepto=movimiento["concepto"] or "",
                forma_pago_nombre=nombres_forma_pago.get(movimiento["forma_pago_id"], ""),
                monto=movimiento["monto"],
            )
        )
        clave = movimiento["categoria_id"]
        montos_por_categoria[clave] = montos_por_categoria.get(clave, Decimal(0)) + movimiento["monto"]

    subtotales = [
        SubtotalCategoria(
            categoria_id=categoria_id_,
            nombre=nombres_categoria.get(categoria_id_, SIN_CATEGORIA),
            monto=monto,
        )
        for categoria_id_, monto in montos_por_categoria.items()
    ]
    subtotales.sort(key=lambda s: s.nombre)

    return GastosCajaChica(
        filas=filas,
        subtotales_por_categoria=subtotales,
        total=sum((f.monto for f in filas), Decimal(0)),
    )
