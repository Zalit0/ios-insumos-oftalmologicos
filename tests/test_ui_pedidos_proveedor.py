"""Pruebas funcionales de la pantalla Pedidos a proveedor (plan de detalle
de comprobantes, etapa 4): armar el pedido "en carga" de un proveedor
(reposición, especiales) y marcarlo realizado. Recibir y consultar pedidos
viejos son pantallas aparte (Recepción de pedidos, Ver pedidos)."""

import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate, QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services import proveedores as servicio_proveedores
from ios.services.comprobantes import RenglonDetalle
from ios.services.tipos_cristal import alta_tipo_cristal
from ios.ui.pages.pedidos_proveedor import PaginaPedidosProveedor


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


def _enter(widget):
    evento = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    QApplication.sendEvent(widget, evento)


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "ios_test.db")
    try:
        yield conexion
    finally:
        conexion.close()


@pytest.fixture
def rto_id(conexion) -> int:
    return conexion.execute(
        "SELECT id FROM tipos_comprobante WHERE abreviatura = 'RTO'"
    ).fetchone()["id"]


@pytest.fixture
def proveedor_id(conexion) -> int:
    return servicio_proveedores.alta_proveedor(conexion, nombre="Essilor")


@pytest.fixture
def croma(conexion):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"),
        con_iva_default=False, sucursales=["Croma"],
    )
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ? AND nombre = 'Croma'", (cliente_id,)
    ).fetchone()["id"]
    return cliente_id, sucursal_id


def test_elegir_proveedor_sin_pedido_en_carga(app, conexion, proveedor_id):
    pagina = PaginaPedidosProveedor(conexion)

    assert pagina._pedido_id is None
    assert pagina._etiqueta_pedido.text() == "Sin pedido en carga"
    assert not pagina._boton_marcar_realizado.isEnabled()


def test_nuevo_pedido_lo_deja_seleccionado(app, conexion, proveedor_id):
    pagina = PaginaPedidosProveedor(conexion)

    pagina._nuevo_pedido()

    assert pagina._pedido_id is not None
    assert pagina._boton_marcar_realizado.isEnabled()


def test_nuevo_pedido_no_duplica_si_ya_hay_uno_en_carga(app, conexion, proveedor_id):
    pagina = PaginaPedidosProveedor(conexion)
    pagina._nuevo_pedido()
    primero_id = pagina._pedido_id

    pagina._nuevo_pedido()

    assert pagina._pedido_id == primero_id


def test_cambiar_de_proveedor_vuelve_a_mostrar_su_pedido_en_carga(app, conexion, proveedor_id):
    otro_proveedor_id = servicio_proveedores.alta_proveedor(conexion, nombre="Lentex")
    pagina = PaginaPedidosProveedor(conexion)
    pagina._nuevo_pedido()
    pedido_essilor_id = pagina._pedido_id

    indice_otro = pagina._campo_proveedor.findData(otro_proveedor_id)
    pagina._campo_proveedor.setCurrentIndex(indice_otro)

    assert pagina._pedido_id is None  # Lentex todavía no tiene pedido en carga

    indice_essilor = pagina._campo_proveedor.findData(proveedor_id)
    pagina._campo_proveedor.setCurrentIndex(indice_essilor)

    assert pagina._pedido_id == pedido_essilor_id


def test_generar_reposicion_trae_lo_vendido(monkeypatch, app, conexion, proveedor_id, rto_id, croma):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    cliente_id, sucursal_id = croma
    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    servicio_comprobantes.alta_comprobante_con_detalle(
        conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
        renglones=[RenglonDetalle(graduacion="Neutro", cantidad=2, tipo_cristal_id=organico)],
    )
    pagina = PaginaPedidosProveedor(conexion)
    pagina._nuevo_pedido()
    pagina._campo_repo_desde.setDate(QDate(2026, 3, 1))
    pagina._campo_repo_hasta.setDate(QDate(2026, 3, 31))

    pagina._generar_reposicion()

    assert pagina._tabla_reposicion.rowCount() == 1
    assert pagina._tabla_reposicion.item(0, 0).text() == "Orgánico blanco"


def test_agregar_linea_especial_la_muestra_en_la_tabla(app, conexion, proveedor_id, croma):
    cliente_id, _ = croma
    pagina = PaginaPedidosProveedor(conexion)
    pagina._nuevo_pedido()
    pagina._campo_especial_descripcion.setText("Ultravex 1.74")
    pagina._campo_especial_cantidad.setValue(1)
    indice_cliente = pagina._campo_especial_cliente.findData(cliente_id)
    pagina._campo_especial_cliente.setCurrentIndex(indice_cliente)

    pagina._agregar_linea_especial()

    assert pagina._tabla_especiales.rowCount() == 1
    assert pagina._tabla_especiales.item(0, 0).text() == "Ultravex 1.74"
    assert pagina._tabla_especiales.item(0, 1).text() == "Croma"
    assert pagina._campo_especial_descripcion.text() == ""  # se blanquea tras agregar


