"""Indicadores del Dashboard directivo de IOS (docs/PLAN.md, etapa 8;
rediseño completo en docs/AJUSTES_V1.1.md): ventas y cobranzas del mes con
sus comparaciones temporales, deuda total, saldos por antigüedad, clientes
con más saldo, total disponible, estado de caja y actividad comercial.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ios.data import clientes as datos_clientes
from ios.data import cierres_caja as datos_cierres
from ios.data import comprobantes as datos_comprobantes
from ios.data import recibos as datos_recibos
from ios.data import resumen_mensual as datos_resumen_mensual
from ios.domain import periodos
from ios.services.compras import listar_compras
from ios.services.cuenta_corriente import estado_de_cuenta_cliente
from ios.services.resumen_mensual import resumen_del_mes

BUCKETS_ANTIGUEDAD = ((0, 30), (31, 60), (61, 90), (91, None))


def mes_anterior(mes: str) -> str:
    """``mes`` en formato 'YYYY-MM'."""
    anio, mes_numero = (int(parte) for parte in mes.split("-"))
    if mes_numero == 1:
        return f"{anio - 1}-12"
    return f"{anio}-{mes_numero - 1:02d}"


def deuda_total(conexion: sqlite3.Connection) -> Decimal:
    """Suma de los saldos consolidados positivos de todos los clientes
    activos (el saldo a favor de uno no compensa la deuda de otro)."""
    total = Decimal(0)
    for cliente in datos_clientes.listar_clientes(conexion):
        estado = estado_de_cuenta_cliente(conexion, cliente["id"])
        if estado.saldo_consolidado > 0:
            total += estado.saldo_consolidado
    return total


@dataclass
class ClienteConSaldo:
    cliente_id: int
    nombre: str
    saldo: Decimal


def top_clientes_por_saldo(
    conexion: sqlite3.Connection, cantidad: int = 10
) -> list[ClienteConSaldo]:
    clientes = []
    for cliente in datos_clientes.listar_clientes(conexion):
        estado = estado_de_cuenta_cliente(conexion, cliente["id"])
        clientes.append(
            ClienteConSaldo(
                cliente_id=cliente["id"], nombre=cliente["nombre"], saldo=estado.saldo_consolidado
            )
        )
    clientes.sort(key=lambda c: c.saldo, reverse=True)
    return clientes[:cantidad]


def venta_y_cobranza_mes_actual_vs_anterior(conexion: sqlite3.Connection, mes: str) -> dict:
    """Comparación equivalente a la hoja TOTALES (se mantiene para no
    romper el resumen mensual existente). El Dashboard usa en cambio
    :func:`comparacion_ventas` y :func:`comparacion_cobranzas`, con
    períodos de igual cantidad de días y fecha de cobranza = fecha del
    recibo."""
    actual = resumen_del_mes(conexion, mes)
    anterior = resumen_del_mes(conexion, mes_anterior(mes))
    return {
        "venta_mes_actual": actual.total_venta,
        "venta_mes_anterior": anterior.total_venta,
        "cobranza_mes_actual": actual.total_pagos,
        "cobranza_mes_anterior": anterior.total_pagos,
    }


def _bucket(dias: int) -> str:
    for desde, hasta in BUCKETS_ANTIGUEDAD:
        if hasta is None or dias <= hasta:
            if dias >= desde:
                etiqueta = f"{desde}-{hasta}" if hasta is not None else f"{desde}+"
                return etiqueta
    raise AssertionError(f"No hay bucket para {dias} días.")  # pragma: no cover


def saldos_por_antiguedad(
    conexion: sqlite3.Connection, fecha_referencia: str
) -> dict[str, Decimal]:
    """Saldo pendiente agrupado por antigüedad (en días, respecto de
    ``fecha_referencia`` 'YYYY-MM-DD') de los remitos vigentes.

    El saldo a favor de cada cliente se descuenta de sus propios remitos
    más viejos primero (orden cronológico), nunca de los de otro cliente
    —el mismo criterio que usa el saldo consolidado (:func:`deuda_total`,
    ``ios/domain/calculos.calcular_saldo_cliente``)— así el total de los
    rangos siempre coincide con la deuda total consolidada. Antes, esta
    función sumaba el saldo "bruto" de cada remito sin descontar el saldo
    a favor, lo que podía dar un total de rangos mayor que la deuda total
    cuando algún cliente tenía recibos sin aplicar (docs/AJUSTES_V1.1.md,
    rediseño del Dashboard: auditoría de consistencia)."""
    hoy = date.fromisoformat(fecha_referencia)
    totales = {_bucket(desde): Decimal(0) for desde, _ in BUCKETS_ANTIGUEDAD}

    for cliente in datos_clientes.listar_clientes(conexion):
        estado = estado_de_cuenta_cliente(conexion, cliente["id"])
        if estado.saldo_consolidado <= 0:
            # Cliente con saldo a favor neto: no tiene deuda que repartir
            # en los rangos (y su crédito no se usa para compensar a otro
            # cliente, igual que en deuda_total).
            continue

        comprobantes_con_saldo = sorted(
            (
                comprobante
                for sucursal in estado.sucursales
                for comprobante in sucursal.comprobantes
                if comprobante.saldo > 0
            ),
            key=lambda comprobante: comprobante.fecha,
        )

        credito_disponible = estado.saldo_a_favor
        for comprobante in comprobantes_con_saldo:
            saldo_neto = comprobante.saldo
            if credito_disponible > 0:
                usado = min(credito_disponible, saldo_neto)
                saldo_neto -= usado
                credito_disponible -= usado
            if saldo_neto <= 0:
                continue
            dias = (hoy - date.fromisoformat(comprobante.fecha)).days
            totales[_bucket(dias)] += saldo_neto

    return totales


def porcentaje_deuda_mayor_a_30_dias(antiguedad: dict[str, Decimal]) -> Decimal | None:
    """(deuda con más de 30 días / deuda total) × 100, o ``None`` si no
    hay deuda (no hay base válida para un porcentaje)."""
    total = sum(antiguedad.values(), Decimal(0))
    if total == 0:
        return None
    menor_a_30 = antiguedad.get("0-30", Decimal(0))
    return ((total - menor_a_30) / total) * Decimal(100)


def estado_de_caja_del_dia(conexion: sqlite3.Connection, fecha: str) -> dict:
    cierre = datos_cierres.obtener_cierre_por_fecha(conexion, fecha)
    if cierre is None:
        return {"abierta": False, "cerrada": False, "cierre_id": None}
    return {
        "abierta": cierre["estado"] == "abierto",
        "cerrada": cierre["estado"] == "cerrado",
        "cierre_id": cierre["id"],
    }


def total_ventas_entre(conexion: sqlite3.Connection, fecha_desde: str, fecha_hasta: str) -> Decimal:
    """Monto final de los remitos vigentes con fecha en el rango (excluye
    anulados)."""
    comprobantes = datos_comprobantes.listar_comprobantes(
        conexion, estado="vigente", fecha_desde=fecha_desde, fecha_hasta=fecha_hasta
    )
    return sum((c["monto_final"] for c in comprobantes), Decimal(0))


def total_cobranzas_entre(conexion: sqlite3.Connection, fecha_desde: str, fecha_hasta: str) -> Decimal:
    """Monto total de los recibos vigentes con fecha en el rango, por su
    propia fecha (no la del remito que cubren). Cada recibo ya suma sus
    distintas formas de pago una sola vez (``recibos.monto_total``), y
    aplicar saldo a favor a un remito no genera un recibo nuevo: no hay
    riesgo de contar dos veces ni de contar una aplicación como ingreso."""
    recibos = datos_recibos.listar_recibos_vigentes_entre(conexion, fecha_desde, fecha_hasta)
    return sum((r["monto_total"] for r in recibos), Decimal(0))


@dataclass
class ComparacionPeriodo:
    total_actual: Decimal
    periodo_actual: periodos.Periodo
    variacion_mensual: periodos.Variacion
    periodo_mensual_anterior: periodos.Periodo
    variacion_anual: periodos.Variacion
    periodo_anual_anterior: periodos.Periodo


def _comparacion_de_periodo(conexion, fecha_hoy: date, total_entre) -> ComparacionPeriodo:
    """Función centralizada para comparar el período transcurrido del mes
    contra el mismo rango de días del mes anterior y del año anterior
    (docs/AJUSTES_V1.1.md, rediseño del Dashboard): se usa tanto para
    ventas como para cobranzas, para no duplicar la lógica de fechas."""
    periodo_actual = periodos.periodo_mes_actual(fecha_hoy)
    periodo_mensual_anterior = periodos.periodo_mismo_rango_mes_anterior(fecha_hoy)
    periodo_anual_anterior = periodos.periodo_mismo_rango_anio_anterior(fecha_hoy)

    total_actual = total_entre(conexion, periodo_actual.desde, periodo_actual.hasta)
    total_mensual_anterior = total_entre(
        conexion, periodo_mensual_anterior.desde, periodo_mensual_anterior.hasta
    )
    total_anual_anterior = total_entre(
        conexion, periodo_anual_anterior.desde, periodo_anual_anterior.hasta
    )

    return ComparacionPeriodo(
        total_actual=total_actual,
        periodo_actual=periodo_actual,
        variacion_mensual=periodos.calcular_variacion(total_actual, total_mensual_anterior),
        periodo_mensual_anterior=periodo_mensual_anterior,
        variacion_anual=periodos.calcular_variacion(total_actual, total_anual_anterior),
        periodo_anual_anterior=periodo_anual_anterior,
    )


def comparacion_ventas(conexion: sqlite3.Connection, fecha_hoy: date) -> ComparacionPeriodo:
    return _comparacion_de_periodo(conexion, fecha_hoy, total_ventas_entre)


def comparacion_cobranzas(conexion: sqlite3.Connection, fecha_hoy: date) -> ComparacionPeriodo:
    return _comparacion_de_periodo(conexion, fecha_hoy, total_cobranzas_entre)


def total_remitos_cobrados_del_mes(conexion: sqlite3.Connection, mes: str) -> Decimal:
    """Cuánto de lo facturado en remitos de ``mes`` ('YYYY-MM') ya está
    cobrado a hoy, sin importar cuándo se cobró (el criterio por fecha
    del remito). Es el dato complementario de "Cobranzas del mes" —que
    usa la fecha del recibo, no la del remito— para que se entienda por
    qué pueden no coincidir: un recibo de este mes puede estar cobrando
    deuda vieja, y un remito de este mes puede cobrarse más adelante
    (docs/AJUSTES_V1.1.md, rediseño del Dashboard)."""
    montos = datos_resumen_mensual.montos_aplicados_a_comprobantes_del_mes(conexion, mes)
    return sum(montos, Decimal(0))


def deuda_de_lo_vendido_del_mes(conexion: sqlite3.Connection, mes: str) -> Decimal:
    """Lo que todavía falta cobrar de los remitos emitidos en ``mes``
    ('YYYY-MM'): venta del mes menos lo ya cobrado de esos mismos
    remitos (:func:`total_remitos_cobrados_del_mes`), sin importar
    cuándo se cobre (docs/AJUSTES_V1.1.md, rediseño del Dashboard).
    Es un corte distinto de :func:`deuda_total` (que es la deuda de
    todos los remitos vigentes, de cualquier mes)."""
    ventas = datos_comprobantes.listar_comprobantes(conexion, mes=mes, estado="vigente")
    total_ventas = sum((c["monto_final"] for c in ventas), Decimal(0))
    return total_ventas - total_remitos_cobrados_del_mes(conexion, mes)


@dataclass
class PuntoEvolucion:
    mes: str
    venta: Decimal
    cobranza: Decimal


def evolucion_ventas_cobranzas_12_meses(
    conexion: sqlite3.Connection, fecha_hoy: date
) -> list[PuntoEvolucion]:
    """Venta y cobranza de los últimos 12 meses completos. Trae los
    comprobantes y recibos del rango en una sola consulta cada uno (no
    doce), y agrupa por mes en Python."""
    meses = periodos.ultimos_n_meses(fecha_hoy, 12)
    desde, hasta = meses[0].desde, meses[-1].hasta

    ventas_por_mes: dict[str, Decimal] = {mes.mes: Decimal(0) for mes in meses}
    for comprobante in datos_comprobantes.listar_comprobantes(
        conexion, estado="vigente", fecha_desde=desde, fecha_hasta=hasta
    ):
        ventas_por_mes[comprobante["fecha"][:7]] += comprobante["monto_final"]

    cobranzas_por_mes: dict[str, Decimal] = {mes.mes: Decimal(0) for mes in meses}
    for recibo in datos_recibos.listar_recibos_vigentes_entre(conexion, desde, hasta):
        cobranzas_por_mes[recibo["fecha"][:7]] += recibo["monto_total"]

    return [
        PuntoEvolucion(mes=mes.mes, venta=ventas_por_mes[mes.mes], cobranza=cobranzas_por_mes[mes.mes])
        for mes in meses
    ]


@dataclass
class ActividadComercial:
    total_compras: Decimal
    clientes_activos: int
    remitos_emitidos: int


def actividad_comercial_del_mes(conexion: sqlite3.Connection, mes: str) -> ActividadComercial:
    """``mes`` en formato 'YYYY-MM'. Compras registradas, clientes con al
    menos un remito vigente (cada cliente cuenta una sola vez aunque tenga
    varias sucursales) y cantidad de remitos vigentes emitidos."""
    compras = listar_compras(conexion, mes=mes)
    total_compras = sum((c["monto"] for c in compras), Decimal(0))

    comprobantes = datos_comprobantes.listar_comprobantes(conexion, mes=mes, estado="vigente")
    clientes_activos = len({c["cliente_id"] for c in comprobantes})

    return ActividadComercial(
        total_compras=total_compras,
        clientes_activos=clientes_activos,
        remitos_emitidos=len(comprobantes),
    )
