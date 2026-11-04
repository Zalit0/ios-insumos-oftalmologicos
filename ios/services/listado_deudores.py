"""Listado de deudores (docs/PLAN.md, sección "Reportes y dashboard"):
clientes con saldo, de mayor a menor, con la antigüedad del remito más
viejo impago."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ios.data import clientes as datos_clientes
from ios.services.cuenta_corriente import estado_de_cuenta_cliente


@dataclass
class Deudor:
    cliente_id: int
    nombre: str
    saldo: Decimal
    fecha_remito_mas_viejo: str | None
    antiguedad_dias: int | None


def listado_deudores(conexion: sqlite3.Connection, fecha_referencia: str) -> list[Deudor]:
    hoy = date.fromisoformat(fecha_referencia)
    deudores = []

    for cliente in datos_clientes.listar_clientes(conexion):
        estado = estado_de_cuenta_cliente(conexion, cliente["id"])
        if estado.saldo_consolidado <= 0:
            continue

        fecha_mas_vieja = None
        for sucursal in estado.sucursales:
            for comprobante in sucursal.comprobantes:
                if comprobante.saldo > 0:
                    if fecha_mas_vieja is None or comprobante.fecha < fecha_mas_vieja:
                        fecha_mas_vieja = comprobante.fecha

        antiguedad = (hoy - date.fromisoformat(fecha_mas_vieja)).days if fecha_mas_vieja else None

        deudores.append(Deudor(
            cliente_id=cliente["id"],
            nombre=cliente["nombre"],
            saldo=estado.saldo_consolidado,
            fecha_remito_mas_viejo=fecha_mas_vieja,
            antiguedad_dias=antiguedad,
        ))

    deudores.sort(key=lambda d: d.saldo, reverse=True)
    return deudores
