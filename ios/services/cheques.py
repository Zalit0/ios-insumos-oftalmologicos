"""Casos de uso de la pantalla de cheques (docs/PLAN.md, etapa 7).

Un cheque en cartera puede: cobrarse (transferencia interna de la forma de
pago "cheque" a la forma "banco" elegida), entregarse a un proveedor (ya
se hace en ios/services/pagos_proveedor.py) o rechazarse.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from ios.data import cheques as datos
from ios.services.caja import registrar_transferencia_interna


def _validar_en_cartera(conexion: sqlite3.Connection, cheque_id: int) -> sqlite3.Row:
    cheque = datos.obtener_cheque(conexion, cheque_id)
    if cheque is None:
        raise ValueError(f"No existe el cheque {cheque_id}.")
    if cheque["estado"] != "en_cartera":
        raise ValueError(
            f"El cheque {cheque_id} no está en cartera (estado actual: {cheque['estado']})."
        )
    return cheque


def cobrar_cheque(
    conexion: sqlite3.Connection,
    cheque_id: int,
    fecha_hora: str,
    forma_pago_cheque_id: int,
    forma_pago_banco_id: int,
) -> None:
    cheque = _validar_en_cartera(conexion, cheque_id)

    registrar_transferencia_interna(
        conexion,
        fecha_hora,
        forma_pago_origen_id=forma_pago_cheque_id,
        forma_pago_destino_id=forma_pago_banco_id,
        monto=cheque["monto"],
        concepto=f"Cobro cheque {cheque['numero']}",
    )

    datos.marcar_estado_cheque(conexion, cheque_id, "cobrado")
    conexion.commit()


def rechazar_cheque(conexion: sqlite3.Connection, cheque_id: int) -> None:
    _validar_en_cartera(conexion, cheque_id)

    datos.marcar_estado_cheque(conexion, cheque_id, "rechazado")
    conexion.commit()
