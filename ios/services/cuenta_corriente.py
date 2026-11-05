"""Cuenta corriente de un cliente (docs/PLAN.md, etapa 5).

Movimientos y saldo agrupados por sucursal (caso Croma / Croma Fdez.), con
el saldo a favor y el total consolidado del cliente.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from ios.data import clientes as datos_clientes
from ios.data import comprobantes as datos_comprobantes
from ios.data import recibos as datos_recibos
from ios.domain.calculos import calcular_saldo_a_favor, calcular_saldo_cliente, calcular_saldo_comprobante


@dataclass
class SaldoComprobante:
    comprobante_id: int
    numero: str
    fecha: str
    monto_final: Decimal
    aplicado: Decimal
    saldo: Decimal


@dataclass
class EstadoCuentaSucursal:
    sucursal_id: int
    nombre: str
    comprobantes: list[SaldoComprobante]
    saldo: Decimal


@dataclass
class EstadoCuentaCliente:
    cliente_id: int
    sucursales: list[EstadoCuentaSucursal]
    saldo_comprobantes: Decimal
    saldo_a_favor: Decimal
    saldo_consolidado: Decimal


def estado_de_cuenta_cliente(conexion: sqlite3.Connection, cliente_id: int) -> EstadoCuentaCliente:
    if datos_clientes.obtener_cliente(conexion, cliente_id) is None:
        raise ValueError(f"No existe el cliente {cliente_id}.")

    sucursales_estado = []
    # Incluye sucursales desactivadas: pueden tener remitos históricos que
    # igual tienen que aparecer en el estado de cuenta (docs/AJUSTES_V1.1.md,
    # etapa 4).
    for sucursal in datos_clientes.listar_sucursales(conexion, cliente_id, incluir_inactivas=True):
        comprobantes = datos_comprobantes.listar_comprobantes(
            conexion, cliente_id=cliente_id, sucursal_id=sucursal["id"], estado="vigente"
        )

        saldos = []
        for comprobante in comprobantes:
            total_aplicado = datos_recibos.total_aplicado_a_comprobante(
                conexion, comprobante["id"]
            )
            saldo = calcular_saldo_comprobante(comprobante["monto_final"], total_aplicado)
            saldos.append(
                SaldoComprobante(
                    comprobante_id=comprobante["id"],
                    numero=comprobante["numero"],
                    fecha=comprobante["fecha"],
                    monto_final=comprobante["monto_final"],
                    aplicado=total_aplicado,
                    saldo=saldo,
                )
            )

        saldo_sucursal = sum((s.saldo for s in saldos), Decimal(0))
        sucursales_estado.append(
            EstadoCuentaSucursal(
                sucursal_id=sucursal["id"],
                nombre=sucursal["nombre"],
                comprobantes=saldos,
                saldo=saldo_sucursal,
            )
        )

    saldo_comprobantes = sum((s.saldo for s in sucursales_estado), Decimal(0))

    total_recibos = datos_recibos.total_monto_recibos_vigentes_cliente(conexion, cliente_id)
    total_aplicado_cliente = datos_recibos.total_aplicado_de_recibos_cliente(conexion, cliente_id)
    saldo_a_favor = calcular_saldo_a_favor(total_recibos, total_aplicado_cliente)

    saldo_consolidado = calcular_saldo_cliente(
        (s.saldo for s in sucursales_estado), saldo_a_favor
    )

    return EstadoCuentaCliente(
        cliente_id=cliente_id,
        sucursales=sucursales_estado,
        saldo_comprobantes=saldo_comprobantes,
        saldo_a_favor=saldo_a_favor,
        saldo_consolidado=saldo_consolidado,
    )


def estado_de_cuenta_solo_pendientes(
    conexion: sqlite3.Connection,
    cliente_id: int,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> EstadoCuentaCliente:
    """La misma información que :func:`estado_de_cuenta_cliente`, pero
    con cada sucursal filtrada a solo los comprobantes con saldo
    pendiente (> 0) a hoy: el modo de reporte pensado para gestionar
    cobranzas, que no mezcla los comprobantes ya cancelados
    (docs/AJUSTES_V1.1.md, rediseño del estado de cuenta). Si se indica
    ``fecha_desde``/``fecha_hasta``, además se filtra por la fecha de
    emisión del comprobante: solo entran los del período elegido, y el
    saldo de la sucursal y el consolidado pasan a ser la suma de lo
    efectivamente listado (no el total histórico). Sin esos parámetros,
    el comportamiento es el de siempre: todo lo pendiente a hoy, y el
    saldo es el total real del cliente."""
    estado = estado_de_cuenta_cliente(conexion, cliente_id)
    sucursales_pendientes = [
        EstadoCuentaSucursal(
            sucursal_id=sucursal.sucursal_id,
            nombre=sucursal.nombre,
            comprobantes=[
                c for c in sucursal.comprobantes
                if c.saldo > 0
                and (fecha_desde is None or c.fecha >= fecha_desde)
                and (fecha_hasta is None or c.fecha <= fecha_hasta)
            ],
            saldo=sucursal.saldo,
        )
        for sucursal in estado.sucursales
    ]

    if fecha_desde is None and fecha_hasta is None:
        saldo_comprobantes = estado.saldo_comprobantes
        saldo_consolidado = estado.saldo_consolidado
    else:
        for sucursal in sucursales_pendientes:
            sucursal.saldo = sum((c.saldo for c in sucursal.comprobantes), Decimal(0))
        saldo_comprobantes = sum((s.saldo for s in sucursales_pendientes), Decimal(0))
        saldo_consolidado = calcular_saldo_cliente(
            (s.saldo for s in sucursales_pendientes), estado.saldo_a_favor
        )

    return EstadoCuentaCliente(
        cliente_id=estado.cliente_id,
        sucursales=sucursales_pendientes,
        saldo_comprobantes=saldo_comprobantes,
        saldo_a_favor=estado.saldo_a_favor,
        saldo_consolidado=saldo_consolidado,
    )


@dataclass
class MovimientoRemito:
    comprobante_id: int
    numero: str
    fecha: str
    monto_final: Decimal
    aplicado: Decimal
    saldo: Decimal


@dataclass
class SucursalPeriodo:
    sucursal_id: int
    nombre: str
    saldo_anterior: Decimal
    movimientos: list[MovimientoRemito]
    saldo_cierre: Decimal
    saldo_del_periodo: Decimal


@dataclass
class AplicacionDetalle:
    comprobante_id: int
    comprobante_numero: str
    comprobante_fecha: str | None  # fecha de emisión del remito cancelado; None si ya no existe
    monto: Decimal


def _detalle_aplicaciones_de_recibo(
    conexion: sqlite3.Connection, recibo_id: int
) -> tuple[list[AplicacionDetalle], Decimal]:
    """A qué comprobantes aplicó este recibo (número, fecha de emisión y
    monto de cada aplicación) y cuánto quedó sin aplicar (saldo a favor
    que generó), leyendo solo ``aplicaciones_pago`` — no inventa
    relaciones de imputación (docs/AJUSTES_V1.1.md, rediseño del estado
    de cuenta). La fecha del comprobante deja ver si un pago del
    período en realidad cancela un comprobante de otro período."""
    aplicaciones = []
    aplicado_total = Decimal(0)
    for aplicacion in datos_recibos.listar_aplicaciones_de_recibo(conexion, recibo_id):
        comprobante = datos_comprobantes.obtener_comprobante(conexion, aplicacion["comprobante_id"])
        aplicado_total += aplicacion["monto_aplicado"]
        aplicaciones.append(AplicacionDetalle(
            comprobante_id=aplicacion["comprobante_id"],
            comprobante_numero=comprobante["numero"] if comprobante is not None else "?",
            comprobante_fecha=comprobante["fecha"] if comprobante is not None else None,
            monto=aplicacion["monto_aplicado"],
        ))
    return aplicaciones, aplicado_total


@dataclass
class ReciboPeriodo:
    recibo_id: int
    numero: int
    fecha: str
    monto_total: Decimal
    aplicaciones: list[AplicacionDetalle]
    sin_aplicar: Decimal


@dataclass
class DesglosePagosDelPeriodo:
    """De los recibos del período (por su propia fecha), a qué se aplicó
    cada peso: no se puede asumir que un recibo del período cancela un
    comprobante del mismo período (docs/AJUSTES_V1.1.md, rediseño del
    estado de cuenta). ``total_recibido`` siempre es la suma exacta de
    los otros cuatro campos."""
    total_recibido: Decimal
    aplicado_a_comprobantes_del_periodo: Decimal
    aplicado_a_comprobantes_de_otros_periodos: Decimal
    aplicado_a_comprobantes_anulados: Decimal
    sin_aplicar: Decimal


@dataclass
class EstadoCuentaPeriodo:
    cliente_id: int
    fecha_desde: str
    fecha_hasta: str
    sucursales: list[SucursalPeriodo]
    saldo_a_favor_anterior: Decimal
    recibos_del_periodo: list[ReciboPeriodo]
    saldo_a_favor_cierre: Decimal
    saldo_consolidado_anterior: Decimal
    saldo_consolidado_cierre: Decimal
    saldo_consolidado_del_periodo: Decimal
    total_comprobantes_emitidos: Decimal
    desglose_pagos: DesglosePagosDelPeriodo


def _saldo_remitos(
    conexion: sqlite3.Connection,
    cliente_id: int,
    sucursal_id: int,
    fecha_hasta: str | None = None,
    excluir_desde: str | None = None,
) -> Decimal:
    """Saldo de hoy (sin importar cuándo se cobró) de los remitos de esa
    sucursal, filtrados por su fecha de emisión: hasta ``fecha_hasta``
    inclusive si se da, y antes de ``excluir_desde`` (exclusive) si se da.
    El saldo de un remito ya pagado siempre da $0, sin importar la fecha
    del pago (docs/AJUSTES_V1.1.md, Cuenta corriente: el saldo de un
    período siempre refleja lo pagado a hoy)."""
    comprobantes = datos_comprobantes.listar_comprobantes(
        conexion, cliente_id=cliente_id, sucursal_id=sucursal_id, estado="vigente",
        fecha_hasta=fecha_hasta,
    )
    saldos = (
        calcular_saldo_comprobante(
            comprobante["monto_final"],
            datos_recibos.total_aplicado_a_comprobante(conexion, comprobante["id"]),
        )
        for comprobante in comprobantes
        if excluir_desde is None or comprobante["fecha"] < excluir_desde
    )
    return sum(saldos, Decimal(0))


def _saldo_a_favor(
    conexion: sqlite3.Connection,
    cliente_id: int,
    fecha_hasta: str | None = None,
    excluir_desde: str | None = None,
) -> Decimal:
    """Saldo a favor de hoy de los recibos filtrados por su propia fecha
    (misma idea que :func:`_saldo_remitos`): lo que cada uno vale menos lo
    que ya tiene aplicado a hoy, sin importar cuándo se aplicó."""
    recibos = datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente_id)
    disponibles = (
        recibo["monto_total"] - datos_recibos.total_aplicado_de_recibo(conexion, recibo["id"])
        for recibo in recibos
        if (fecha_hasta is None or recibo["fecha"] <= fecha_hasta)
        and (excluir_desde is None or recibo["fecha"] < excluir_desde)
    )
    return sum(disponibles, Decimal(0))


def desglose_pagos_del_periodo(
    conexion: sqlite3.Connection, cliente_id: int, fecha_desde: str, fecha_hasta: str
) -> DesglosePagosDelPeriodo:
    """De los recibos con fecha en el período, cuánto de lo cobrado se
    aplicó a comprobantes del propio período, cuánto a comprobantes de
    otro período (deuda vieja, o un adelanto), cuánto quedó atado a un
    comprobante que después se anuló, y cuánto no se aplicó a nada
    (saldo a favor). No asume que la fecha del recibo coincide con la
    del comprobante que cancela, y no modifica ningún registro
    (docs/AJUSTES_V1.1.md, rediseño del estado de cuenta)."""
    total_recibido = Decimal(0)
    del_periodo = Decimal(0)
    otros_periodos = Decimal(0)
    anulados = Decimal(0)
    sin_aplicar = Decimal(0)

    for recibo in datos_recibos.listar_recibos_cliente_entre(conexion, cliente_id, fecha_desde, fecha_hasta):
        total_recibido += recibo["monto_total"]
        aplicado_de_este_recibo = Decimal(0)
        for aplicacion in datos_recibos.listar_aplicaciones_de_recibo(conexion, recibo["id"]):
            monto = aplicacion["monto_aplicado"]
            aplicado_de_este_recibo += monto
            comprobante = datos_comprobantes.obtener_comprobante(conexion, aplicacion["comprobante_id"])
            if comprobante is None or comprobante["estado"] != "vigente":
                anulados += monto
            elif fecha_desde <= comprobante["fecha"] <= fecha_hasta:
                del_periodo += monto
            else:
                otros_periodos += monto
        sin_aplicar += recibo["monto_total"] - aplicado_de_este_recibo

    return DesglosePagosDelPeriodo(
        total_recibido=total_recibido,
        aplicado_a_comprobantes_del_periodo=del_periodo,
        aplicado_a_comprobantes_de_otros_periodos=otros_periodos,
        aplicado_a_comprobantes_anulados=anulados,
        sin_aplicar=sin_aplicar,
    )


def estado_de_cuenta_periodo(
    conexion: sqlite3.Connection, cliente_id: int, fecha_desde: str, fecha_hasta: str
) -> EstadoCuentaPeriodo:
    """Estado de cuenta de un período, con el saldo pendiente de antes del
    período arrastrado como "saldo anterior". El saldo (anterior, de cada
    remito del período, y al cierre) siempre es el de hoy: un remito ya
    cobrado nunca vuelve a figurar como saldo, sin importar cuándo se
    cobró — las fechas del período solo deciden qué remitos/recibos entran
    en cada grupo, no qué pagos cuentan (docs/AJUSTES_V1.1.md, Cuenta
    corriente: el saldo de un período siempre refleja lo pagado a hoy)."""
    if datos_clientes.obtener_cliente(conexion, cliente_id) is None:
        raise ValueError(f"No existe el cliente {cliente_id}.")

    sucursales_periodo = []
    for sucursal in datos_clientes.listar_sucursales(conexion, cliente_id, incluir_inactivas=True):
        saldo_anterior = _saldo_remitos(
            conexion, cliente_id, sucursal["id"], excluir_desde=fecha_desde
        )
        saldo_cierre = _saldo_remitos(conexion, cliente_id, sucursal["id"], fecha_hasta=fecha_hasta)

        remitos_del_periodo = datos_comprobantes.listar_comprobantes(
            conexion, cliente_id=cliente_id, sucursal_id=sucursal["id"], estado="vigente",
            fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        )
        movimientos = []
        for remito in remitos_del_periodo:
            aplicado = datos_recibos.total_aplicado_a_comprobante(conexion, remito["id"])
            movimientos.append(MovimientoRemito(
                comprobante_id=remito["id"],
                numero=remito["numero"],
                fecha=remito["fecha"],
                monto_final=remito["monto_final"],
                aplicado=aplicado,
                saldo=calcular_saldo_comprobante(remito["monto_final"], aplicado),
            ))

        sucursales_periodo.append(
            SucursalPeriodo(
                sucursal_id=sucursal["id"],
                nombre=sucursal["nombre"],
                saldo_anterior=saldo_anterior,
                movimientos=movimientos,
                saldo_cierre=saldo_cierre,
                saldo_del_periodo=saldo_cierre - saldo_anterior,
            )
        )

    saldo_a_favor_anterior = _saldo_a_favor(conexion, cliente_id, excluir_desde=fecha_desde)
    saldo_a_favor_cierre = _saldo_a_favor(conexion, cliente_id, fecha_hasta=fecha_hasta)

    recibos_del_periodo = []
    for recibo in datos_recibos.listar_recibos_cliente_entre(conexion, cliente_id, fecha_desde, fecha_hasta):
        aplicaciones, aplicado_total = _detalle_aplicaciones_de_recibo(conexion, recibo["id"])
        recibos_del_periodo.append(ReciboPeriodo(
            recibo_id=recibo["id"],
            numero=recibo["numero"],
            fecha=recibo["fecha"],
            monto_total=recibo["monto_total"],
            aplicaciones=aplicaciones,
            sin_aplicar=recibo["monto_total"] - aplicado_total,
        ))

    saldo_consolidado_anterior = calcular_saldo_cliente(
        (s.saldo_anterior for s in sucursales_periodo), saldo_a_favor_anterior
    )
    saldo_consolidado_cierre = calcular_saldo_cliente(
        (s.saldo_cierre for s in sucursales_periodo), saldo_a_favor_cierre
    )

    total_comprobantes_emitidos = sum(
        (m.monto_final for s in sucursales_periodo for m in s.movimientos), Decimal(0)
    )

    return EstadoCuentaPeriodo(
        cliente_id=cliente_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        sucursales=sucursales_periodo,
        saldo_a_favor_anterior=saldo_a_favor_anterior,
        recibos_del_periodo=recibos_del_periodo,
        saldo_a_favor_cierre=saldo_a_favor_cierre,
        saldo_consolidado_anterior=saldo_consolidado_anterior,
        saldo_consolidado_cierre=saldo_consolidado_cierre,
        saldo_consolidado_del_periodo=saldo_consolidado_cierre - saldo_consolidado_anterior,
        total_comprobantes_emitidos=total_comprobantes_emitidos,
        desglose_pagos=desglose_pagos_del_periodo(conexion, cliente_id, fecha_desde, fecha_hasta),
    )


@dataclass
class MovimientoHistorial:
    fecha: str
    tipo: str  # "remito" o "recibo"
    numero: str
    sucursal_nombre: str | None  # None para un recibo (no es de una sucursal en particular)
    monto: Decimal
    saldo: Decimal | None  # saldo a hoy; solo para un remito
    aplicaciones: list[AplicacionDetalle]  # a qué remitos aplicó; solo para un recibo
    sin_aplicar: Decimal | None  # saldo a favor que generó; solo para un recibo


@dataclass
class HistorialCliente:
    cliente_id: int
    fecha_desde: str
    fecha_hasta: str
    movimientos: list[MovimientoHistorial]
    saldo_a_favor_cierre: Decimal
    saldo_consolidado_cierre: Decimal


def historial_de_movimientos(
    conexion: sqlite3.Connection, cliente_id: int, fecha_desde: str, fecha_hasta: str
) -> HistorialCliente:
    """Remitos y recibos del período mezclados en una sola línea de
    tiempo (en vez de dos tablas separadas), con el detalle de a qué
    remito aplicó cada recibo: para auditar la cuenta sin tener que
    asumir que la fecha del recibo coincide con la del remito que
    cancela (docs/AJUSTES_V1.1.md, rediseño del estado de cuenta). No
    inventa relaciones de imputación: solo lee ``aplicaciones_pago``."""
    if datos_clientes.obtener_cliente(conexion, cliente_id) is None:
        raise ValueError(f"No existe el cliente {cliente_id}.")

    movimientos: list[MovimientoHistorial] = []

    for sucursal in datos_clientes.listar_sucursales(conexion, cliente_id, incluir_inactivas=True):
        remitos = datos_comprobantes.listar_comprobantes(
            conexion, cliente_id=cliente_id, sucursal_id=sucursal["id"], estado="vigente",
            fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        )
        for remito in remitos:
            aplicado = datos_recibos.total_aplicado_a_comprobante(conexion, remito["id"])
            movimientos.append(MovimientoHistorial(
                fecha=remito["fecha"],
                tipo="remito",
                numero=remito["numero"],
                sucursal_nombre=sucursal["nombre"],
                monto=remito["monto_final"],
                saldo=calcular_saldo_comprobante(remito["monto_final"], aplicado),
                aplicaciones=[],
                sin_aplicar=None,
            ))

    for recibo in datos_recibos.listar_recibos_cliente_entre(conexion, cliente_id, fecha_desde, fecha_hasta):
        aplicaciones, aplicado_total = _detalle_aplicaciones_de_recibo(conexion, recibo["id"])
        movimientos.append(MovimientoHistorial(
            fecha=recibo["fecha"],
            tipo="recibo",
            numero=str(recibo["numero"]),
            sucursal_nombre=None,
            monto=recibo["monto_total"],
            saldo=None,
            aplicaciones=aplicaciones,
            sin_aplicar=recibo["monto_total"] - aplicado_total,
        ))

    movimientos.sort(key=lambda m: (m.fecha, m.tipo, m.numero))

    estado_cliente = estado_de_cuenta_cliente(conexion, cliente_id)

    return HistorialCliente(
        cliente_id=cliente_id,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        movimientos=movimientos,
        saldo_a_favor_cierre=estado_cliente.saldo_a_favor,
        saldo_consolidado_cierre=estado_cliente.saldo_consolidado,
    )
