"""Consultas SQL de cheques."""

from __future__ import annotations

import sqlite3
from decimal import Decimal


def insertar_cheque(
    conexion: sqlite3.Connection,
    numero: str,
    cliente_id: int,
    banco: str | None,
    monto: Decimal,
    fecha_cobro: str,
    recibo_origen_id: int | None,
    estado: str = "en_cartera",
) -> int:
    cursor = conexion.execute(
        """
        INSERT INTO cheques
            (numero, cliente_id, banco, monto, fecha_cobro, recibo_origen_id, estado)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (numero, cliente_id, banco, monto, fecha_cobro, recibo_origen_id, estado),
    )
    return cursor.lastrowid


def obtener_cheque(conexion: sqlite3.Connection, cheque_id: int) -> sqlite3.Row | None:
    return conexion.execute("SELECT * FROM cheques WHERE id = ?", (cheque_id,)).fetchone()


def marcar_estado_cheque(conexion: sqlite3.Connection, cheque_id: int, estado: str) -> None:
    conexion.execute("UPDATE cheques SET estado = ? WHERE id = ?", (estado, cheque_id))


def listar_cheques_de_recibo_origen(
    conexion: sqlite3.Connection, recibo_id: int
) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT * FROM cheques WHERE recibo_origen_id = ? ORDER BY id", (recibo_id,)
    ).fetchall()


def listar_cheques_en_cartera(conexion: sqlite3.Connection) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT * FROM cheques WHERE estado = 'en_cartera' ORDER BY fecha_cobro"
    ).fetchall()
