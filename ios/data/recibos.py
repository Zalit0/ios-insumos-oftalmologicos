"""Consultas SQL de recibos, recibo_pagos y aplicaciones_pago. Sin lógica
de negocio: eso vive en ios/services/cobranzas.py."""

from __future__ import annotations

import sqlite3
from decimal import Decimal


def siguiente_numero_recibo(conexion: sqlite3.Connection) -> int:
    """Número inicial configurable; si ya existe, usa el inmediato superior
    libre (docs/PLAN.md, "Integridad")."""
    numero_inicial = conexion.execute(
        "SELECT numero_inicial_recibo FROM configuracion WHERE id = 1"
    ).fetchone()["numero_inicial_recibo"]
    maximo_actual = conexion.execute("SELECT MAX(numero) AS maximo FROM recibos").fetchone()[
        "maximo"
    ]

    if maximo_actual is None:
        return numero_inicial
    return max(numero_inicial, maximo_actual + 1)


def existe_numero_recibo(conexion: sqlite3.Connection, numero: int) -> bool:
    return conexion.execute(
        "SELECT 1 FROM recibos WHERE numero = ?", (numero,)
    ).fetchone() is not None


def insertar_recibo(
    conexion: sqlite3.Connection,
    numero: int,
    fecha: str,
    cliente_id: int,
    monto_total: Decimal,
    origen: str = "manual",
    referencia: str | None = None,
) -> int:
    cursor = conexion.execute(
        """
        INSERT INTO recibos (numero, fecha, cliente_id, monto_total, origen, referencia, estado)
        VALUES (?, ?, ?, ?, ?, ?, 'vigente')
        """,
        (numero, fecha, cliente_id, monto_total, origen, referencia),
    )
    return cursor.lastrowid


def obtener_recibo(conexion: sqlite3.Connection, recibo_id: int) -> sqlite3.Row | None:
    return conexion.execute("SELECT * FROM recibos WHERE id = ?", (recibo_id,)).fetchone()


def marcar_estado_recibo(conexion: sqlite3.Connection, recibo_id: int, estado: str) -> None:
    conexion.execute("UPDATE recibos SET estado = ? WHERE id = ?", (estado, recibo_id))


def listar_recibos_vigentes_cliente(
    conexion: sqlite3.Connection, cliente_id: int
) -> list[sqlite3.Row]:
    return conexion.execute(
        """
        SELECT * FROM recibos
        WHERE cliente_id = ? AND estado = 'vigente'
        ORDER BY fecha, id
        """,
        (cliente_id,),
    ).fetchall()


def insertar_recibo_pago(
    conexion: sqlite3.Connection,
    recibo_id: int,
    forma_pago_id: int,
    monto: Decimal,
    cheque_id: int | None = None,
) -> int:
    cursor = conexion.execute(
        """
        INSERT INTO recibo_pagos (recibo_id, forma_pago_id, monto, cheque_id)
        VALUES (?, ?, ?, ?)
        """,
        (recibo_id, forma_pago_id, monto, cheque_id),
    )
    return cursor.lastrowid


def listar_recibo_pagos(conexion: sqlite3.Connection, recibo_id: int) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT * FROM recibo_pagos WHERE recibo_id = ? ORDER BY id", (recibo_id,)
    ).fetchall()


def insertar_aplicacion_pago(
    conexion: sqlite3.Connection, recibo_id: int, comprobante_id: int, monto_aplicado: Decimal
) -> int:
    cursor = conexion.execute(
        """
        INSERT INTO aplicaciones_pago (recibo_id, comprobante_id, monto_aplicado)
        VALUES (?, ?, ?)
        """,
        (recibo_id, comprobante_id, monto_aplicado),
    )
    return cursor.lastrowid


def listar_aplicaciones_de_recibo(conexion: sqlite3.Connection, recibo_id: int) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT * FROM aplicaciones_pago WHERE recibo_id = ? ORDER BY id", (recibo_id,)
    ).fetchall()


def listar_aplicaciones_de_comprobante(
    conexion: sqlite3.Connection, comprobante_id: int
) -> list[sqlite3.Row]:
    return conexion.execute(
        "SELECT * FROM aplicaciones_pago WHERE comprobante_id = ? ORDER BY id", (comprobante_id,)
    ).fetchall()


