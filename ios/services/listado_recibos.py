"""Listado de recibos emitidos (docs/AJUSTES_V1.1.md, módulo de recibos):
consulta de solo lectura sobre los recibos que ya asentó la pantalla
Cobranzas, con lo aplicado y lo pendiente de cada uno. No crea, modifica
ni anula recibos: eso sigue siendo responsabilidad de
ios/services/cobranzas.py."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from ios.data import recibos as datos_recibos


@dataclass
class ReciboListado:
    recibo_id: int
    numero: int
    fecha: str
    cliente_id: int
    cliente_nombre: str
    monto_total: Decimal
    aplicado: Decimal
    pendiente: Decimal
    origen: str
    estado: str


def listado_recibos(
    conexion: sqlite3.Connection,
    cliente_id: int | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    estado: str | None = None,
) -> list[ReciboListado]:
    recibos = []
    for fila in datos_recibos.listar_recibos(
        conexion, cliente_id=cliente_id, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, estado=estado
    ):
        aplicado = datos_recibos.total_aplicado_de_recibo(conexion, fila["id"])
        recibos.append(ReciboListado(
            recibo_id=fila["id"],
            numero=fila["numero"],
            fecha=fila["fecha"],
            cliente_id=fila["cliente_id"],
            cliente_nombre=fila["cliente_nombre"],
            monto_total=fila["monto_total"],
            aplicado=aplicado,
            pendiente=fila["monto_total"] - aplicado,
            origen=fila["origen"],
            estado=fila["estado"],
        ))
    return recibos
