"""Etapa 6.1: reporte "Compras por cliente"."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services.cobranzas import AplicacionARemito, Pago, asentar_cobranza
from ios.services.compras_por_cliente import compras_de_cliente, ranking_todos_los_clientes


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "ios_test.db")
    try:
        yield conexion
    finally:
        conexion.close()


@pytest.fixture
def rto_id(conexion) -> int:
    return conexion.execute("SELECT id FROM tipos_comprobante WHERE abreviatura = 'RTO'").fetchone()["id"]


@pytest.fixture
def efectivo_id(conexion) -> int:
    return conexion.execute("SELECT id FROM formas_pago WHERE nombre = 'Efectivo'").fetchone()["id"]


def test_compras_de_cliente_sin_comprobantes(conexion):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")

    resultado = compras_de_cliente(conexion, cliente_id, "2024-03-01", "2024-03-31")

    assert resultado.filas == []
    assert resultado.cantidad == 0
    assert resultado.total_final == Decimal("0")


def test_compras_de_cliente_suma_totales(conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]

    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_id, Decimal("10000")
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-03-10", cliente_id, sucursal_id, Decimal("5000")
    )

    resultado = compras_de_cliente(conexion, cliente_id, "2024-03-01", "2024-03-31")

    assert resultado.cantidad == 2
    assert resultado.total_lista == Decimal("15000")
    assert resultado.total_final == Decimal("15000")
    assert resultado.subtotales_por_sucursal == []  # una sola sucursal


def test_compras_de_cliente_filtra_por_fecha(conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-02-20", cliente_id, sucursal_id, Decimal("1000")
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-03-10", cliente_id, sucursal_id, Decimal("2000")
    )

    resultado = compras_de_cliente(conexion, cliente_id, "2024-03-01", "2024-03-31")

    assert resultado.cantidad == 1
    assert resultado.total_lista == Decimal("2000")


def test_compras_de_cliente_subtotal_por_sucursal(conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", sucursales=["Croma", "Croma Fdez."]
    )
    sucursales = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ? ORDER BY id", (cliente_id,)
    ).fetchall()
    sucursal_a, sucursal_b = sucursales[0]["id"], sucursales[1]["id"]

    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_a, Decimal("1000")
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-03-06", cliente_id, sucursal_b, Decimal("4000")
    )

    resultado = compras_de_cliente(conexion, cliente_id, "2024-03-01", "2024-03-31")

    assert len(resultado.subtotales_por_sucursal) == 2
    subtotal_a = next(s for s in resultado.subtotales_por_sucursal if s.sucursal_id == sucursal_a)
    assert subtotal_a.monto_final == Decimal("1000")
    assert subtotal_a.cantidad == 1


def test_compras_de_cliente_filtra_por_sucursal(conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", sucursales=["Croma", "Croma Fdez."]
    )
    sucursales = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ? ORDER BY id", (cliente_id,)
    ).fetchall()
    sucursal_a, sucursal_b = sucursales[0]["id"], sucursales[1]["id"]
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_a, Decimal("1000")
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-03-06", cliente_id, sucursal_b, Decimal("4000")
    )

    resultado = compras_de_cliente(
        conexion, cliente_id, "2024-03-01", "2024-03-31", sucursal_id=sucursal_a
    )

    assert resultado.cantidad == 1
    assert resultado.total_final == Decimal("1000")


def test_compras_de_cliente_calcula_cobrado_y_pendiente(conexion, rto_id, efectivo_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    comprobante_id = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_id, Decimal("10000")
    )
    asentar_cobranza(
        conexion, cliente_id, "2024-03-10",
        pagos=[Pago(efectivo_id, Decimal("4000"))],
        aplicaciones=[AplicacionARemito(comprobante_id, Decimal("4000"))],
    )

    resultado = compras_de_cliente(conexion, cliente_id, "2024-03-01", "2024-03-31")

    assert resultado.total_cobrado == Decimal("4000")
    assert resultado.total_pendiente == Decimal("6000")


def test_compras_de_cliente_inexistente_falla(conexion):
    with pytest.raises(ValueError):
        compras_de_cliente(conexion, 9999, "2024-03-01", "2024-03-31")


def test_ranking_ordena_de_mayor_a_menor(conexion, rto_id):
    croma_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    mirage_id = servicio_clientes.alta_cliente(conexion, nombre="Mirage")
    sucursal_croma = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (croma_id,)
    ).fetchone()["id"]
    sucursal_mirage = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (mirage_id,)
    ).fetchone()["id"]

    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", croma_id, sucursal_croma, Decimal("1000")
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-03-06", mirage_id, sucursal_mirage, Decimal("5000")
    )

    ranking = ranking_todos_los_clientes(conexion, "2024-03-01", "2024-03-31")

    assert [f.nombre for f in ranking] == ["Mirage", "Croma"]


def test_ranking_omite_clientes_sin_movimientos(conexion):
    servicio_clientes.alta_cliente(conexion, nombre="Croma")

    ranking = ranking_todos_los_clientes(conexion, "2024-03-01", "2024-03-31")

    assert ranking == []
