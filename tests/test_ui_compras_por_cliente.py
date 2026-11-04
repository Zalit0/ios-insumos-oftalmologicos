"""Pruebas funcionales de la pantalla Compras por cliente: ranking de
todos los clientes por defecto, y detalle por cliente al elegirlo
(docs/AJUSTES_V1.1.md, etapa 6.1)."""

import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.ui.pages.compras_por_cliente import PaginaComprasPorCliente


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


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


def test_por_defecto_muestra_el_ranking(app, conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", conexion.execute("SELECT date('now')").fetchone()[0],
        cliente_id, sucursal_id, Decimal("1000"),
    )

    pagina = PaginaComprasPorCliente(conexion)

    assert pagina._tabla.columnCount() == 3
    assert pagina._campo_sucursal.isHidden() is True


def test_elegir_cliente_muestra_el_detalle(app, conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    hoy = conexion.execute("SELECT date('now')").fetchone()[0]
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", hoy, cliente_id, sucursal_id, Decimal("1000")
    )

    pagina = PaginaComprasPorCliente(conexion)
    pagina._al_elegir_cliente(cliente_id)

    assert pagina._tabla.columnCount() == 8
    assert pagina._tabla.rowCount() == 1
    assert pagina._tabla.item(0, 1).text() == "1"


def test_ver_todos_vuelve_al_ranking(app, conexion):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")

    pagina = PaginaComprasPorCliente(conexion)
    pagina._al_elegir_cliente(cliente_id)
    assert pagina._tabla.columnCount() == 8

    pagina._ver_todos()

    assert pagina._tabla.columnCount() == 3
    assert pagina._cliente_id is None


def test_sucursal_visible_solo_con_cliente_elegido(app, conexion):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", sucursales=["Croma", "Croma Fdez."]
    )

    pagina = PaginaComprasPorCliente(conexion)
    assert pagina._campo_sucursal.isHidden() is True

    pagina._al_elegir_cliente(cliente_id)
    assert pagina._campo_sucursal.isHidden() is False
    assert pagina._campo_sucursal.count() == 3  # "Todas" + 2 sucursales
