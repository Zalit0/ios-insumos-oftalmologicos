"""Reporte "Compras por cliente" (docs/AJUSTES_V1.1.md, etapa 6.1):
cuánto compró un cliente entre dos fechas, con subtotal por sucursal si
tiene más de una; o un ranking de todos los clientes del período."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from ios.data import clientes as datos_clientes
from ios.data import comprobantes as datos_comprobantes
from ios.data import recibos as datos_recibos
from ios.domain.calculos import calcular_saldo_comprobante


@dataclass
class FilaComprobante:
    comprobante_id: int
    numero: str
    fecha: str
    sucursal_id: int
    sucursal_nombre: str
    monto_lista: Decimal
    monto_final: Decimal
    iva_discriminado: Decimal
    cobrado: Decimal
    pendiente: Decimal


@dataclass
class SubtotalSucursal:
    sucursal_id: int
    nombre: str
    cantidad: int
    monto_lista: Decimal
    monto_final: Decimal
    iva: Decimal
    cobrado: Decimal
    pendiente: Decimal


@dataclass
class ComprasCliente:
    cliente_id: int
    filas: list[FilaComprobante]
    subtotales_por_sucursal: list[SubtotalSucursal]
    cantidad: int
    total_lista: Decimal
    total_descuento: Decimal
    total_final: Decimal
    total_iva: Decimal
    total_cobrado: Decimal
    total_pendiente: Decimal


def compras_de_cliente(
    conexion: sqlite3.Connection,
    cliente_id: int,
    fecha_desde: str,
    fecha_hasta: str,
    sucursal_id: int | None = None,
) -> ComprasCliente:
    if datos_clientes.obtener_cliente(conexion, cliente_id) is None:
        raise ValueError(f"No existe el cliente {cliente_id}.")

    comprobantes = datos_comprobantes.listar_comprobantes(
        conexion,
        cliente_id=cliente_id,
        sucursal_id=sucursal_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        estado="vigente",
    )

    nombres_sucursal = {
        sucursal["id"]: sucursal["nombre"]
        for sucursal in datos_clientes.listar_sucursales(conexion, cliente_id, incluir_inactivas=True)
    }

    filas: list[FilaComprobante] = []
    filas_por_sucursal: dict[int, list[FilaComprobante]] = {}
    for comprobante in comprobantes:
        cobrado = datos_recibos.total_aplicado_a_comprobante(conexion, comprobante["id"])
        pendiente = calcular_saldo_comprobante(comprobante["monto_final"], cobrado)
        fila = FilaComprobante(
            comprobante_id=comprobante["id"],
            numero=comprobante["numero"],
            fecha=comprobante["fecha"],
            sucursal_id=comprobante["sucursal_id"],
            sucursal_nombre=nombres_sucursal.get(comprobante["sucursal_id"], ""),
            monto_lista=comprobante["monto_lista"],
            monto_final=comprobante["monto_final"],
            iva_discriminado=comprobante["iva_discriminado"],
            cobrado=cobrado,
            pendiente=pendiente,
        )
        filas.append(fila)
        filas_por_sucursal.setdefault(fila.sucursal_id, []).append(fila)

    subtotales = []
    if len(filas_por_sucursal) > 1:
        for sucursal_id_, filas_sucursal in filas_por_sucursal.items():
            subtotales.append(
                SubtotalSucursal(
                    sucursal_id=sucursal_id_,
                    nombre=nombres_sucursal.get(sucursal_id_, ""),
                    cantidad=len(filas_sucursal),
                    monto_lista=sum((f.monto_lista for f in filas_sucursal), Decimal(0)),
                    monto_final=sum((f.monto_final for f in filas_sucursal), Decimal(0)),
                    iva=sum((f.iva_discriminado for f in filas_sucursal), Decimal(0)),
                    cobrado=sum((f.cobrado for f in filas_sucursal), Decimal(0)),
                    pendiente=sum((f.pendiente for f in filas_sucursal), Decimal(0)),
                )
            )

    total_lista = sum((f.monto_lista for f in filas), Decimal(0))
    total_final = sum((f.monto_final for f in filas), Decimal(0))

    return ComprasCliente(
        cliente_id=cliente_id,
        filas=filas,
        subtotales_por_sucursal=subtotales,
        cantidad=len(filas),
        total_lista=total_lista,
        total_descuento=total_lista - total_final,
        total_final=total_final,
        total_iva=sum((f.iva_discriminado for f in filas), Decimal(0)),
        total_cobrado=sum((f.cobrado for f in filas), Decimal(0)),
        total_pendiente=sum((f.pendiente for f in filas), Decimal(0)),
    )


@dataclass
class FilaRanking:
    cliente_id: int
    nombre: str
    cantidad: int
    total_final: Decimal


def ranking_todos_los_clientes(
    conexion: sqlite3.Connection, fecha_desde: str, fecha_hasta: str
) -> list[FilaRanking]:
    """Todos los clientes con compras en el período, de mayor a menor total
    facturado. No incluye clientes sin movimientos en el rango."""
    ranking = []
    for cliente in datos_clientes.listar_clientes(conexion, incluir_inactivos=True):
        comprobantes = datos_comprobantes.listar_comprobantes(
            conexion,
            cliente_id=cliente["id"],
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estado="vigente",
        )
        if not comprobantes:
            continue
        ranking.append(
            FilaRanking(
                cliente_id=cliente["id"],
                nombre=cliente["nombre"],
                cantidad=len(comprobantes),
                total_final=sum((c["monto_final"] for c in comprobantes), Decimal(0)),
            )
        )

    ranking.sort(key=lambda f: f.total_final, reverse=True)
    return ranking
