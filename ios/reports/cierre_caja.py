"""PDF del cierre de caja: saldo inicial, ingresos, egresos, saldo
teórico, arqueo y diferencia por forma de pago (docs/PLAN.md, etapa 7)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from reportlab.platypus import Paragraph, Spacer
from reportlab.lib.units import mm

from ios.data import cierres_caja as datos_cierres
from ios.reports.formato import formato_fecha, formato_moneda
from ios.reports.pdf_comun import ESTILO_NORMAL, encabezado, generar_pdf, tabla


def generar_pdf_cierre_caja(
    conexion: sqlite3.Connection, cierre_id: int, ruta_salida: Path | str
) -> Path:
    cierre = datos_cierres.obtener_cierre(conexion, cierre_id)
    if cierre is None:
        raise ValueError(f"No existe el cierre {cierre_id}.")

    elementos = encabezado("Cierre de caja", formato_fecha(cierre["fecha"]))

    filas = []
    for detalle in datos_cierres.listar_detalle_de_cierre(conexion, cierre_id):
        forma = conexion.execute(
            "SELECT nombre FROM formas_pago WHERE id = ?", (detalle["forma_pago_id"],)
        ).fetchone()["nombre"]
        filas.append([
            forma,
            formato_moneda(detalle["saldo_inicial"]),
            formato_moneda(detalle["ingresos"]),
            formato_moneda(detalle["egresos"]),
            formato_moneda(detalle["saldo_teorico"]),
            formato_moneda(detalle["arqueo"]),
            formato_moneda(detalle["diferencia"]),
        ])

    elementos.append(tabla(
        ["Forma de pago", "Saldo inicial", "Ingresos", "Egresos", "Saldo teórico", "Arqueo", "Diferencia"],
        filas,
    ))

    if cierre["nota"]:
        elementos.append(Spacer(1, 4 * mm))
        elementos.append(Paragraph(f"Nota: {cierre['nota']}", ESTILO_NORMAL))

    return generar_pdf(ruta_salida, elementos)
