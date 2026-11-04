"""Resumen mensual (equivalente a la hoja TOTALES): PDF y Excel
(docs/PLAN.md, etapa 8)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import openpyxl

from ios.domain.calculos import TotalesMes
from ios.reports.formato import formato_moneda
from ios.reports.pdf_comun import encabezado, generar_pdf, tabla
from ios.services.resumen_mensual import resumen_del_mes, total_disponible_actual

ETIQUETAS = [
    ("total_venta", "Total venta"),
    ("total_pagos", "Total pagos"),
    ("total_saldos", "Total saldos"),
    ("iva_venta", "IVA venta"),
    ("iva_compra", "IVA compra"),
    ("iva_deuda", "IVA deuda"),
    ("comision", "Comisión"),
    ("total_compras", "Total compras"),
    ("depositos", "Depósitos"),
    ("ganancia_teorica", "Ganancia teórica"),
]


def _filas(resumen: TotalesMes, total_disponible) -> list[tuple[str, str]]:
    filas = [(etiqueta, formato_moneda(getattr(resumen, campo))) for campo, etiqueta in ETIQUETAS]
    filas.append(("Total disponible", formato_moneda(total_disponible)))
    return filas


def generar_pdf_resumen_mensual(conexion: sqlite3.Connection, mes: str, ruta_salida: Path | str) -> Path:
    resumen = resumen_del_mes(conexion, mes)
    total_disponible = total_disponible_actual(conexion)

    elementos = encabezado("Resumen mensual", mes)
    elementos.append(tabla(["Concepto", "Monto"], [list(fila) for fila in _filas(resumen, total_disponible)]))
    return generar_pdf(ruta_salida, elementos)


def generar_excel_resumen_mensual(
    conexion: sqlite3.Connection, mes: str, ruta_salida: Path | str
) -> Path:
    resumen = resumen_del_mes(conexion, mes)
    total_disponible = total_disponible_actual(conexion)

    libro = openpyxl.Workbook()
    ws = libro.active
    ws.title = "Resumen"
    ws.append(["Mes", mes])
    ws.append([])
    ws.append(["Concepto", "Monto"])
    for campo, etiqueta in ETIQUETAS:
        ws.append([etiqueta, float(getattr(resumen, campo))])
    ws.append(["Total disponible", float(total_disponible)])

    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta_salida)
    return ruta_salida
