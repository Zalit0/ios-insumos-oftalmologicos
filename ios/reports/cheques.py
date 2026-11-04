"""PDF de cheques en cartera, ordenados por fecha de cobro, con cliente,
banco, monto y estado (docs/PLAN.md, "Reportes y dashboard")."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ios.data import cheques as datos_cheques
from ios.data import clientes as datos_clientes
from ios.reports.formato import formato_fecha, formato_moneda
from ios.reports.pdf_comun import encabezado, generar_pdf, tabla

ETIQUETAS_ESTADO = {
    "en_cartera": "En cartera",
    "cobrado": "Cobrado",
    "entregado_a_proveedor": "Entregado a proveedor",
    "rechazado": "Rechazado",
    "anulado": "Anulado",
}


def generar_pdf_cheques_en_cartera(conexion: sqlite3.Connection, ruta_salida: Path | str) -> Path:
    elementos = encabezado("Cheques en cartera")

    filas = []
    for cheque in datos_cheques.listar_cheques_en_cartera(conexion):
        cliente = datos_clientes.obtener_cliente(conexion, cheque["cliente_id"])
        filas.append([
            cheque["numero"],
            cliente["nombre"],
            cheque["banco"] or "-",
            formato_moneda(cheque["monto"]),
            formato_fecha(cheque["fecha_cobro"]),
            ETIQUETAS_ESTADO.get(cheque["estado"], cheque["estado"]),
        ])

    elementos.append(tabla(["Nº", "Cliente", "Banco", "Monto", "Fecha de cobro", "Estado"], filas))
    return generar_pdf(ruta_salida, elementos)
