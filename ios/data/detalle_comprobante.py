"""Consultas SQL del detalle (renglones) de un comprobante (plan de
detalle de comprobantes, etapa 2). Opcional: un comprobante cargado con la
carga rápida de siempre simplemente no tiene filas acá."""

from __future__ import annotations

import sqlite3
from decimal import Decimal


def insertar_detalle(
    conexion: sqlite3.Connection,
    comprobante_id: int,
    tipo_cristal_id: int | None,
    descripcion: str | None,
    graduacion: str,
    cantidad: int,
    precio_unitario: Decimal,
    subtotal: Decimal,
    pedido_especial_linea_id: int | None = None,
) -> int:
    cursor = conexion.execute(
        "INSERT INTO detalle_comprobante "
        "(comprobante_id, tipo_cristal_id, descripcion, graduacion, cantidad, "
        "precio_unitario, subtotal, pedido_especial_linea_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (comprobante_id, tipo_cristal_id, descripcion, graduacion, cantidad,
         precio_unitario, subtotal, pedido_especial_linea_id),
    )
    return cursor.lastrowid


def listar_detalle_por_comprobante(
    conexion: sqlite3.Connection, comprobante_id: int
) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT detalle_comprobante.*, tipos_cristal.nombre AS tipo_cristal_nombre "
        "FROM detalle_comprobante "
        "LEFT JOIN tipos_cristal ON tipos_cristal.id = detalle_comprobante.tipo_cristal_id "
        "WHERE comprobante_id = ? ORDER BY detalle_comprobante.id",
        (comprobante_id,),
    ).fetchall()


def eliminar_detalle_por_comprobante(conexion: sqlite3.Connection, comprobante_id: int) -> None:
    conexion.execute("DELETE FROM detalle_comprobante WHERE comprobante_id = ?", (comprobante_id,))


def detalle_pendiente_de_reposicion(
    conexion: sqlite3.Connection, fecha_desde: str, fecha_hasta: str
) -> list[sqlite3.Row]:
    """Renglones de venta de stock (sin agrupar, uno por fila) que todavía
    no se incluyeron en ningún pedido de reposición, en el rango de fechas
    — base del pedido de reposición al proveedor (plan de detalle de
    comprobantes, etapa 3/4/5.2): solo cuenta renglones de stock
    (``pedido_especial_linea_id`` nulo — los especiales no reponen stock, se
    piden aparte) de comprobantes vigentes (uno anulado no generó una venta
    real), de tipos marcados ``reponible`` (p. ej. minerales "hasta agotar
    stock" quedan afuera aunque se hayan vendido de stock), y que
    ``incluido_en_reposicion`` todavía esté en 0 — así, si se generan dos
    pedidos de reposición con rangos de fechas que se superponen, lo ya
    pedido no se vuelve a contar (``ios.services.reposicion`` agrupa esto
    por tipo de cristal y graduación, y marca los renglones usados)."""
    return conexion.execute(
        """
        SELECT dc.id AS id, tc.id AS tipo_cristal_id, tc.nombre AS nombre,
               dc.graduacion AS graduacion, dc.cantidad AS cantidad
        FROM detalle_comprobante dc
        JOIN comprobantes co ON co.id = dc.comprobante_id
        JOIN tipos_cristal tc ON tc.id = dc.tipo_cristal_id
        WHERE dc.pedido_especial_linea_id IS NULL
          AND dc.incluido_en_reposicion = 0
          AND tc.reponible = 1
          AND co.estado = 'vigente'
          AND co.fecha BETWEEN ? AND ?
        ORDER BY tc.nombre, dc.graduacion
        """,
        (fecha_desde, fecha_hasta),
    ).fetchall()


def marcar_incluido_en_reposicion(conexion: sqlite3.Connection, detalle_ids: list[int]) -> None:
    if not detalle_ids:
        return
    marcadores = ", ".join("?" for _ in detalle_ids)
    conexion.execute(
        f"UPDATE detalle_comprobante SET incluido_en_reposicion = 1 WHERE id IN ({marcadores})",
        detalle_ids,
    )
