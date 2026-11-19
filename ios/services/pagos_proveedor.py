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


def editar_pago_proveedor(
    conexion: sqlite3.Connection,
    pago_id: int,
    fecha_hoy: str,
    **campos,
) -> None:
    """Corrige un pago a proveedor ya cargado (por ejemplo, un monto mal
    tipeado por confundir el separador decimal). Si cambia el monto, la
    forma de pago o el cheque entregado, el movimiento de caja original
    se revierte y se vuelve a generar con los valores corregidos — la
    reversión y el movimiento nuevo se asientan siempre en la caja de
    ``fecha_hoy``, nunca en la del día original (que puede estar ya
    cerrada), igual que al anular un recibo."""
    pago = datos.obtener_pago_proveedor(conexion, pago_id)
    if pago is None:
        raise ValueError(f"No existe el pago {pago_id}.")

    monto_nuevo = campos.get("monto", pago["monto"])
    forma_pago_nueva = campos.get("forma_pago_id", pago["forma_pago_id"])
    cheque_nuevo = campos.get("cheque_entregado_id", pago["cheque_entregado_id"])

    if cheque_nuevo is not None and cheque_nuevo != pago["cheque_entregado_id"]:
        cheque = datos_cheques.obtener_cheque(conexion, cheque_nuevo)
        if cheque is None:
            raise ValueError(f"No existe el cheque {cheque_nuevo}.")
        if cheque["estado"] != "en_cartera":
            raise ValueError(
                f"El cheque {cheque_nuevo} no está en cartera "
                f"(estado actual: {cheque['estado']})."
            )

    cambia_caja = (
        monto_nuevo != pago["monto"]
        or forma_pago_nueva != pago["forma_pago_id"]
        or cheque_nuevo != pago["cheque_entregado_id"]
    )

    if cambia_caja:
        if pago["cheque_entregado_id"] is not None and pago["cheque_entregado_id"] != cheque_nuevo:
            datos_cheques.marcar_estado_cheque(conexion, pago["cheque_entregado_id"], "en_cartera")
        if cheque_nuevo is not None and cheque_nuevo != pago["cheque_entregado_id"]:
            datos_cheques.marcar_estado_cheque(conexion, cheque_nuevo, "entregado_a_proveedor")

        # Si ya se corrigió antes, cada corrección vuelve a postear con el
        # mismo concepto ("pago_proveedor"): el vigente es siempre el más
        # reciente, nunca el original ya revertido.
        movimientos_previos = datos_caja.listar_movimientos_por_concepto(
            conexion, f"Pago proveedor {pago_id}", "pago_proveedor"
        )
        movimiento_vigente = movimientos_previos[-1] if movimientos_previos else None
        relacionado_id = movimiento_vigente["id"] if movimiento_vigente is not None else None
        monto_a_revertir = movimiento_vigente["monto"] if movimiento_vigente is not None else pago["monto"]
        forma_a_revertir = (
            movimiento_vigente["forma_pago_id"] if movimiento_vigente is not None
            else pago["forma_pago_id"]
        )

        datos_caja.insertar_movimiento(
            conexion,
            fecha_hora=fecha_hoy,
            tipo="ingreso",
            forma_pago_id=forma_a_revertir,
            monto=monto_a_revertir,
            origen="anulacion",
            concepto=f"Corrección pago proveedor {pago_id}: reversión del valor anterior",
            movimiento_relacionado_id=relacionado_id,
        )
        datos_caja.insertar_movimiento(
            conexion,
            fecha_hora=fecha_hoy,
            tipo="egreso",
            forma_pago_id=forma_pago_nueva,
            monto=monto_nuevo,
            origen="pago_proveedor",
            concepto=f"Pago proveedor {pago_id}",
            movimiento_relacionado_id=relacionado_id,
        )

    datos.actualizar_pago_proveedor(conexion, pago_id, campos)
    conexion.commit()
