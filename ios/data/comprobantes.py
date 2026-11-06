"""Consultas SQL de comprobantes. Sin lógica de negocio: eso vive en
ios/services/comprobantes.py (cálculo de monto final e IVA, duplicados)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal


def buscar_vigentes_por_tipo_numero(
    conexion: sqlite3.Connection, tipo_comprobante_id: int, numero: str
) -> list[sqlite3.Row]:
    """Comprobantes vigentes con ese tipo y número, en cualquier cliente
    (docs/AJUSTES_V1.1.md, D1: los números repetidos se permiten; esto solo
    sirve para avisar, nunca para bloquear por sí solo)."""
    return conexion.execute(
        """
        SELECT co.*, cl.nombre AS cliente_nombre FROM comprobantes co
        JOIN clientes cl ON cl.id = co.cliente_id
        WHERE co.tipo_comprobante_id = ? AND co.numero = ? AND co.estado = 'vigente'
        """,
        (tipo_comprobante_id, numero),
    ).fetchall()


def maximo_numero_comprobante(conexion: sqlite3.Connection, tipo_comprobante_id: int) -> int | None:
    """Mayor número puramente numérico ya usado para ese tipo (manual o
    cargado con detalle, vigente o anulado: un número usado no se reemite).
    Los números no numéricos (de remitos manuales con otro formato) se
    ignoran, igual que al importar recibos con número no numérico
    (docs/AJUSTES_V1.1.md, etapa 7)."""
    fila = conexion.execute(
        "SELECT MAX(CAST(numero AS INTEGER)) AS maximo FROM comprobantes "
        "WHERE tipo_comprobante_id = ? AND numero GLOB '[0-9]*' AND numero NOT GLOB '*[^0-9]*'",
        (tipo_comprobante_id,),
    ).fetchone()
    return fila["maximo"]


def insertar_comprobante(
    conexion: sqlite3.Connection,
    tipo_comprobante_id: int,
    numero: str,
    fecha: str,
    cliente_id: int,
    sucursal_id: int,
    monto_lista: Decimal,
    descuento_pct: Decimal,
    monto_final: Decimal,
    con_iva: bool,
    iva_discriminado: Decimal,
    nombre_particular: str | None,
    notas: str | None,
) -> int:
    cursor = conexion.execute(
        """
        INSERT INTO comprobantes
            (tipo_comprobante_id, numero, fecha, cliente_id, sucursal_id,
             nombre_particular, monto_lista, descuento_pct, monto_final,
             con_iva, iva_discriminado, notas, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'vigente')
        """,
        (
            tipo_comprobante_id,
            numero,
            fecha,
            cliente_id,
            sucursal_id,
            nombre_particular,
            monto_lista,
            descuento_pct,
            monto_final,
            int(con_iva),
            iva_discriminado,
            notas,
        ),
    )
    return cursor.lastrowid


def actualizar_comprobante(conexion: sqlite3.Connection, comprobante_id: int, campos: dict) -> None:
    columnas = ", ".join(f"{columna} = ?" for columna in campos)
    valores = list(campos.values())
    conexion.execute(
        f"UPDATE comprobantes SET {columnas} WHERE id = ?", (*valores, comprobante_id)
    )


def marcar_estado(conexion: sqlite3.Connection, comprobante_id: int, estado: str) -> None:
    conexion.execute(
        "UPDATE comprobantes SET estado = ? WHERE id = ?", (estado, comprobante_id)
    )


def obtener_comprobante(conexion: sqlite3.Connection, comprobante_id: int) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT * FROM comprobantes WHERE id = ?", (comprobante_id,)
    ).fetchone()


def listar_comprobantes(
    conexion: sqlite3.Connection,
    cliente_id: int | None = None,
    sucursal_id: int | None = None,
    mes: str | None = None,
    estado: str | None = None,
    tipo_comprobante_id: int | None = None,
    numero: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> list[sqlite3.Row]:
    """``mes`` en formato 'YYYY-MM'; ``fecha_desde``/``fecha_hasta`` en
    'YYYY-MM-DD' (filtro entre fechas, docs/AJUSTES_V1.1.md, etapa 2.3).
    ``numero`` busca por coincidencia parcial. Sin filtros, devuelve todo."""
    condiciones = []
    parametros: list = []

    if cliente_id is not None:
        condiciones.append("cliente_id = ?")
        parametros.append(cliente_id)
    if sucursal_id is not None:
        condiciones.append("sucursal_id = ?")
        parametros.append(sucursal_id)
    if mes is not None:
        condiciones.append("fecha LIKE ?")
        parametros.append(f"{mes}%")
    if fecha_desde is not None:
        condiciones.append("fecha >= ?")
        parametros.append(fecha_desde)
    if fecha_hasta is not None:
        condiciones.append("fecha <= ?")
        parametros.append(fecha_hasta)
    if estado is not None:
        condiciones.append("estado = ?")
        parametros.append(estado)
    if tipo_comprobante_id is not None:
        condiciones.append("tipo_comprobante_id = ?")
        parametros.append(tipo_comprobante_id)
    if numero is not None:
        condiciones.append("numero LIKE ?")
        parametros.append(f"%{numero}%")

    sql = "SELECT * FROM comprobantes"
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY fecha, id"

    return conexion.execute(sql, parametros).fetchall()