def total_aplicado_a_comprobante(conexion: sqlite3.Connection, comprobante_id: int) -> Decimal:
    """Suma solo lo aplicado desde recibos vigentes: un recibo anulado
    libera el saldo que cubría (docs/PLAN.md, "Integridad")."""
    filas = conexion.execute(
        """
        SELECT ap.monto_aplicado AS monto FROM aplicaciones_pago ap
        JOIN recibos r ON r.id = ap.recibo_id
        WHERE ap.comprobante_id = ? AND r.estado = 'vigente'
        """,
        (comprobante_id,),
    ).fetchall()
    return sum((fila["monto"] for fila in filas), Decimal(0))


def total_aplicado_de_recibo(conexion: sqlite3.Connection, recibo_id: int) -> Decimal:
    filas = conexion.execute(
        "SELECT monto_aplicado AS monto FROM aplicaciones_pago WHERE recibo_id = ?",
        (recibo_id,),
    ).fetchall()
    return sum((fila["monto"] for fila in filas), Decimal(0))


def total_monto_recibos_vigentes_cliente(conexion: sqlite3.Connection, cliente_id: int) -> Decimal:
    filas = conexion.execute(
        "SELECT monto_total AS monto FROM recibos WHERE cliente_id = ? AND estado = 'vigente'",
        (cliente_id,),
    ).fetchall()
    return sum((fila["monto"] for fila in filas), Decimal(0))


def total_aplicado_de_recibos_cliente(conexion: sqlite3.Connection, cliente_id: int) -> Decimal:
    filas = conexion.execute(
        """
        SELECT ap.monto_aplicado AS monto FROM aplicaciones_pago ap
        JOIN recibos r ON r.id = ap.recibo_id
        WHERE r.cliente_id = ? AND r.estado = 'vigente'
        """,
        (cliente_id,),
    ).fetchall()
    return sum((fila["monto"] for fila in filas), Decimal(0))


def listar_recibos(
    conexion: sqlite3.Connection,
    cliente_id: int | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    estado: str | None = None,
) -> list[sqlite3.Row]:
    """Listado general de recibos (todos los clientes salvo que se
    filtre), con el nombre del cliente, para la pantalla de Recibos
    emitidos (docs/AJUSTES_V1.1.md, módulo de recibos). Sin filtros,
    devuelve todos."""
    condiciones = []
    parametros: list = []

    if cliente_id is not None:
        condiciones.append("r.cliente_id = ?")
        parametros.append(cliente_id)
    if fecha_desde is not None:
        condiciones.append("r.fecha >= ?")
        parametros.append(fecha_desde)
    if fecha_hasta is not None:
        condiciones.append("r.fecha <= ?")
        parametros.append(fecha_hasta)
    if estado is not None:
        condiciones.append("r.estado = ?")
        parametros.append(estado)

    sql = "SELECT r.*, c.nombre AS cliente_nombre FROM recibos r JOIN clientes c ON c.id = r.cliente_id"
    if condiciones:
        sql += " WHERE " + " AND ".join(condiciones)
    sql += " ORDER BY r.fecha, r.id"

    return conexion.execute(sql, parametros).fetchall()


def listar_recibos_vigentes_entre(
    conexion: sqlite3.Connection, fecha_desde: str, fecha_hasta: str
) -> list[sqlite3.Row]:
    """Recibos vigentes de todos los clientes con fecha entre
    ``fecha_desde`` y ``fecha_hasta`` (ambos incluidos), por su propia
    fecha de cobro (docs/AJUSTES_V1.1.md, Dashboard: la cobranza se mide
    por la fecha del recibo, no por la del remito que cubre)."""
    return conexion.execute(
        """
        SELECT * FROM recibos
        WHERE estado = 'vigente' AND fecha BETWEEN ? AND ?
        ORDER BY fecha, id
        """,
        (fecha_desde, fecha_hasta),
    ).fetchall()


def listar_recibos_cliente_entre(
    conexion: sqlite3.Connection, cliente_id: int, fecha_desde: str, fecha_hasta: str
) -> list[sqlite3.Row]:
    """Recibos vigentes del cliente con fecha entre ``fecha_desde`` y
    ``fecha_hasta`` (ambos incluidos): movimientos de cobro de un período
    de la cuenta corriente."""
    return conexion.execute(
        """
        SELECT * FROM recibos
        WHERE cliente_id = ? AND estado = 'vigente' AND fecha BETWEEN ? AND ?
        ORDER BY fecha, id
        """,
        (cliente_id, fecha_desde, fecha_hasta),
    ).fetchall()