def test_marcar_realizado_vacia_el_pedido_en_carga(monkeypatch, app, conexion, proveedor_id, tmp_path):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(
        "ios.ui.pages.pedidos_proveedor.ruta_pdf_automatica", lambda nombre, subcarpeta=None: tmp_path / nombre
    )
    monkeypatch.setattr("ios.ui.pages.pedidos_proveedor.abrir_pdf", lambda ruta: None)
    pagina = PaginaPedidosProveedor(conexion)
    pagina._nuevo_pedido()
    pagina._campo_especial_descripcion.setText("Cristal")
    pagina._agregar_linea_especial()

    pagina._marcar_pedido_realizado()

    assert pagina._pedido_id is None
    assert pagina._etiqueta_pedido.text() == "Sin pedido en carga"
    assert not pagina._boton_marcar_realizado.isEnabled()
    assert pagina._tabla_especiales.rowCount() == 0


def test_marcar_realizado_genera_y_abre_el_pdf(monkeypatch, app, conexion, proveedor_id, tmp_path):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(
        "ios.ui.pages.pedidos_proveedor.ruta_pdf_automatica", lambda nombre, subcarpeta=None: tmp_path / nombre
    )
    rutas_abiertas = []
    monkeypatch.setattr("ios.ui.pages.pedidos_proveedor.abrir_pdf", lambda ruta: rutas_abiertas.append(ruta))

    pagina = PaginaPedidosProveedor(conexion)
    pagina._nuevo_pedido()
    pagina._campo_especial_descripcion.setText("Ultravex 1.74")
    pagina._agregar_linea_especial()

    pagina._marcar_pedido_realizado()

    assert len(rutas_abiertas) == 1
    assert rutas_abiertas[0].exists()


def test_linea_especial_arma_la_graduacion_con_esferico_y_cilindrico(app, conexion, proveedor_id):
    pagina = PaginaPedidosProveedor(conexion)
    pagina._nuevo_pedido()
    pagina._campo_especial_descripcion.setText("Ultravex 1.74")
    pagina._campo_especial_esferico.setValue(-8.00)
    pagina._campo_especial_cilindrico.setValue(-1.50)

    pagina._agregar_linea_especial()

    assert pagina._tabla_especiales.item(0, 3).text() == "ESF -8.00 CIL -1.50"
    # se blanquea tras agregar, lista para la próxima
    assert pagina._campo_especial_esferico.value() == pytest.approx(0.0)
    assert pagina._campo_especial_cilindrico.value() == pytest.approx(0.0)


def test_linea_especial_sin_tocar_esferico_ni_cilindrico_queda_neutro(app, conexion, proveedor_id):
    pagina = PaginaPedidosProveedor(conexion)
    pagina._nuevo_pedido()
    pagina._campo_especial_descripcion.setText("Cristal")

    pagina._agregar_linea_especial()

    assert pagina._tabla_especiales.item(0, 3).text() == "Neutro"


def test_enter_avanza_de_campo_en_campo_y_al_final_agrega(app, conexion, proveedor_id):
    pagina = PaginaPedidosProveedor(conexion)
    pagina.show()
    pagina.activateWindow()
    pagina._nuevo_pedido()
    pagina._campo_especial_descripcion.setText("Ultravex 1.74")

    pagina._campo_especial_tipo.setFocus()
    app.processEvents()
    _enter(pagina._campo_especial_tipo)
    app.processEvents()
    assert pagina._campo_especial_descripcion.hasFocus()

    _enter(pagina._campo_especial_descripcion)
    app.processEvents()
    assert pagina._campo_especial_cliente.hasFocus()

    _enter(pagina._campo_especial_cliente)
    app.processEvents()
    assert pagina._campo_especial_esferico.hasFocus()

    _enter(pagina._campo_especial_esferico)
    app.processEvents()
    assert pagina._campo_especial_cilindrico.hasFocus()

    _enter(pagina._campo_especial_cilindrico)
    app.processEvents()
    assert pagina._campo_especial_cantidad.hasFocus()

    _enter(pagina._campo_especial_cantidad)
    app.processEvents()

    assert pagina._tabla_especiales.rowCount() == 1
    assert pagina._tabla_especiales.item(0, 0).text() == "Ultravex 1.74"
