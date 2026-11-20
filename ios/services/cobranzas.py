"""Casos de uso de cobranzas: recibos, cheques y aplicación a remitos
(docs/PLAN.md, etapa 4).

Un pago puede combinar varias formas de pago (y varios cheques) y cubrir
varios remitos, incluso en pagos parciales. Cada pago manual registra su
movimiento de caja; uno importado, no. El excedente sobre lo aplicado a
remitos queda como saldo a favor, que se puede aplicar después a remitos
nuevos sin generar movimiento de caja.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from ios.data import caja as datos_caja
from ios.data import cheques as datos_cheques
from ios.data import cierres_caja as datos_cierres
from ios.data import comprobantes as datos_comprobantes
from ios.data import formas_pago as datos_formas_pago
from ios.data import recibos as datos
from ios.domain.calculos import calcular_saldo_comprobante


@dataclass
class DatosCheque:
    numero: str
    banco: str | None
    fecha_cobro: str


@dataclass
class Pago:
    forma_pago_id: int
    monto: Decimal
    cheque: DatosCheque | None = None


@dataclass
class AplicacionARemito:
    comprobante_id: int
    monto: Decimal


def _saldo_pendiente_comprobante(
    conexion: sqlite3.Connection, comprobante_id: int, cliente_id: int
) -> Decimal:
    comprobante = datos_comprobantes.obtener_comprobante(conexion, comprobante_id)
    if comprobante is None:
        raise ValueError(f"No existe el comprobante {comprobante_id}.")
    if comprobante["cliente_id"] != cliente_id:
        raise ValueError(
            f"El comprobante {comprobante_id} no es del cliente {cliente_id}."
        )
    total_aplicado = datos.total_aplicado_a_comprobante(conexion, comprobante_id)
    return calcular_saldo_comprobante(comprobante["monto_final"], total_aplicado)


def asentar_cobranza(
    conexion: sqlite3.Connection,
    cliente_id: int,
    fecha: str,
    pagos: list[Pago],
    aplicaciones: list[AplicacionARemito],
    origen: str = "manual",
    fecha_hoy: str | None = None,
) -> int:
    if not pagos:
        raise ValueError("La cobranza necesita al menos una forma de pago.")
    if fecha_hoy is not None and fecha > fecha_hoy:
        raise ValueError("No se puede registrar un recibo con fecha posterior a hoy.")

    monto_total = sum((pago.monto for pago in pagos), Decimal(0))
    monto_aplicado = sum((aplicacion.monto for aplicacion in aplicaciones), Decimal(0))
    if monto_aplicado > monto_total:
        raise ValueError("No se puede aplicar más de lo que cubre el pago.")

    for aplicacion in aplicaciones:
        saldo_pendiente = _saldo_pendiente_comprobante(
            conexion, aplicacion.comprobante_id, cliente_id
        )
        if aplicacion.monto > saldo_pendiente:
            raise ValueError(
                f"El monto aplicado al comprobante {aplicacion.comprobante_id} "
                f"supera su saldo pendiente ({saldo_pendiente})."
            )

    numero = datos.siguiente_numero_recibo(conexion)
    recibo_id = datos.insertar_recibo(conexion, numero, fecha, cliente_id, monto_total, origen)
    concepto = f"Recibo {numero}"

    fecha_movimiento = fecha
    nota_movimiento = None
    if origen == "manual" and fecha_hoy is not None and fecha_hoy != fecha:
        cierre = datos_cierres.obtener_cierre_por_fecha(conexion, fecha)
        if cierre is not None and cierre["estado"] == "cerrado":
            fecha_movimiento = fecha_hoy
            nota_movimiento = (
                f"Recibo con fecha {fecha}: la caja de ese día ya estaba cerrada, "
                f"se registra en la de hoy."
            )

    for pago in pagos:
        cheque_id = None
        if pago.cheque is not None:
            cheque_id = datos_cheques.insertar_cheque(
                conexion,
                pago.cheque.numero,
                cliente_id,
                pago.cheque.banco,
                pago.monto,
                pago.cheque.fecha_cobro,
                recibo_origen_id=recibo_id,
            )

        recibo_pago_id = datos.insertar_recibo_pago(
            conexion, recibo_id, pago.forma_pago_id, pago.monto, cheque_id
        )

        if origen == "manual":
            movimiento_id = datos_caja.insertar_movimiento(
                conexion,
                fecha_hora=fecha_movimiento,
                tipo="ingreso",
                forma_pago_id=pago.forma_pago_id,
                monto=pago.monto,
                origen="recibo",
                concepto=concepto,
                nota=nota_movimiento,
            )
            datos.actualizar_recibo_pago(
                conexion, recibo_pago_id, {"movimiento_caja_id": movimiento_id}
            )

    for aplicacion in aplicaciones:
        datos.insertar_aplicacion_pago(
            conexion, recibo_id, aplicacion.comprobante_id, aplicacion.monto
        )

    conexion.commit()
    return recibo_id


def aplicar_saldo_a_favor(
    conexion: sqlite3.Connection,
    cliente_id: int,
    aplicaciones: list[AplicacionARemito],
) -> None:
    """Aplica saldo a favor de recibos vigentes del cliente a remitos
    pendientes, sin generar movimiento de caja (el ingreso ya se registró
    cuando se asentó el recibo original)."""
    if not aplicaciones:
        return

    for aplicacion in aplicaciones:
        saldo_pendiente = _saldo_pendiente_comprobante(
            conexion, aplicacion.comprobante_id, cliente_id
        )
        if aplicacion.monto > saldo_pendiente:
            raise ValueError(
                f"El monto aplicado al comprobante {aplicacion.comprobante_id} "
                f"supera su saldo pendiente ({saldo_pendiente})."
            )

    creditos = []
    for recibo in datos.listar_recibos_vigentes_cliente(conexion, cliente_id):
        disponible = recibo["monto_total"] - datos.total_aplicado_de_recibo(conexion, recibo["id"])
        if disponible > 0:
            creditos.append({"recibo_id": recibo["id"], "disponible": disponible})

    total_disponible = sum((credito["disponible"] for credito in creditos), Decimal(0))
    total_solicitado = sum((aplicacion.monto for aplicacion in aplicaciones), Decimal(0))
    if total_solicitado > total_disponible:
        raise ValueError(
            f"El cliente no tiene suficiente saldo a favor "
            f"(disponible {total_disponible}, solicitado {total_solicitado})."
        )

    for aplicacion in aplicaciones:
        restante = aplicacion.monto
        for credito in creditos:
            if restante <= 0:
                break
            if credito["disponible"] <= 0:
                continue
            usar = min(restante, credito["disponible"])
            datos.insertar_aplicacion_pago(
                conexion, credito["recibo_id"], aplicacion.comprobante_id, usar
            )
            credito["disponible"] -= usar
            restante -= usar

    conexion.commit()


def anular_recibo(conexion: sqlite3.Connection, recibo_id: int, fecha_anulacion: str) -> None:
    """Anula un recibo: libera los saldos que cubría (las aplicaciones de
    un recibo anulado dejan de contar), sus cheques pasan a anulado y se
    genera el contramovimiento de caja de cada ingreso que generó."""
    recibo = datos.obtener_recibo(conexion, recibo_id)
    if recibo is None:
        raise ValueError(f"No existe el recibo {recibo_id}.")
    if recibo["estado"] != "vigente":
        raise ValueError(f"El recibo {recibo_id} ya está anulado.")

    for cheque in datos_cheques.listar_cheques_de_recibo_origen(conexion, recibo_id):
        datos_cheques.marcar_estado_cheque(conexion, cheque["id"], "anulado")

    concepto = f"Recibo {recibo['numero']}"
    for movimiento in datos_caja.listar_movimientos_por_concepto(conexion, concepto, "recibo"):
        datos_caja.insertar_movimiento(
            conexion,
            fecha_hora=fecha_anulacion,
            tipo="egreso",
            forma_pago_id=movimiento["forma_pago_id"],
            monto=movimiento["monto"],
            origen="anulacion",
            concepto=f"Anulación recibo {recibo['numero']}",
            movimiento_relacionado_id=movimiento["id"],
        )

    datos.marcar_estado_recibo(conexion, recibo_id, "anulado")
    conexion.commit()


def editar_forma_pago_recibo_pago(
    conexion: sqlite3.Connection,
    recibo_pago_id: int,
    fecha_hoy: str,
    forma_pago_id: int | None = None,
    monto: Decimal | None = None,
) -> None:
    """Corrige la forma de pago (y, si hace falta, el monto) de una línea
    de un recibo ya asentado — por ejemplo, si quedó cargada como
    "Efectivo" cuando en realidad era "Transferencia" y por eso no cierra
    la caja. No se puede pasar una línea a o desde "Cheque" con esta
    corrección: un cheque tiene datos propios (número, banco, fecha de
    cobro) que esto no junta — para eso hay que anular el recibo y
    volver a cargarlo. Si cambia la forma de pago o el monto, revierte el
    movimiento de caja original y postea el corregido, siempre en la
    caja de ``fecha_hoy`` (nunca en la del día original, que puede estar
    cerrada), igual que al anular un recibo."""
    recibo_pago = datos.obtener_recibo_pago(conexion, recibo_pago_id)
    if recibo_pago is None:
        raise ValueError(f"No existe la línea de pago {recibo_pago_id}.")

    recibo = datos.obtener_recibo(conexion, recibo_pago["recibo_id"])
    if recibo["estado"] != "vigente":
        raise ValueError(f"El recibo {recibo['numero']} está anulado: no se puede corregir.")

    forma_pago_nueva = forma_pago_id if forma_pago_id is not None else recibo_pago["forma_pago_id"]
    monto_nuevo = monto if monto is not None else recibo_pago["monto"]

    forma_vieja = datos_formas_pago.obtener_forma_pago(conexion, recibo_pago["forma_pago_id"])
    forma_nueva = datos_formas_pago.obtener_forma_pago(conexion, forma_pago_nueva)
    if forma_nueva is None:
        raise ValueError(f"No existe la forma de pago {forma_pago_nueva}.")
    if forma_vieja["tipo"] == "cheque" or forma_nueva["tipo"] == "cheque":
        raise ValueError(
            "No se puede cambiar una línea desde o hacia Cheque con esta corrección "
            "(un cheque tiene sus propios datos). Anulá el recibo y volvé a cargarlo."
        )

    cambia = forma_pago_nueva != recibo_pago["forma_pago_id"] or monto_nuevo != recibo_pago["monto"]
    if not cambia:
        return

    movimiento_nuevo_id = recibo_pago["movimiento_caja_id"]
    if recibo["origen"] == "manual":
        movimiento_original = None
        if recibo_pago["movimiento_caja_id"] is not None:
            movimiento_original = datos_caja.obtener_movimiento(
                conexion, recibo_pago["movimiento_caja_id"]
            )
        if movimiento_original is None:
            # Línea de un recibo cargado antes de que se empezara a guardar
            # este vínculo: se busca por concepto + forma + monto. Si el
            # recibo tiene más de una línea con la misma forma y el mismo
            # monto, puede no ser exactamente la correcta.
            concepto = f"Recibo {recibo['numero']}"
            candidatos = [
                movimiento
                for movimiento in datos_caja.listar_movimientos_por_concepto(conexion, concepto, "recibo")
                if movimiento["forma_pago_id"] == recibo_pago["forma_pago_id"]
                and movimiento["monto"] == recibo_pago["monto"]
            ]
            movimiento_original = candidatos[0] if candidatos else None
        if movimiento_original is None:
            raise ValueError(
                f"No se encontró el movimiento de caja de esta línea del recibo "
                f"{recibo['numero']}: no se puede corregir con seguridad."
            )

        datos_caja.insertar_movimiento(
            conexion,
            fecha_hora=fecha_hoy,
            tipo="egreso",
            forma_pago_id=movimiento_original["forma_pago_id"],
            monto=movimiento_original["monto"],
            origen="anulacion",
            concepto=f"Corrección recibo {recibo['numero']}: reversión del valor anterior",
            movimiento_relacionado_id=movimiento_original["id"],
        )
        movimiento_nuevo_id = datos_caja.insertar_movimiento(
            conexion,
            fecha_hora=fecha_hoy,
            tipo="ingreso",
            forma_pago_id=forma_pago_nueva,
            monto=monto_nuevo,
            origen="recibo",
            concepto=f"Recibo {recibo['numero']}",
            movimiento_relacionado_id=movimiento_original["id"],
        )

    datos.actualizar_recibo_pago(
        conexion,
        recibo_pago_id,
        {
            "forma_pago_id": forma_pago_nueva,
            "monto": monto_nuevo,
            "movimiento_caja_id": movimiento_nuevo_id,
        },
    )
    conexion.commit()
