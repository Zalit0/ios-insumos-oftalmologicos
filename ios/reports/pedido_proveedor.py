"""PDF del pedido a proveedor: listado de líneas (cristal, graduación
solicitada y cantidad) para poder cargar el pedido real con el proveedor,
con la reposición y las especiales en tablas separadas (plan de detalle
de comprobantes, etapa 4/5.4)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer

from ios.data import pedidos_proveedor as datos_pedidos
from ios.data import proveedores as datos_proveedores
from ios.reports.formato import formato_fecha
from ios.reports.pdf_comun import ESTILO_NORMAL, ESTILO_SUBTITULO, encabezado, generar_pdf, tabla


def generar_pdf_pedido_proveedor(
    conexion: sqlite3.Connection, pedido_id: int, ruta_salida: Path | str
) -> Path:
    pedido = datos_pedidos.obtener_pedido(conexion, pedido_id)
    if pedido is None:
        raise ValueError(f"No existe el pedido {pedido_id}.")
    proveedor = datos_proveedores.obtener_proveedor(conexion, pedido["proveedor_id"])

    elementos = encabezado(
        f"Pedido a {proveedor['nombre']}",
        f"Fecha: {formato_fecha(pedido['fecha'])}",
    )

    lineas = datos_pedidos.listar_lineas_pedido(conexion, pedido_id)
    reposicion = sorted(
        (l for l in lineas if l["origen"] == "reposicion"),
        key=lambda l: l["tipo_cristal_nombre"] or l["descripcion"] or "",
    )
    especiales = sorted(
        (l for l in lineas if l["origen"] == "especial"),
        key=lambda l: l["tipo_cristal_nombre"] or l["descripcion"] or "",
    )

    elementos.append(Paragraph("Reposición", ESTILO_SUBTITULO))
    elementos.append(Spacer(1, 1 * mm))
    if reposicion:
        filas_reposicion = [
            [linea["tipo_cristal_nombre"] or linea["descripcion"] or "",
             linea["graduacion_solicitada"] or "", str(linea["cantidad"])]
            for linea in reposicion
        ]
        elementos.append(tabla(
            ["Cristal", "Graduación", "Cantidad"], filas_reposicion,
            anchos=[75 * mm, 50 * mm, 25 * mm], alinear_derecha=[2],
        ))
    else:
        elementos.append(Paragraph("Sin líneas de reposición.", ESTILO_NORMAL))
    elementos.append(Spacer(1, 4 * mm))

    elementos.append(Paragraph("Especiales", ESTILO_SUBTITULO))
    elementos.append(Spacer(1, 1 * mm))
    if especiales:
        filas_especiales = [
            [linea["tipo_cristal_nombre"] or linea["descripcion"] or "",
             linea["cliente_nombre"] or "", linea["graduacion_solicitada"] or "", str(linea["cantidad"])]
            for linea in especiales
        ]
        elementos.append(tabla(
            ["Cristal/Descripción", "Cliente", "Graduación", "Cantidad"], filas_especiales,
            anchos=[55 * mm, 40 * mm, 35 * mm, 20 * mm], alinear_derecha=[3],
        ))
    else:
        elementos.append(Paragraph("Sin líneas especiales.", ESTILO_NORMAL))

    return generar_pdf(ruta_salida, elementos)
