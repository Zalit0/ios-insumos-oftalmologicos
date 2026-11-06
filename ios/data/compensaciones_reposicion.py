"""Consultas SQL de compensaciones de reposición (plan de detalle de
comprobantes, etapa 5.1): una fila por combinación de tipo de cristal y
graduación, con la cantidad que ya se repuso de más por una devolución —
se consulta y se descuenta al generar el próximo pedido de reposición."""

from __future__ import annotations

import sqlite3


def incrementar_compensacion(
    conexion: sqlite3.Connection, tipo_cristal_id: int, graduacion: str, cantidad: int
) -> None:
    existente = conexion.execute(
        "SELECT id FROM compensaciones_reposicion WHERE tipo_cristal_id = ? AND graduacion = ?",
        (tipo_cristal_id, graduacion),
    ).fetchone()
    if existente is None:
        conexion.execute(
            "INSERT INTO compensaciones_reposicion (tipo_cristal_id, graduacion, cantidad) "
            "VALUES (?, ?, ?)",
            (tipo_cristal_id, graduacion, cantidad),
        )
    else:
        conexion.execute(
            "UPDATE compensaciones_reposicion SET cantidad = cantidad + ? WHERE id = ?",
            (cantidad, existente["id"]),
        )


def obtener_cantidad_compensada(
    conexion: sqlite3.Connection, tipo_cristal_id: int, graduacion: str
) -> int:
    fila = conexion.execute(
        "SELECT cantidad FROM compensaciones_reposicion WHERE tipo_cristal_id = ? AND graduacion = ?",
        (tipo_cristal_id, graduacion),
    ).fetchone()
    return fila["cantidad"] if fila is not None else 0


def descontar_compensacion(
    conexion: sqlite3.Connection, tipo_cristal_id: int, graduacion: str, cantidad: int
) -> None:
    """Resta ``cantidad`` de la compensación pendiente de esa combinación.
    Si se termina de usar (llega a cero), se borra la fila — una
    compensación resuelta no tiene nada más que decir."""
    fila = conexion.execute(
        "SELECT id, cantidad FROM compensaciones_reposicion WHERE tipo_cristal_id = ? AND graduacion = ?",
        (tipo_cristal_id, graduacion),
    ).fetchone()
    if fila is None:
        return
    restante = fila["cantidad"] - cantidad
    if restante <= 0:
        conexion.execute("DELETE FROM compensaciones_reposicion WHERE id = ?", (fila["id"],))
    else:
        conexion.execute(
            "UPDATE compensaciones_reposicion SET cantidad = ? WHERE id = ?", (restante, fila["id"])
        )


def listar_compensaciones(conexion: sqlite3.Connection) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT cr.*, tc.nombre AS tipo_cristal_nombre FROM compensaciones_reposicion cr "
        "JOIN tipos_cristal tc ON tc.id = cr.tipo_cristal_id "
        "ORDER BY tc.nombre, cr.graduacion"
    ).fetchall()
