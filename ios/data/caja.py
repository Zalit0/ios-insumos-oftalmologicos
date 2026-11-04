"""Consultas SQL de movimientos de caja."""

from __future__ import annotations

import sqlite3
from decimal import Decimal


def insertar_movimiento(
    conexion: sqlite3.Connection,
    fecha_hora: str,
    tipo: str,
    forma_pago_id: int,
    monto: Decimal,
    origen: str,
    concepto: str | None = None,
    categoria_id: int | None = None,
    movimiento_relacionado_id: int | None = None,
    cierre_id: int | None = None,
    nota: str | None = None,
) -> int:
    cursor = conexion.execute(
        """
        INSERT INTO movimientos_caja
            (fecha_hora, tipo, forma_pago_id, monto, categoria_id, concepto,
             origen, movimiento_relacionado_id, cierre_id, nota)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            fecha_hora,
            tipo,
            forma_pago_id,
            monto,
            categoria_id,
            concepto,
            origen,
            movimiento_relacionado_id,
            cierre_id,
            nota,
        ),
    )
    return cursor.lastrowid


def actualizar_movimiento_relacionado(
    conexion: sqlite3.Connection, movimiento_id: int, movimiento_relacionado_id: int
) -> None:
    conexion.execute(
        "UPDATE movimientos_caja SET movimiento_relacionado_id = ? WHERE id = ?",
        (movimiento_relacionado_id, movimiento_id),
    )


def listar_movimientos_por_concepto(
    conexion: sqlite3.Connection, concepto: str, origen: str
) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT * FROM movimientos_caja WHERE concepto = ? AND origen = ? ORDER BY id",
        (concepto, origen),
    ).fetchall()


def asignar_cierre_a_movimientos_del_dia(
    conexion: sqlite3.Connection, cierre_id: int, fecha: str
) -> None:
    """Todo movimiento sin cierre asignado y con fecha de ese día pasa a
    pertenecer a este cierre. Se usa al cerrar la caja."""
    conexion.execute(
        """
        UPDATE movimientos_caja SET cierre_id = ?
        WHERE cierre_id IS NULL AND fecha_hora LIKE ?
        """,
        (cierre_id, f"{fecha}%"),
    )


def listar_movimientos_del_dia(conexion: sqlite3.Connection, fecha: str) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT * FROM movimientos_caja WHERE fecha_hora LIKE ? ORDER BY fecha_hora",
        (f"{fecha}%",),
    ).fetchall()


def listar_movimientos_de_cierre_y_forma(
    conexion: sqlite3.Connection, cierre_id: int, forma_pago_id: int, tipo: str
) -> list[sqlite3.Row]:
    return conexion.execute(
        """
        SELECT * FROM movimientos_caja
        WHERE cierre_id = ? AND forma_pago_id = ? AND tipo = ?
        """,
        (cierre_id, forma_pago_id, tipo),
    ).fetchall()


def listar_formas_de_pago_con_movimientos_del_dia(
    conexion: sqlite3.Connection, fecha: str
) -> list[int]:
    filas = conexion.execute(
        "SELECT DISTINCT forma_pago_id FROM movimientos_caja WHERE fecha_hora LIKE ?",
        (f"{fecha}%",),
    ).fetchall()
    return [fila["forma_pago_id"] for fila in filas]


def listar_movimientos_sin_cierre(conexion: sqlite3.Connection) -> list[sqlite3.Row]:
    return conexion.execute("SELECT * FROM movimientos_caja WHERE cierre_id IS NULL").fetchall()


def listar_egresos_manuales(
    conexion: sqlite3.Connection,
    fecha_desde: str,
    fecha_hasta: str,
    categoria_id: int | None = None,
    forma_pago_id: int | None = None,
) -> list[sqlite3.Row]:
    """Gastos y retiros de caja chica (docs/AJUSTES_V1.1.md, etapa 6.2, D4):
    egresos de origen 'manual' entre dos fechas (inclusive), filtrables por
    categoría y forma de pago."""
    condiciones = [
        "tipo = 'egreso'", "origen = 'manual'", "substr(fecha_hora, 1, 10) BETWEEN ? AND ?"
    ]
    parametros: list = [fecha_desde, fecha_hasta]

    if categoria_id is not None:
        condiciones.append("categoria_id = ?")
        parametros.append(categoria_id)
    if forma_pago_id is not None:
        condiciones.append("forma_pago_id = ?")
        parametros.append(forma_pago_id)

    sql = "SELECT * FROM movimientos_caja WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY fecha_hora"
    return conexion.execute(sql, parametros).fetchall()
