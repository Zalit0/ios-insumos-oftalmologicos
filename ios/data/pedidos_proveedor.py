"""Consultas SQL de pedidos a proveedor y sus líneas (plan de detalle de
comprobantes, etapa 4)."""

from __future__ import annotations

import sqlite3


def insertar_pedido(conexion: sqlite3.Connection, proveedor_id: int, fecha: str) -> int:
    cursor = conexion.execute(
        "INSERT INTO pedidos_proveedor (proveedor_id, fecha, estado) VALUES (?, ?, 'en_carga')",
        (proveedor_id, fecha),
    )
    return cursor.lastrowid


def obtener_pedido(conexion: sqlite3.Connection, pedido_id: int) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT * FROM pedidos_proveedor WHERE id = ?", (pedido_id,)
    ).fetchone()


def obtener_pedido_en_carga(conexion: sqlite3.Connection, proveedor_id: int) -> sqlite3.Row | None:
    """El pedido "en carga" de este proveedor, si hay uno — nunca puede
    haber más de uno a la vez (se garantiza en services/, no acá)."""
    return conexion.execute(
        "SELECT * FROM pedidos_proveedor WHERE proveedor_id = ? AND estado = 'en_carga'",
        (proveedor_id,),
    ).fetchone()


def marcar_estado_pedido(conexion: sqlite3.Connection, pedido_id: int, estado: str) -> None:
    conexion.execute(
        "UPDATE pedidos_proveedor SET estado = ? WHERE id = ?", (estado, pedido_id)
    )


def listar_pedidos(
    conexion: sqlite3.Connection,
    proveedor_id: int | None = None,
    estado: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    numero: int | None = None,
) -> list[sqlite3.Row]:
    condiciones = []
    parametros: list = []
    if proveedor_id is not None:
        condiciones.append("pp.proveedor_id = ?")
        parametros.append(proveedor_id)
    if estado is not None:
        condiciones.append("pp.estado = ?")
        parametros.append(estado)
    if fecha_desde is not None:
        condiciones.append("pp.fecha >= ?")
        parametros.append(fecha_desde)
    if fecha_hasta is not None:
        condiciones.append("pp.fecha <= ?")
        parametros.append(fecha_hasta)
    if numero is not None:
        condiciones.append("pp.id = ?")
        parametros.append(numero)

    sql = (
        "SELECT pp.*, pr.nombre AS proveedor_nombre FROM pedidos_proveedor pp "
        "JOIN proveedores pr ON pr.id = pp.proveedor_id"
    )
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY pp.fecha DESC, pp.id DESC"

    return conexion.execute(sql, parametros).fetchall()


def insertar_linea(
    conexion: sqlite3.Connection,
    pedido_id: int,
    tipo_cristal_id: int | None,
    descripcion: str | None,
    cantidad: int,
    origen: str,
    cliente_id: int | None = None,
    graduacion_solicitada: str | None = None,
) -> int:
    cursor = conexion.execute(
        "INSERT INTO pedido_lineas "
        "(pedido_id, tipo_cristal_id, descripcion, cantidad, origen, cliente_id, "
        "graduacion_solicitada, estado) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'pedido')",
        (pedido_id, tipo_cristal_id, descripcion, cantidad, origen, cliente_id,
         graduacion_solicitada),
    )
    return cursor.lastrowid


def obtener_linea(conexion: sqlite3.Connection, linea_id: int) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT * FROM pedido_lineas WHERE id = ?", (linea_id,)
    ).fetchone()


def actualizar_linea(conexion: sqlite3.Connection, linea_id: int, campos: dict) -> None:
    columnas = ", ".join(f"{columna} = ?" for columna in campos)
    valores = list(campos.values())
    conexion.execute(f"UPDATE pedido_lineas SET {columnas} WHERE id = ?", (*valores, linea_id))


def listar_lineas_pedido(conexion: sqlite3.Connection, pedido_id: int) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT pl.*, tc.nombre AS tipo_cristal_nombre, cl.nombre AS cliente_nombre "
        "FROM pedido_lineas pl "
        "LEFT JOIN tipos_cristal tc ON tc.id = pl.tipo_cristal_id "
        "LEFT JOIN clientes cl ON cl.id = pl.cliente_id "
        "WHERE pl.pedido_id = ? ORDER BY pl.id",
        (pedido_id,),
    ).fetchall()


def lineas_especiales_por_estado(
    conexion: sqlite3.Connection, estados: list[str], cliente_id: int | None = None
) -> list[sqlite3.Row]:
    """Líneas especiales (con cliente) en alguno de ``estados`` — base tanto
    de "pendientes de aprobación del cliente" como de "listas para
    entregar" (plan de detalle de comprobantes, etapa 5)."""
    condiciones = [
        "pl.origen = 'especial'",
        f"pl.estado IN ({', '.join('?' for _ in estados)})",
    ]
    parametros: list = list(estados)
    if cliente_id is not None:
        condiciones.append("pl.cliente_id = ?")
        parametros.append(cliente_id)

    sql = (
        "SELECT pl.*, tc.nombre AS tipo_cristal_nombre, cl.nombre AS cliente_nombre "
        "FROM pedido_lineas pl "
        "LEFT JOIN tipos_cristal tc ON tc.id = pl.tipo_cristal_id "
        "LEFT JOIN clientes cl ON cl.id = pl.cliente_id "
        "WHERE " + " AND ".join(condiciones) +
        " ORDER BY cl.nombre, pl.id"
    )
    return conexion.execute(sql, parametros).fetchall()
