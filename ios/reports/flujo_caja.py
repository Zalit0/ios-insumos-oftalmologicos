"""Flujo de caja de un período: Excel con el detalle diario y por
categoría (docs/PLAN.md, "Reportes y dashboard")."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import openpyxl

from ios.services.flujo_caja import flujo_de_caja_diario, flujo_de_caja_por_categoria


def generar_excel_flujo_caja(
    conexion: sqlite3.Connection, fecha_desde: str, fecha_hasta: str, ruta_salida: Path | str
) -> Path:
    diario = flujo_de_caja_diario(conexion, fecha_desde, fecha_hasta)
    por_categoria = flujo_de_caja_por_categoria(conexion, fecha_desde, fecha_hasta)

    libro = openpyxl.Workbook()

    ws_diario = libro.active
    ws_diario.title = "Por día"
    ws_diario.append(["Fecha", "Ingresos", "Egresos", "Saldo del día", "Saldo acumulado"])
    for fila in diario:
        ws_diario.append([
            fila.fecha, float(fila.ingresos), float(fila.egresos),
            float(fila.saldo_del_dia), float(fila.saldo_acumulado),
        ])

    ws_categoria = libro.create_sheet("Por categoría")
    ws_categoria.append(["Categoría", "Ingresos", "Egresos"])
    for categoria, totales in por_categoria.items():
        ws_categoria.append([categoria, float(totales["ingresos"]), float(totales["egresos"])])

    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta_salida)
    return ruta_salida
