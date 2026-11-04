"""Casos de uso de pagos a proveedores ("depósitos"; salen de la caja).

Se puede pagar con un cheque que está en cartera: no sale efectivo ni
transferencia, pero el cheque pasa a "entregado a proveedor" y de todos
modos se registra el egreso de caja en la forma de pago "cheque".
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from ios.data import caja as datos_caja
from ios.data import cheques as datos_cheques
from ios.data import pagos_proveedor as datos
from ios.data import proveedores as datos_proveedores


def registrar_pago_proveedor(
    conexion: sqlite3.Connection,
    proveedor_id: int,
    fecha: str,
    monto: Decimal,
    forma_pago_id: int,
    cheque_entregado_id: int | None = None,
    referencia: str | None = None,
) -> int:
    if datos_proveedores.obtener_proveedor(conexion, proveedor_id) is None:
        raise ValueError(f"No existe el proveedor {proveedor_id}.")

    if cheque_entregado_id is not None:
        cheque = datos_cheques.obtener_cheque(conexion, cheque_entregado_id)
        if cheque is None:
            raise ValueError(f"No existe el cheque {cheque_entregado_id}.")
        if cheque["estado"] != "en_cartera":
            raise ValueError(
                f"El cheque {cheque_entregado_id} no está en cartera "
                f"(estado actual: {cheque['estado']})."
            )

    pago_id = datos.insertar_pago_proveedor(
        conexion, proveedor_id, fecha, monto, forma_pago_id, cheque_entregado_id, referencia
    )

    if cheque_entregado_id is not None:
        datos_cheques.marcar_estado_cheque(conexion, cheque_entregado_id, "entregado_a_proveedor")

    datos_caja.insertar_movimiento(
        conexion,
        fecha_hora=fecha,
        tipo="egreso",
        forma_pago_id=forma_pago_id,
        monto=monto,
        origen="pago_proveedor",
        concepto=f"Pago proveedor {pago_id}",
    )

    conexion.commit()
    return pago_id


def listar_pagos_proveedor(
    conexion: sqlite3.Connection, proveedor_id: int | None = None, mes: str | None = None
) -> list[sqlite3.Row]:
    return datos.listar_pagos_proveedor(conexion, proveedor_id=proveedor_id, mes=mes)
