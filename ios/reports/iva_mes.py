"""IVA del mes: Excel con el detalle de comprobantes y compras
(docs/PLAN.md, "Reportes y dashboard")."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import openpyxl

from ios.services.iva_mes import detalle_iva_del_mes


def generar_excel_iva_mes(conexion: sqlite3.Connection, mes: str, ruta_salida: Path | str) -> Path:
    detalle = detalle_iva_del_mes(conexion, mes)

    libro = openpyxl.Workbook()

    ws_resumen = libro.active
    ws_resumen.title = "Resumen"
    ws_resumen.append(["Mes", mes])
    ws_resumen.append(["IVA venta", float(detalle.iva_venta)])
    ws_resumen.append(["IVA compra", float(detalle.iva_compra)])
    ws_resumen.append(["IVA deuda", float(detalle.iva_deuda)])

    ws_ventas = libro.create_sheet("Ventas")
    ws_ventas.append(["Remito", "Fecha", "Monto final", "IVA"])
    for c in detalle.comprobantes:
        ws_ventas.append([c["numero"], c["fecha"], float(c["monto_final"]), float(c["iva_discriminado"])])

    ws_compras = libro.create_sheet("Compras")
    ws_compras.append(["Nº factura", "Fecha", "Monto", "IVA"])
    for c in detalle.compras:
        ws_compras.append([c["numero_factura"], c["fecha"], float(c["monto"]), float(c["iva"])])

    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta_salida)
    return ruta_salida
