"""Módulo de recibos: listado de solo lectura de los recibos emitidos
(docs/AJUSTES_V1.1.md, módulo de recibos)."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services.cobranzas import AplicacionARemito, Pago, anular_recibo, asentar_cobranza
from ios.services.listado_recibos import listado_recibos


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "ios_test.db")
    try:
        yield conexion
    finally:
        conexion.close()


@pytest.fixture
def formas_pago(conexion) -> dict[str, int]:
    filas = conexion.execute("SELECT id, nombre FROM formas_pago").fetchall()
    return {fila["nombre"]: fila["id"] for fila in filas}


@pytest.fixture
def rto_id(conexion) -> int:
    return conexion.execute(
        "SELECT id FROM tipos_comprobante WHERE abreviatura = 'RTO'"
    ).fetchone()["id"]


def _nueva_sucursal(conexion, cliente_id):
    return conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]


def test_listado_recibos_sin_filtros_trae_todos_con_aplicado_y_pendiente(
    conexion, rto_id, formas_pago
):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    sucursal_id = _nueva_sucursal(conexion, cliente_id)
    remito_id = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-01", cliente_id, sucursal_id, Decimal("1000")
    )
    asentar_cobranza(
        conexion, cliente_id, "2024-03-05",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1500"))],
        aplicaciones=[AplicacionARemito(remito_id, Decimal("1000"))],
    )

    recibos = listado_recibos(conexion)

    assert len(recibos) == 1
    recibo = recibos[0]
    assert recibo.cliente_nombre == "Croma"
    assert recibo.monto_total == Decimal("1500")
    assert recibo.aplicado == Decimal("1000")
    assert recibo.pendiente == Decimal("500")
    assert recibo.origen == "manual"
    assert recibo.estado == "vigente"


def test_listado_recibos_filtra_por_cliente(conexion, rto_id, formas_pago):
    croma_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    mirage_id = servicio_clientes.alta_cliente(
        conexion, nombre="Mirage", descuento_default=Decimal("0"), con_iva_default=False
    )
    asentar_cobranza(
        conexion, croma_id, "2024-03-05", pagos=[Pago(formas_pago["Efectivo"], Decimal("100"))],
        aplicaciones=[],
    )
    asentar_cobranza(
        conexion, mirage_id, "2024-03-06", pagos=[Pago(formas_pago["Efectivo"], Decimal("200"))],
        aplicaciones=[],
    )

    recibos = listado_recibos(conexion, cliente_id=croma_id)

    assert len(recibos) == 1
    assert recibos[0].cliente_nombre == "Croma"


def test_listado_recibos_filtra_por_rango_de_fechas(conexion, rto_id, formas_pago):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    asentar_cobranza(
        conexion, cliente_id, "2024-02-15", pagos=[Pago(formas_pago["Efectivo"], Decimal("100"))],
        aplicaciones=[],
    )
    asentar_cobranza(
        conexion, cliente_id, "2024-03-15", pagos=[Pago(formas_pago["Efectivo"], Decimal("200"))],
        aplicaciones=[],
    )

    recibos = listado_recibos(conexion, fecha_desde="2024-03-01", fecha_hasta="2024-03-31")

    assert len(recibos) == 1
    assert recibos[0].monto_total == Decimal("200")


def test_listado_recibos_filtra_por_estado(conexion, rto_id, formas_pago):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    vigente_id = asentar_cobranza(
        conexion, cliente_id, "2024-03-05", pagos=[Pago(formas_pago["Efectivo"], Decimal("100"))],
        aplicaciones=[],
    )
    anulado_id = asentar_cobranza(
        conexion, cliente_id, "2024-03-06", pagos=[Pago(formas_pago["Efectivo"], Decimal("200"))],
        aplicaciones=[],
    )
    anular_recibo(conexion, anulado_id, "2024-03-07")

    vigentes = listado_recibos(conexion, estado="vigente")
    anulados = listado_recibos(conexion, estado="anulado")

    assert [r.recibo_id for r in vigentes] == [vigente_id]
    assert [r.recibo_id for r in anulados] == [anulado_id]
