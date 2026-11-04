"""Consultas SQL de cierres de caja y su detalle por forma de pago."""

from __future__ import annotations

import sqlite3
from decimal import Decimal


def insertar_cierre(conexion: sqlite3.Connection, fecha: str) -> int:
    cursor = conexion.execute(
        "INSERT INTO cierres_caja (fecha, estado) VALUES (?, 'abierto')", (fecha,)
    )
    return cursor.lastrowid


def obtener_cierre(conexion: sqlite3.Connection, cierre_id: int) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT * FROM cierres_caja WHERE id = ?", (cierre_id,)
    ).fetchone()


def obtener_cierre_por_fecha(conexion: sqlite3.Connection, fecha: str) -> sqlite3.Row | None:
    return conexion.execute(
        "SELECT * FROM cierres_caja WHERE fecha = ?", (fecha,)
    ).fetchone()


def marcar_cierre_cerrado(conexion: sqlite3.Connection, cierre_id: int, nota: str | None) -> None:
    conexion.execute(
        "UPDATE cierres_caja SET estado = 'cerrado', nota = ? WHERE id = ?", (nota, cierre_id)
    )


def listar_cierres(conexion: sqlite3.Connection) -> list[sqlite3.Row]:
    return conexion.execute("SELECT * FROM cierres_caja ORDER BY fecha").fetchall()


def listar_cierres_abiertos_anteriores_a(
    conexion: sqlite3.Connection, fecha_hoy: str
) -> list[sqlite3.Row]:
    """Cajas que quedaron abiertas de un día anterior a ``fecha_hoy``: se
    cierran solas al cambiar de día (docs/AJUSTES_V1.1.md, Caja obligatoria
    para cobrar)."""
    return conexion.execute(
        "SELECT * FROM cierres_caja WHERE estado = 'abierto' AND fecha < ? ORDER BY fecha",
        (fecha_hoy,),
    ).fetchall()


def insertar_detalle(
    conexion: sqlite3.Connection,
    cierre_id: int,
    forma_pago_id: int,
    saldo_inicial: Decimal,
    ingresos: Decimal,
    egresos: Decimal,
    saldo_teorico: Decimal,
    arqueo: Decimal,
    diferencia: Decimal,
) -> int:
    cursor = conexion.execute(
        """
        INSERT INTO cierres_caja_detalle
            (cierre_id, forma_pago_id, saldo_inicial, ingresos, egresos,
             saldo_teorico, arqueo, diferencia)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (cierre_id, forma_pago_id, saldo_inicial, ingresos, egresos, saldo_teorico, arqueo,
         diferencia),
    )
    return cursor.lastrowid


def listar_detalle_de_cierre(conexion: sqlite3.Connection, cierre_id: int) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT * FROM cierres_caja_detalle WHERE cierre_id = ? ORDER BY forma_pago_id",
        (cierre_id,),
    ).fetchall()


def obtener_ultimo_detalle_de_forma(
    conexion: sqlite3.Connection, forma_pago_id: int
) -> sqlite3.Row | None:
    """Detalle del último cierre ya cerrado para esa forma de pago."""
    return conexion.execute(
        """
        SELECT d.* FROM cierres_caja_detalle d
        JOIN cierres_caja c ON c.id = d.cierre_id
        WHERE d.forma_pago_id = ? AND c.estado = 'cerrado'
        ORDER BY c.fecha DESC, d.id DESC
        LIMIT 1
        """,
        (forma_pago_id,),
    ).fetchone()
