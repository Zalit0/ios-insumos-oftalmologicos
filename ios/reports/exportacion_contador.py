"""Exportación a Excel para el contador: comprobantes, recibos, compras y
movimientos de caja de un período (docs/PLAN.md, "Reportes y dashboard").
``fecha_desde``/``fecha_hasta`` en formato 'YYYY-MM-DD', inclusive."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import openpyxl


def generar_excel_exportacion_contador(
    conexion: sqlite3.Connection, fecha_desde: str, fecha_hasta: str, ruta_salida: Path | str
) -> Path:
    libro = openpyxl.Workbook()
    libro.remove(libro.active)

    ws_comprobantes = libro.create_sheet("Comprobantes")
    ws_comprobantes.append(["Tipo", "Número", "Fecha", "Cliente", "Monto final", "IVA", "Estado"])
    comprobantes = conexion.execute(
        """
        SELECT co.numero, co.fecha, co.monto_final, co.iva_discriminado, co.estado,
               tc.abreviatura AS tipo, cl.nombre AS cliente
        FROM comprobantes co
        JOIN tipos_comprobante tc ON tc.id = co.tipo_comprobante_id
        JOIN clientes cl ON cl.id = co.cliente_id
        WHERE co.fecha BETWEEN ? AND ?
        ORDER BY co.fecha
        """,
        (fecha_desde, fecha_hasta),
    ).fetchall()
    for c in comprobantes:
        ws_comprobantes.append([
            c["tipo"], c["numero"], c["fecha"], c["cliente"],
            float(c["monto_final"]), float(c["iva_discriminado"]), c["estado"],
        ])

    ws_recibos = libro.create_sheet("Recibos")
    ws_recibos.append(["Número", "Fecha", "Cliente", "Monto total", "Origen", "Estado"])
    recibos = conexion.execute(
        """
        SELECT r.numero, r.fecha, r.monto_total, r.origen, r.estado, cl.nombre AS cliente
        FROM recibos r JOIN clientes cl ON cl.id = r.cliente_id
        WHERE r.fecha BETWEEN ? AND ?
        ORDER BY r.fecha
        """,
        (fecha_desde, fecha_hasta),
    ).fetchall()
    for r in recibos:
        ws_recibos.append([
            r["numero"], r["fecha"], r["cliente"], float(r["monto_total"]), r["origen"], r["estado"],
        ])

    ws_compras = libro.create_sheet("Compras")
    ws_compras.append(["Nº factura", "Fecha", "Proveedor", "Monto", "IVA"])
    compras = conexion.execute(
        """
        SELECT co.numero_factura, co.fecha, co.monto, co.iva, p.nombre AS proveedor
        FROM compras co JOIN proveedores p ON p.id = co.proveedor_id
        WHERE co.fecha BETWEEN ? AND ?
        ORDER BY co.fecha
        """,
        (fecha_desde, fecha_hasta),
    ).fetchall()
    for c in compras:
        ws_compras.append([c["numero_factura"], c["fecha"], c["proveedor"], float(c["monto"]), float(c["iva"])])

    ws_movimientos = libro.create_sheet("Movimientos de caja")
    ws_movimientos.append(["Fecha y hora", "Tipo", "Forma de pago", "Monto", "Origen", "Concepto"])
    movimientos = conexion.execute(
        """
        SELECT m.fecha_hora, m.tipo, m.monto, m.origen, m.concepto, fp.nombre AS forma_pago
        FROM movimientos_caja m JOIN formas_pago fp ON fp.id = m.forma_pago_id
        WHERE date(m.fecha_hora) BETWEEN ? AND ?
        ORDER BY m.fecha_hora
        """,
        (fecha_desde, fecha_hasta),
    ).fetchall()
    for m in movimientos:
        ws_movimientos.append([
            m["fecha_hora"], m["tipo"], m["forma_pago"], float(m["monto"]), m["origen"], m["concepto"],
        ])

    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta_salida)
    return ruta_salida
