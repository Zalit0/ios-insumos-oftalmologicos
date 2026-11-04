"""Listado de deudores: PDF y Excel (docs/PLAN.md, "Reportes y
dashboard")."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import openpyxl

from ios.reports.formato import formato_fecha, formato_moneda
from ios.reports.pdf_comun import encabezado, generar_pdf, tabla
from ios.services.listado_deudores import listado_deudores


def generar_pdf_deudores(
    conexion: sqlite3.Connection, fecha_referencia: str, ruta_salida: Path | str
) -> Path:
    deudores = listado_deudores(conexion, fecha_referencia)
    elementos = encabezado("Listado de deudores", f"Al {formato_fecha(fecha_referencia)}")

    filas = [
        [
            d.nombre,
            formato_moneda(d.saldo),
            formato_fecha(d.fecha_remito_mas_viejo) if d.fecha_remito_mas_viejo else "-",
            f"{d.antiguedad_dias} días" if d.antiguedad_dias is not None else "-",
        ]
        for d in deudores
    ]
    elementos.append(tabla(["Cliente", "Saldo", "Remito más viejo impago", "Antigüedad"], filas))
    return generar_pdf(ruta_salida, elementos)


def generar_excel_deudores(
    conexion: sqlite3.Connection, fecha_referencia: str, ruta_salida: Path | str
) -> Path:
    deudores = listado_deudores(conexion, fecha_referencia)

    libro = openpyxl.Workbook()
    ws = libro.active
    ws.title = "Deudores"
    ws.append(["Cliente", "Saldo", "Remito más viejo impago", "Antigüedad (días)"])
    for d in deudores:
        ws.append([
            d.nombre,
            float(d.saldo),
            d.fecha_remito_mas_viejo or "",
            d.antiguedad_dias if d.antiguedad_dias is not None else "",
        ])

    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta_salida)
    return ruta_salida
