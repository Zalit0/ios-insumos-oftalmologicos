"""Caja diaria (docs/PLAN.md, etapa 7).

Saldo inicial, saldo teórico, arqueo y diferencia se llevan por separado
para cada forma de pago. Un cierre congela los movimientos del día y no se
reabre; la corrección de un día cerrado (anular un recibo) genera su
contramovimiento en la caja del día actual, no en la cerrada.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from ios.data import caja as datos_caja
from ios.data import cierres_caja as datos_cierres

FORMATO_FECHA_LEN = 10  # 'YYYY-MM-DD'


def saldo_inicial_propuesto(conexion: sqlite3.Connection, forma_pago_id: int) -> Decimal:
    """Arqueo del último cierre para esa forma de pago, o 0 si no hay cierres."""
    detalle = datos_cierres.obtener_ultimo_detalle_de_forma(conexion, forma_pago_id)
    return detalle["arqueo"] if detalle is not None else Decimal(0)


def abrir_caja(conexion: sqlite3.Connection, fecha: str) -> int:
    if datos_cierres.obtener_cierre_por_fecha(conexion, fecha) is not None:
        raise ValueError(f"Ya hay una caja abierta o cerrada para el {fecha}.")

    cierre_id = datos_cierres.insertar_cierre(conexion, fecha)
    conexion.commit()
    return cierre_id


def ajustar_saldo_inicial(
    conexion: sqlite3.Connection,
    fecha_hora: str,
    forma_pago_id: int,
    saldo_real: Decimal,
    nota: str | None = None,
) -> int | None:
    """Si el saldo inicial propuesto se modifica, la diferencia queda como
    un movimiento de ajuste con nota obligatoria. Devuelve el id del
    movimiento creado, o None si no hubo diferencia."""
    propuesto = saldo_inicial_propuesto(conexion, forma_pago_id)
    diferencia = saldo_real - propuesto
    if diferencia == 0:
        return None
    if not nota or not nota.strip():
        raise ValueError("Ajustar el saldo inicial propuesto requiere una nota.")

    movimiento_id = datos_caja.insertar_movimiento(
        conexion,
        fecha_hora=fecha_hora,
        tipo="ingreso" if diferencia > 0 else "egreso",
        forma_pago_id=forma_pago_id,
        monto=abs(diferencia),
        origen="ajuste_saldo_inicial",
        concepto=nota,
    )
    conexion.commit()
    return movimiento_id


def registrar_movimiento_manual(
    conexion: sqlite3.Connection,
    fecha_hora: str,
    tipo: str,
    forma_pago_id: int,
    monto: Decimal,
    categoria_id: int | None = None,
    concepto: str | None = None,
) -> int:
    """Gastos, retiros y aportes: movimientos manuales de caja."""
    if tipo not in ("ingreso", "egreso"):
        raise ValueError(f"Tipo de movimiento inválido: {tipo}")

    movimiento_id = datos_caja.insertar_movimiento(
        conexion,
        fecha_hora=fecha_hora,
        tipo=tipo,
        forma_pago_id=forma_pago_id,
        monto=monto,
        origen="manual",
        concepto=concepto,
        categoria_id=categoria_id,
    )
    conexion.commit()
    return movimiento_id


def registrar_transferencia_interna(
    conexion: sqlite3.Connection,
    fecha_hora: str,
    forma_pago_origen_id: int,
    forma_pago_destino_id: int,
    monto: Decimal,
    concepto: str | None = None,
) -> tuple[int, int]:
    """Depositar efectivo en el banco, cobrar un cheque, etc.: egreso en una
    forma de pago e ingreso en otra por el mismo monto. No cambia el total
    disponible."""
    egreso_id = datos_caja.insertar_movimiento(
        conexion,
        fecha_hora=fecha_hora,
        tipo="egreso",
        forma_pago_id=forma_pago_origen_id,
        monto=monto,
        origen="transferencia_interna",
        concepto=concepto,
    )
    ingreso_id = datos_caja.insertar_movimiento(
        conexion,
        fecha_hora=fecha_hora,
        tipo="ingreso",
        forma_pago_id=forma_pago_destino_id,
        monto=monto,
        origen="transferencia_interna",
        concepto=concepto,
        movimiento_relacionado_id=egreso_id,
    )
    datos_caja.actualizar_movimiento_relacionado(conexion, egreso_id, ingreso_id)

    conexion.commit()
    return egreso_id, ingreso_id


def cerrar_caja(
    conexion: sqlite3.Connection,
    cierre_id: int,
    arqueos: dict[int, Decimal],
    nota: str | None = None,
) -> None:
    """Calcula saldo teórico y diferencia por forma de pago, y cierra el
    día. Si alguna forma de pago queda con diferencia distinta de cero,
    exige una nota."""
    cierre = datos_cierres.obtener_cierre(conexion, cierre_id)
    if cierre is None:
        raise ValueError(f"No existe el cierre {cierre_id}.")
    if cierre["estado"] != "abierto":
        raise ValueError(f"El cierre {cierre_id} ya está cerrado.")

    fecha = cierre["fecha"]
    datos_caja.asignar_cierre_a_movimientos_del_dia(conexion, cierre_id, fecha)

    formas_con_movimiento = set(
        datos_caja.listar_formas_de_pago_con_movimientos_del_dia(conexion, fecha)
    )
    formas_a_cerrar = formas_con_movimiento | set(arqueos.keys())

    hay_diferencia = False
    detalles = []
    for forma_pago_id in formas_a_cerrar:
        if forma_pago_id not in arqueos:
            raise ValueError(f"Falta el arqueo de la forma de pago {forma_pago_id}.")

        saldo_inicial = saldo_inicial_propuesto(conexion, forma_pago_id)
        ingresos = sum(
            (
                fila["monto"]
                for fila in datos_caja.listar_movimientos_de_cierre_y_forma(
                    conexion, cierre_id, forma_pago_id, "ingreso"
                )
            ),
            Decimal(0),
        )
        egresos = sum(
            (
                fila["monto"]
                for fila in datos_caja.listar_movimientos_de_cierre_y_forma(
                    conexion, cierre_id, forma_pago_id, "egreso"
                )
            ),
            Decimal(0),
        )
        saldo_teorico = saldo_inicial + ingresos - egresos
        arqueo = arqueos[forma_pago_id]
        diferencia = arqueo - saldo_teorico
        if diferencia != 0:
            hay_diferencia = True

        detalles.append(
            (forma_pago_id, saldo_inicial, ingresos, egresos, saldo_teorico, arqueo, diferencia)
        )

    if hay_diferencia and (not nota or not nota.strip()):
        raise ValueError("Hay diferencia en el cierre: falta la nota.")

    for forma_pago_id, saldo_inicial, ingresos, egresos, saldo_teorico, arqueo, diferencia in detalles:
        datos_cierres.insertar_detalle(
            conexion,
            cierre_id,
            forma_pago_id,
            saldo_inicial,
            ingresos,
            egresos,
            saldo_teorico,
            arqueo,
            diferencia,
        )

    datos_cierres.marcar_cierre_cerrado(conexion, cierre_id, nota)
    conexion.commit()


@dataclass
class FilaVistaPreviaCierre:
    forma_pago_id: int
    saldo_inicial: Decimal
    ingresos: Decimal
    egresos: Decimal
    saldo_teorico: Decimal


def vista_previa_cierre(conexion: sqlite3.Connection, fecha: str) -> list[FilaVistaPreviaCierre]:
    """Saldo teórico por forma de pago si se cerrara la caja de ``fecha``
    ahora mismo, antes de pedir el arqueo. Usa los movimientos del día que
    todavía no están asignados a ningún cierre."""
    totales: dict[int, dict[str, Decimal]] = {}
    for movimiento in datos_caja.listar_movimientos_del_dia(conexion, fecha):
        if movimiento["cierre_id"] is not None:
            continue
        fila = totales.setdefault(
            movimiento["forma_pago_id"], {"ingresos": Decimal(0), "egresos": Decimal(0)}
        )
        clave = "ingresos" if movimiento["tipo"] == "ingreso" else "egresos"
        fila[clave] += movimiento["monto"]

    filas = []
    for forma_pago_id, totales_forma in totales.items():
        saldo_inicial = saldo_inicial_propuesto(conexion, forma_pago_id)
        saldo_teorico = saldo_inicial + totales_forma["ingresos"] - totales_forma["egresos"]
        filas.append(FilaVistaPreviaCierre(
            forma_pago_id=forma_pago_id,
            saldo_inicial=saldo_inicial,
            ingresos=totales_forma["ingresos"],
            egresos=totales_forma["egresos"],
            saldo_teorico=saldo_teorico,
        ))
    return filas


def cerrar_cajas_vencidas(conexion: sqlite3.Connection, fecha_hoy: str) -> None:
    """Cierra solas, con el saldo teórico como arqueo (sin pedir nada), las
    cajas que quedaron abiertas de un día anterior a ``fecha_hoy``
    (docs/AJUSTES_V1.1.md, Caja obligatoria para cobrar: "cada caja se
    cierra automáticamente a las 00:00 del día siguiente")."""
    for cierre in datos_cierres.listar_cierres_abiertos_anteriores_a(conexion, fecha_hoy):
        arqueos = {
            fila.forma_pago_id: fila.saldo_teorico
            for fila in vista_previa_cierre(conexion, cierre["fecha"])
        }
        cerrar_caja(conexion, cierre["id"], arqueos, nota="Cierre automático al cambiar de día")


def hay_caja_abierta_hoy(conexion: sqlite3.Connection, fecha_hoy: str) -> bool:
    """Antes de chequear, cierra cualquier caja vieja que haya quedado
    abierta: así la caja de hoy nunca se confunde con una de un día
    anterior sin cerrar."""
    cerrar_cajas_vencidas(conexion, fecha_hoy)
    cierre = datos_cierres.obtener_cierre_por_fecha(conexion, fecha_hoy)
    return cierre is not None and cierre["estado"] == "abierto"


def total_disponible(conexion: sqlite3.Connection, formas_pago_ids: list[int]) -> Decimal:
    """Saldo del último cierre más los movimientos posteriores (todavía sin
    asignar a un cierre)."""
    total = sum(
        (saldo_inicial_propuesto(conexion, forma_pago_id) for forma_pago_id in formas_pago_ids),
        Decimal(0),
    )
    for movimiento in datos_caja.listar_movimientos_sin_cierre(conexion):
        if movimiento["tipo"] == "ingreso":
            total += movimiento["monto"]
        else:
            total -= movimiento["monto"]
    return total
