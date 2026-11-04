"""PDF del recibo: número, fecha, cliente, formas de pago (con los datos
de cada cheque) y remitos que cubre (docs/PLAN.md, "Reportes y
dashboard")."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer

from ios.data import cheques as datos_cheques
from ios.data import clientes as datos_clientes
from ios.data import comprobantes as datos_comprobantes
from ios.data import recibos as datos_recibos
from ios.reports.formato import formato_fecha, formato_moneda
from ios.reports.pdf_comun import ESTILO_NORMAL, encabezado, generar_pdf, tabla


def generar_pdf_recibo(conexion: sqlite3.Connection, recibo_id: int, ruta_salida: Path | str) -> Path:
    recibo = datos_recibos.obtener_recibo(conexion, recibo_id)
    if recibo is None:
        raise ValueError(f"No existe el recibo {recibo_id}.")
    cliente = datos_clientes.obtener_cliente(conexion, recibo["cliente_id"])

    elementos = encabezado(
        f"Recibo Nº {recibo['numero']}",
        f"Fecha: {formato_fecha(recibo['fecha'])} · Cliente: {cliente['nombre']}",
    )

    filas_pagos = []
    for pago in datos_recibos.listar_recibo_pagos(conexion, recibo_id):
        forma = conexion.execute(
            "SELECT nombre FROM formas_pago WHERE id = ?", (pago["forma_pago_id"],)
        ).fetchone()["nombre"]
        detalle_cheque = ""
        if pago["cheque_id"] is not None:
            cheque = datos_cheques.obtener_cheque(conexion, pago["cheque_id"])
            detalle_cheque = (
                f"Nº {cheque['numero']} · {cheque['banco'] or '-'} · "
                f"cobra el {formato_fecha(cheque['fecha_cobro'])}"
            )
        filas_pagos.append([forma, formato_moneda(pago["monto"]), detalle_cheque])

    elementos.append(Paragraph("Formas de pago", ESTILO_NORMAL))
    elementos.append(Spacer(1, 2 * mm))
    elementos.append(tabla(
        ["Forma de pago", "Monto", "Cheque"], filas_pagos,
        anchos=[40 * mm, 30 * mm, 100 * mm],
    ))
    elementos.append(Spacer(1, 6 * mm))

    filas_remitos = []
    for aplicacion in datos_recibos.listar_aplicaciones_de_recibo(conexion, recibo_id):
        comprobante = datos_comprobantes.obtener_comprobante(conexion, aplicacion["comprobante_id"])
        filas_remitos.append([
            comprobante["numero"],
            formato_fecha(comprobante["fecha"]),
            formato_moneda(aplicacion["monto_aplicado"]),
        ])

    elementos.append(Paragraph("Remitos cubiertos", ESTILO_NORMAL))
    elementos.append(Spacer(1, 2 * mm))
    if filas_remitos:
        elementos.append(tabla(
            ["Remito", "Fecha", "Monto aplicado"], filas_remitos,
            anchos=[40 * mm, 40 * mm, 40 * mm],
        ))
    else:
        elementos.append(Paragraph("El pago no se aplicó a ningún remito (saldo a favor).", ESTILO_NORMAL))

    elementos.append(Spacer(1, 6 * mm))
    elementos.append(Paragraph(f"<b>Total: {formato_moneda(recibo['monto_total'])}</b>", ESTILO_NORMAL))

    return generar_pdf(ruta_salida, elementos)
