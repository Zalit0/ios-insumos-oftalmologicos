"""PDF del estado de cuenta corriente, en tres modalidades
(docs/AJUSTES_V1.1.md, rediseño del estado de cuenta corriente):

- "Completo del período": saldo anterior, remitos y recibos del
  período, y saldo al cierre — para enviar al cliente.
- "Solo comprobantes con saldo pendiente" (la modalidad por defecto
  para gestionar cobranzas): únicamente los remitos que todavía deben
  algo a hoy, con el total de pagos ya imputados a cada uno.
- "Historial completo de movimientos": remitos y recibos del período
  mezclados en una sola línea de tiempo, con el detalle de a qué
  remito aplicó cada recibo, para no tener que asumir que la fecha del
  recibo coincide con la del remito que cancela.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer

from ios.data import clientes as datos_clientes
from ios.reports.formato import formato_fecha, formato_moneda
from ios.reports.pdf_comun import ESTILO_NORMAL, ESTILO_SUBTITULO, encabezado, generar_pdf, tabla
from ios.services.cuenta_corriente import (
    estado_de_cuenta_cliente,
    estado_de_cuenta_periodo,
    estado_de_cuenta_solo_pendientes,
    historial_de_movimientos,
)

ESTILO_PIE = ESTILO_NORMAL


def _mes_anio(fecha: str | None) -> str:
    """``fecha`` en 'YYYY-MM-DD' → 'MM/YYYY', para ubicar de qué período
    es un comprobante sin mostrar la fecha completa."""
    if fecha is None:
        return "?"
    anio, mes, _ = fecha.split("-")
    return f"{mes}/{anio}"


def _detalle_aplicaciones_recibo(recibo) -> str:
    """Texto de a qué remitos canceló este recibo (ya sean de este
    período o de otro, con su mes/año para que se note), para que quede
    claro sin tener que cruzarlo a mano con la tabla de remitos."""
    partes = [
        f"Remito {a.comprobante_numero} ({_mes_anio(a.comprobante_fecha)} — {formato_moneda(a.monto)})"
        for a in recibo.aplicaciones
    ]
    if recibo.sin_aplicar and recibo.sin_aplicar > 0:
        partes.append(f"saldo a favor ({formato_moneda(recibo.sin_aplicar)})")
    return ", ".join(partes) if partes else "Sin aplicar (saldo a favor)"


def _pie_de_pagina() -> list:
    return [
        Spacer(1, 4 * mm),
        Paragraph(
            f"Estado de cuenta generado el {formato_fecha(date.today())}. Los saldos reflejan los "
            "pagos aplicados hasta esta fecha, no una foto fija del período.",
            ESTILO_PIE,
        ),
    ]


def generar_pdf_estado_cuenta(
    conexion: sqlite3.Connection, cliente_id: int, ruta_salida: Path | str
) -> Path:
    """Estado de cuenta a hoy, con todos los comprobantes vigentes
    (pagados o no). Para el reporte pensado para gestionar cobranzas,
    ver :func:`generar_pdf_estado_cuenta_pendientes`."""
    cliente = datos_clientes.obtener_cliente(conexion, cliente_id)
    if cliente is None:
        raise ValueError(f"No existe el cliente {cliente_id}.")
    estado = estado_de_cuenta_cliente(conexion, cliente_id)

    elementos = encabezado("Estado de cuenta", cliente["nombre"])

    for sucursal in estado.sucursales:
        elementos.append(Paragraph(sucursal.nombre, ESTILO_SUBTITULO))
        elementos.append(Spacer(1, 1 * mm))
        if sucursal.comprobantes:
            filas = [
                [c.numero, formato_fecha(c.fecha), formato_moneda(c.monto_final),
                 formato_moneda(c.aplicado), formato_moneda(c.saldo)]
                for c in sucursal.comprobantes
            ]
            elementos.append(tabla(
                ["Remito", "Fecha emisión", "Importe original", "Pagos imputados", "Saldo"], filas,
                anchos=[25 * mm, 28 * mm, 30 * mm, 30 * mm, 27 * mm],
                alinear_derecha=[2, 3, 4],
            ))
        else:
            elementos.append(Paragraph("Sin remitos vigentes.", ESTILO_NORMAL))
        elementos.append(Spacer(1, 2 * mm))
        elementos.append(Paragraph(
            f"<b>Saldo {sucursal.nombre}: {formato_moneda(sucursal.saldo)}</b>", ESTILO_NORMAL
        ))
        elementos.append(Spacer(1, 6 * mm))

    elementos.append(Paragraph(
        f"Saldo de remitos (todas las sucursales): {formato_moneda(estado.saldo_comprobantes)}",
        ESTILO_NORMAL,
    ))
    elementos.append(Paragraph(f"Saldo a favor: {formato_moneda(estado.saldo_a_favor)}", ESTILO_NORMAL))
    elementos.append(Spacer(1, 2 * mm))
    elementos.append(Paragraph(
        f"<b>Saldo consolidado: {formato_moneda(estado.saldo_consolidado)}</b>", ESTILO_NORMAL
    ))
    elementos.extend(_pie_de_pagina())

    return generar_pdf(ruta_salida, elementos)


def generar_pdf_estado_cuenta_pendientes(
    conexion: sqlite3.Connection,
    cliente_id: int,
    ruta_salida: Path | str,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> Path:
    """Modalidad "Solo comprobantes con saldo pendiente": la
    predeterminada para gestionar cobranzas. Solo lista, por sucursal,
    los remitos que todavía deben algo a hoy — número, fecha de
    emisión, importe original, pagos ya imputados y saldo pendiente —
    sin mezclarlos con los ya cancelados. Si se indica
    ``fecha_desde``/``fecha_hasta``, se limita a los comprobantes
    emitidos en ese período (y el saldo mostrado es la suma de esos,
    no el total histórico del cliente)."""
    cliente = datos_clientes.obtener_cliente(conexion, cliente_id)
    if cliente is None:
        raise ValueError(f"No existe el cliente {cliente_id}.")
    estado = estado_de_cuenta_solo_pendientes(conexion, cliente_id, fecha_desde, fecha_hasta)

    if fecha_desde is not None and fecha_hasta is not None:
        subtitulo = (
            f"{cliente['nombre']} — comprobantes pendientes del "
            f"{formato_fecha(fecha_desde)} al {formato_fecha(fecha_hasta)}"
        )
    else:
        subtitulo = f"{cliente['nombre']} — comprobantes pendientes al {formato_fecha(date.today())}"
    elementos = encabezado("Estado de cuenta — Solo pendientes", subtitulo)

    total_comprobantes_pendientes = 0
    for sucursal in estado.sucursales:
        elementos.append(Paragraph(sucursal.nombre, ESTILO_SUBTITULO))
        elementos.append(Spacer(1, 1 * mm))
        if sucursal.comprobantes:
            total_comprobantes_pendientes += len(sucursal.comprobantes)
            filas = [
                [c.numero, formato_fecha(c.fecha), formato_moneda(c.monto_final),
                 formato_moneda(c.aplicado), formato_moneda(c.saldo)]
                for c in sucursal.comprobantes
            ]
            elementos.append(tabla(
                ["Remito", "Fecha emisión", "Importe original", "Pagos imputados", "Saldo pendiente"],
                filas, anchos=[25 * mm, 28 * mm, 30 * mm, 30 * mm, 27 * mm],
                alinear_derecha=[2, 3, 4],
            ))
        else:
            elementos.append(Paragraph("Sin comprobantes pendientes en esta sucursal.", ESTILO_NORMAL))
        elementos.append(Spacer(1, 2 * mm))
        elementos.append(Paragraph(
            f"<b>Saldo pendiente {sucursal.nombre}: {formato_moneda(sucursal.saldo)}</b>", ESTILO_NORMAL
        ))
        elementos.append(Spacer(1, 6 * mm))

    elementos.append(Paragraph(
        f"Comprobantes pendientes: {total_comprobantes_pendientes}", ESTILO_NORMAL
    ))
    elementos.append(Paragraph(f"Saldo a favor: {formato_moneda(estado.saldo_a_favor)}", ESTILO_NORMAL))
    elementos.append(Spacer(1, 2 * mm))
    elementos.append(Paragraph(
        f"<b>Saldo consolidado: {formato_moneda(estado.saldo_consolidado)}</b>", ESTILO_NORMAL
    ))
    elementos.extend(_pie_de_pagina())

    return generar_pdf(ruta_salida, elementos)


def generar_pdf_estado_cuenta_periodo(
    conexion: sqlite3.Connection,
    cliente_id: int,
    fecha_desde: str,
    fecha_hasta: str,
    ruta_salida: Path | str,
) -> Path:
    """Modalidad "Completo del período": saldo anterior, movimientos
    (remitos) y recibos del período, y saldo al cierre, con el
    desglose de a qué comprobantes se aplicaron los pagos del período
    —propios o de otro período— para que no se confundan
    (docs/AJUSTES_V1.1.md, rediseño del estado de cuenta corriente)."""
    cliente = datos_clientes.obtener_cliente(conexion, cliente_id)
    if cliente is None:
        raise ValueError(f"No existe el cliente {cliente_id}.")
    estado = estado_de_cuenta_periodo(conexion, cliente_id, fecha_desde, fecha_hasta)

    subtitulo = f"{cliente['nombre']} — {formato_fecha(fecha_desde)} a {formato_fecha(fecha_hasta)}"
    elementos = encabezado("Estado de cuenta — Completo del período", subtitulo)

    for sucursal in estado.sucursales:
        elementos.append(Paragraph(sucursal.nombre, ESTILO_SUBTITULO))
        elementos.append(Spacer(1, 1 * mm))
        elementos.append(Paragraph(
            f"Saldo anterior: {formato_moneda(sucursal.saldo_anterior)}", ESTILO_NORMAL
        ))
        elementos.append(Spacer(1, 1 * mm))
        if sucursal.movimientos:
            filas = [
                [m.numero, formato_fecha(m.fecha), formato_moneda(m.monto_final),
                 formato_moneda(m.aplicado), formato_moneda(m.saldo)]
                for m in sucursal.movimientos
            ]
            elementos.append(tabla(
                ["Remito", "Fecha emisión", "Importe original", "Pagos imputados", "Saldo"], filas,
                anchos=[25 * mm, 28 * mm, 30 * mm, 30 * mm, 27 * mm],
                alinear_derecha=[2, 3, 4],
            ))
        else:
            elementos.append(Paragraph("Sin remitos en el período.", ESTILO_NORMAL))
        elementos.append(Spacer(1, 2 * mm))
        elementos.append(Paragraph(
            f"Saldo del período {sucursal.nombre}: {formato_moneda(sucursal.saldo_del_periodo)}",
            ESTILO_NORMAL,
        ))
        elementos.append(Paragraph(
            f"<b>Saldo al cierre {sucursal.nombre}: {formato_moneda(sucursal.saldo_cierre)}</b>",
            ESTILO_NORMAL,
        ))
        elementos.append(Spacer(1, 6 * mm))

    elementos.append(Paragraph("Recibos del período (fecha de cobro)", ESTILO_SUBTITULO))
    elementos.append(Spacer(1, 1 * mm))
    elementos.append(Paragraph(
        f"Saldo a favor anterior: {formato_moneda(estado.saldo_a_favor_anterior)}", ESTILO_NORMAL
    ))
    if estado.recibos_del_periodo:
        filas = [
            [str(r.numero), formato_fecha(r.fecha), formato_moneda(r.monto_total),
             _detalle_aplicaciones_recibo(r)]
            for r in estado.recibos_del_periodo
        ]
        elementos.append(tabla(
            ["Recibo", "Fecha de cobro", "Monto", "Qué remitos cancela"], filas,
            anchos=[22 * mm, 28 * mm, 28 * mm, 67 * mm],
            alinear_derecha=[2],
        ))
    else:
        elementos.append(Paragraph("Sin recibos en el período.", ESTILO_NORMAL))
    elementos.append(Paragraph(
        f"Saldo a favor al cierre: {formato_moneda(estado.saldo_a_favor_cierre)}", ESTILO_NORMAL
    ))
    elementos.append(Spacer(1, 4 * mm))

    desglose = estado.desglose_pagos
    elementos.append(Paragraph("Resumen del período", ESTILO_SUBTITULO))
    elementos.append(Spacer(1, 1 * mm))
    elementos.append(Paragraph(
        f"Total de comprobantes emitidos en el período: {formato_moneda(estado.total_comprobantes_emitidos)}",
        ESTILO_NORMAL,
    ))
    elementos.append(Paragraph(
        f"Total de pagos recibidos en el período: {formato_moneda(desglose.total_recibido)}",
        ESTILO_NORMAL,
    ))
    aplicado_total = (
        desglose.aplicado_a_comprobantes_del_periodo
        + desglose.aplicado_a_comprobantes_de_otros_periodos
        + desglose.aplicado_a_comprobantes_anulados
    )
    elementos.append(Paragraph(
        f"Total de pagos aplicados a comprobantes: {formato_moneda(aplicado_total)}",
        ESTILO_NORMAL,
    ))
    elementos.append(Paragraph(
        f"&nbsp;&nbsp;— aplicados a comprobantes de este mismo período: "
        f"{formato_moneda(desglose.aplicado_a_comprobantes_del_periodo)}",
        ESTILO_NORMAL,
    ))
    elementos.append(Paragraph(
        f"&nbsp;&nbsp;— aplicados a comprobantes de otro período (deuda anterior, o un adelanto): "
        f"{formato_moneda(desglose.aplicado_a_comprobantes_de_otros_periodos)}",
        ESTILO_NORMAL,
    ))
    if desglose.aplicado_a_comprobantes_anulados:
        elementos.append(Paragraph(
            f"&nbsp;&nbsp;— aplicados a comprobantes que luego se anularon: "
            f"{formato_moneda(desglose.aplicado_a_comprobantes_anulados)}",
            ESTILO_NORMAL,
        ))
    if desglose.sin_aplicar:
        elementos.append(Paragraph(
            f"&nbsp;&nbsp;— sin aplicar (quedó como saldo a favor): "
            f"{formato_moneda(desglose.sin_aplicar)}",
            ESTILO_NORMAL,
        ))
    elementos.append(Spacer(1, 2 * mm))

    elementos.append(Paragraph(
        f"Saldo consolidado anterior: {formato_moneda(estado.saldo_consolidado_anterior)}",
        ESTILO_NORMAL,
    ))
    elementos.append(Paragraph(
        f"Saldo consolidado del período: {formato_moneda(estado.saldo_consolidado_del_periodo)}",
        ESTILO_NORMAL,
    ))
    elementos.append(Paragraph(
        f"<b>Saldo pendiente al cierre: {formato_moneda(estado.saldo_consolidado_cierre)}</b>",
        ESTILO_NORMAL,
    ))
    elementos.extend(_pie_de_pagina())

    return generar_pdf(ruta_salida, elementos)


def _detalle_movimiento_historial(movimiento) -> str:
    if movimiento.tipo == "remito":
        return formato_moneda(movimiento.saldo)
    partes = [
        f"Remito {a.comprobante_numero} ({_mes_anio(a.comprobante_fecha)} — {formato_moneda(a.monto)})"
        for a in movimiento.aplicaciones
    ]
    if movimiento.sin_aplicar and movimiento.sin_aplicar > 0:
        partes.append(f"saldo a favor ({formato_moneda(movimiento.sin_aplicar)})")
    return "Aplicado a " + ", ".join(partes) if partes else "Sin aplicar (saldo a favor)"


def generar_pdf_historial_movimientos(
    conexion: sqlite3.Connection,
    cliente_id: int,
    fecha_desde: str,
    fecha_hasta: str,
    ruta_salida: Path | str,
) -> Path:
    """Modalidad "Historial completo de movimientos": remitos y recibos
    del período en una sola línea de tiempo, mostrando explícitamente a
    qué remito aplicó cada recibo (sin asumir que coinciden en fecha),
    para auditar la cuenta (docs/AJUSTES_V1.1.md, rediseño del estado
    de cuenta corriente)."""
    cliente = datos_clientes.obtener_cliente(conexion, cliente_id)
    if cliente is None:
        raise ValueError(f"No existe el cliente {cliente_id}.")
    historial = historial_de_movimientos(conexion, cliente_id, fecha_desde, fecha_hasta)

    subtitulo = f"{cliente['nombre']} — {formato_fecha(fecha_desde)} a {formato_fecha(fecha_hasta)}"
    elementos = encabezado("Estado de cuenta — Historial de movimientos", subtitulo)

    if historial.movimientos:
        filas = [
            [
                formato_fecha(m.fecha),
                "Remito" if m.tipo == "remito" else "Recibo",
                m.numero,
                m.sucursal_nombre or "-",
                formato_moneda(m.monto),
                _detalle_movimiento_historial(m),
            ]
            for m in historial.movimientos
        ]
        elementos.append(tabla(
            ["Fecha", "Tipo", "Nº", "Sucursal", "Importe", "Saldo / Aplicación"], filas,
            anchos=[22 * mm, 18 * mm, 18 * mm, 28 * mm, 25 * mm, 59 * mm],
            alinear_derecha=[4],
        ))
    else:
        elementos.append(Paragraph("Sin movimientos en el período.", ESTILO_NORMAL))
    elementos.append(Spacer(1, 4 * mm))

    elementos.append(Paragraph(
        f"Saldo a favor al cierre: {formato_moneda(historial.saldo_a_favor_cierre)}", ESTILO_NORMAL
    ))
    elementos.append(Paragraph(
        f"<b>Saldo consolidado al cierre: {formato_moneda(historial.saldo_consolidado_cierre)}</b>",
        ESTILO_NORMAL,
    ))
    elementos.extend(_pie_de_pagina())

    return generar_pdf(ruta_salida, elementos)
