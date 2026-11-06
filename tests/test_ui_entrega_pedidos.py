"""Pruebas funcionales de la pantalla Entrega de pedidos especiales (plan de
detalle de comprobantes, etapa 5): generar un comprobante con las líneas
especiales ya recibidas de un cliente."""

import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services import proveedores as servicio_proveedores
from ios.services.pedidos_proveedor import agregar_linea_especial, alta_pedido, marcar_linea_recibida
from ios.ui.pages.entrega_pedidos import PaginaEntregaPedidos


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
def proveedor_id(conexion) -> int:
    return servicio_proveedores.alta_proveedor(conexion, nombre="Essilor")


@pytest.fixture
def croma(conexion):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"),
        con_iva_default=False, sucursales=["Croma"],
    )
    return cliente_id


def test_sin_lineas_pendientes_combo_vacio(app, conexion):
    pagina = PaginaEntregaPedidos(conexion)

    assert pagina._campo_cliente.count() == 0


def test_lista_linea_lista_para_entregar(app, conexion, proveedor_id, croma):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    linea_id = agregar_linea_especial(
        conexion, pedido_id, cantidad=1, descripcion="Ultravex 1.74", cliente_id=croma,
        graduacion_solicitada="-2.00",
    )
    marcar_linea_recibida(conexion, linea_id, graduacion_recibida="-2.00")

    pagina = PaginaEntregaPedidos(conexion)

    assert pagina._campo_cliente.count() == 1
    assert pagina._tabla_listas.rowCount() == 1
    assert pagina._tabla_listas.item(0, 1).text() == "Ultravex 1.74"


def test_linea_recibida_con_graduacion_distinta_igual_queda_lista(app, conexion, proveedor_id, croma):
    """Si llegó y se marcó recibida es porque el cliente la aceptó así —
    no hay ningún paso de aprobación extra antes de poder entregarla."""
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    linea_id = agregar_linea_especial(
        conexion, pedido_id, cantidad=1, descripcion="Cristal", cliente_id=croma,
        graduacion_solicitada="-2.00",
    )
    marcar_linea_recibida(conexion, linea_id, graduacion_recibida="-2.25")

    pagina = PaginaEntregaPedidos(conexion)

    assert pagina._tabla_listas.rowCount() == 1
    assert pagina._tabla_listas.item(0, 3).text() == "-2.25"


def test_generar_comprobante_con_una_linea_tildada(monkeypatch, app, conexion, proveedor_id, croma):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    linea_id = agregar_linea_especial(
        conexion, pedido_id, cantidad=1, descripcion="Ultravex 1.74", cliente_id=croma,
        graduacion_solicitada="-2.00",
    )
    marcar_linea_recibida(conexion, linea_id, graduacion_recibida="-2.00")
    pagina = PaginaEntregaPedidos(conexion)
    pagina._tabla_listas.item(0, 0).setCheckState(Qt.Checked)
    pagina._tabla_listas.item(0, 4).setText("5000")

    pagina._generar_comprobante()

    assert pagina._tabla_listas.rowCount() == 0
    comprobantes = servicio_comprobantes.listar_comprobantes(conexion, cliente_id=croma)
    assert len(comprobantes) == 1


def test_generar_comprobante_sin_tildar_nada_avisa(monkeypatch, app, conexion, proveedor_id, croma):
    avisos = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: avisos.append(a) or QMessageBox.Ok)
    )
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    linea_id = agregar_linea_especial(
        conexion, pedido_id, cantidad=1, descripcion="Ultravex 1.74", cliente_id=croma,
        graduacion_solicitada="-2.00",
    )
    marcar_linea_recibida(conexion, linea_id, graduacion_recibida="-2.00")
    pagina = PaginaEntregaPedidos(conexion)

    pagina._generar_comprobante()

    assert len(avisos) == 1
    assert pagina._tabla_listas.rowCount() == 1
