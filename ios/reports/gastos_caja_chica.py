"""Reporte "Gastos de caja chica": PDF y Excel (docs/AJUSTES_V1.1.md,
etapa 6.2, D4)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import openpyxl

from ios.reports.formato import formato_fecha, formato_moneda
from ios.reports.pdf_comun import encabezado, generar_pdf, tabla
from ios.services.gastos_caja_chica import gastos_de_caja_chica


def generar_pdf_gastos_caja_chica(
    conexion: sqlite3.Connection,
    fecha_desde: str,
    fecha_hasta: str,
    ruta_salida: Path | str,
    categoria_id: int | None = None,
    forma_pago_id: int | None = None,
) -> Path:
    resultado = gastos_de_caja_chica(conexion, fecha_desde, fecha_hasta, categoria_id, forma_pago_id)
    subtitulo = f"{formato_fecha(fecha_desde)} a {formato_fecha(fecha_hasta)}"
    elementos = encabezado("Gastos de caja chica", subtitulo)

    filas = [
        [formato_fecha(f.fecha), f.categoria_nombre, f.concepto, f.forma_pago_nombre, formato_moneda(f.monto)]
        for f in resultado.filas
    ]
    elementos.append(tabla(["Fecha", "Categoría", "Concepto", "Forma de pago", "Monto"], filas))

    filas_subtotal = [[s.nombre, formato_moneda(s.monto)] for s in resultado.subtotales_por_categoria]
    filas_subtotal.append(["Total", formato_moneda(resultado.total)])
    elementos.append(tabla(["Categoría", "Subtotal"], filas_subtotal))

    return generar_pdf(ruta_salida, elementos)


def generar_excel_gastos_caja_chica(
    conexion: sqlite3.Connection,
    fecha_desde: str,
    fecha_hasta: str,
    ruta_salida: Path | str,
    categoria_id: int | None = None,
    forma_pago_id: int | None = None,
) -> Path:
    resultado = gastos_de_caja_chica(conexion, fecha_desde, fecha_hasta, categoria_id, forma_pago_id)

    libro = openpyxl.Workbook()
    ws = libro.active
    ws.title = "Gastos de caja chica"
    ws.append([f"{fecha_desde} a {fecha_hasta}"])
    ws.append(["Fecha", "Categoría", "Concepto", "Forma de pago", "Monto"])
    for f in resultado.filas:
        ws.append([f.fecha, f.categoria_nombre, f.concepto, f.forma_pago_nombre, float(f.monto)])

    ws_subtotales = libro.create_sheet("Por categoría")
    ws_subtotales.append(["Categoría", "Subtotal"])
    for s in resultado.subtotales_por_categoria:
        ws_subtotales.append([s.nombre, float(s.monto)])
    ws_subtotales.append(["Total", float(resultado.total)])

    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta_salida)
    return ruta_salida
