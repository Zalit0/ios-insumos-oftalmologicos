"""Reporte "Compras por cliente": PDF y Excel, por cliente o ranking de
todos (docs/AJUSTES_V1.1.md, etapa 6.1)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import openpyxl

from ios.reports.formato import formato_fecha, formato_moneda
from ios.reports.pdf_comun import encabezado, generar_pdf, tabla
from ios.services.compras_por_cliente import compras_de_cliente, ranking_todos_los_clientes


def generar_pdf_compras_cliente(
    conexion: sqlite3.Connection,
    cliente_id: int,
    cliente_nombre: str,
    fecha_desde: str,
    fecha_hasta: str,
    ruta_salida: Path | str,
    sucursal_id: int | None = None,
) -> Path:
    resultado = compras_de_cliente(conexion, cliente_id, fecha_desde, fecha_hasta, sucursal_id)
    subtitulo = f"{cliente_nombre} · {formato_fecha(fecha_desde)} a {formato_fecha(fecha_hasta)}"
    elementos = encabezado("Compras por cliente", subtitulo)

    filas = [
        [
            formato_fecha(f.fecha),
            f.numero,
            f.sucursal_nombre,
            formato_moneda(f.monto_lista),
            formato_moneda(f.monto_final),
            formato_moneda(f.iva_discriminado),
            formato_moneda(f.cobrado),
            formato_moneda(f.pendiente),
        ]
        for f in resultado.filas
    ]
    filas.append([
        "", "", "Total",
        formato_moneda(resultado.total_lista),
        formato_moneda(resultado.total_final),
        formato_moneda(resultado.total_iva),
        formato_moneda(resultado.total_cobrado),
        formato_moneda(resultado.total_pendiente),
    ])
    elementos.append(tabla(
        ["Fecha", "Número", "Sucursal", "Lista", "Final", "IVA", "Cobrado", "Pendiente"], filas
    ))
    return generar_pdf(ruta_salida, elementos)


def generar_excel_compras_cliente(
    conexion: sqlite3.Connection,
    cliente_id: int,
    cliente_nombre: str,
    fecha_desde: str,
    fecha_hasta: str,
    ruta_salida: Path | str,
    sucursal_id: int | None = None,
) -> Path:
    resultado = compras_de_cliente(conexion, cliente_id, fecha_desde, fecha_hasta, sucursal_id)

    libro = openpyxl.Workbook()
    ws = libro.active
    ws.title = "Compras por cliente"
    ws.append([cliente_nombre, f"{fecha_desde} a {fecha_hasta}"])
    ws.append(["Fecha", "Número", "Sucursal", "Lista", "Final", "IVA", "Cobrado", "Pendiente"])
    for f in resultado.filas:
        ws.append([
            f.fecha, f.numero, f.sucursal_nombre,
            float(f.monto_lista), float(f.monto_final),
            float(f.iva_discriminado), float(f.cobrado), float(f.pendiente),
        ])
    ws.append([
        "", "", "Total",
        float(resultado.total_lista), float(resultado.total_final),
        float(resultado.total_iva), float(resultado.total_cobrado), float(resultado.total_pendiente),
    ])

    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta_salida)
    return ruta_salida


def generar_pdf_ranking_clientes(
    conexion: sqlite3.Connection, fecha_desde: str, fecha_hasta: str, ruta_salida: Path | str
) -> Path:
    ranking = ranking_todos_los_clientes(conexion, fecha_desde, fecha_hasta)
    subtitulo = f"{formato_fecha(fecha_desde)} a {formato_fecha(fecha_hasta)}"
    elementos = encabezado("Compras por cliente — Todos los clientes", subtitulo)

    filas = [[f.nombre, str(f.cantidad), formato_moneda(f.total_final)] for f in ranking]
    elementos.append(tabla(["Cliente", "Comprobantes", "Total final"], filas))
    return generar_pdf(ruta_salida, elementos)


def generar_excel_ranking_clientes(
    conexion: sqlite3.Connection, fecha_desde: str, fecha_hasta: str, ruta_salida: Path | str
) -> Path:
    ranking = ranking_todos_los_clientes(conexion, fecha_desde, fecha_hasta)

    libro = openpyxl.Workbook()
    ws = libro.active
    ws.title = "Ranking de clientes"
    ws.append([f"{fecha_desde} a {fecha_hasta}"])
    ws.append(["Cliente", "Comprobantes", "Total final"])
    for f in ranking:
        ws.append([f.nombre, f.cantidad, float(f.total_final)])

    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta_salida)
    return ruta_salida
