"""Pruebas funcionales de la pantalla Facturación (docs/AJUSTES_V1.1.md,
etapa 2.1): elegir cliente, sucursal/particular dinámicos, cálculo en
vivo, guardar con Enter, editar y anular desde la tabla de la sesión, y
reinicio al cambiar de cliente o salir de la pantalla."""

import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from ios.data import comprobantes as datos_comprobantes
from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services.cobranzas import AplicacionARemito, Pago, asentar_cobranza
from ios.ui.pages.facturacion import PaginaFacturacion


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


def _enter(widget):
    evento = QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)
    QApplication.sendEvent(widget, evento)


def test_elegir_cliente_con_una_sola_sucursal_no_muestra_el_selector(app, conexion):
    servicio_clientes.alta_cliente(conexion, nombre="Croma")
    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados

    pagina.buscador.campo.setText("Croma")
    pagina.buscador._al_elegir_texto("Croma")

    assert pagina._cliente_id is not None
    assert pagina._mostrar_sucursal is False
    assert pagina.campo_numero.isEnabled()


def test_elegir_cliente_con_dos_sucursales_muestra_el_selector(app, conexion):
    servicio_clientes.alta_cliente(conexion, nombre="Croma", sucursales=["Croma", "Croma Fdez."])
    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados

    pagina.buscador._al_elegir_texto("Croma")

    assert pagina._mostrar_sucursal is True
    assert pagina.campo_sucursal.count() == 2


def test_particulares_muestra_el_campo_de_nombre(app, conexion):
    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados
    pagina.buscador._al_elegir_texto("Particulares")

    assert pagina._mostrar_particular is True


def test_buscador_encuentra_sin_distinguir_mayusculas_ni_acentos(app, conexion):
    servicio_clientes.alta_cliente(conexion, nombre="ÓPTICA CIUDAD")
    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados

    pagina.buscador._actualizar_sugerencias("optica")

    nombres = pagina.buscador._completer.model().stringList()
    assert "ÓPTICA CIUDAD" in nombres


def test_calculo_en_vivo(app, conexion):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("25"), con_iva_default=True
    )
    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados
    pagina._al_elegir_cliente(cliente_id)

    pagina.campo_monto_lista.setValue(104544)

    assert pagina.etiqueta_final.text() == "$ 78.408,00"
    assert pagina.etiqueta_iva.text() == "$ 13.608,00"


def test_guardar_agrega_a_la_tabla_de_la_sesion_y_limpia_el_formulario(app, conexion):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("25"), con_iva_default=True
    )
    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados
    pagina._al_elegir_cliente(cliente_id)

    pagina.campo_numero.setText("1")
    pagina.campo_monto_lista.setValue(104544)
    pagina._guardar()

    assert pagina.tabla_sesion.rowCount() == 1
    assert pagina.campo_numero.text() == ""  # se limpia tras guardar
    assert pagina.campo_tipo.currentData() is not None  # cliente/tipo se mantienen
    assert pagina._cliente_id == cliente_id


def test_enter_en_monto_lista_avanza_a_descuento(app, conexion):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados
    pagina.activateWindow()
    pagina._al_elegir_cliente(cliente_id)

    pagina.campo_monto_lista.setFocus()
    app.processEvents()
    _enter(pagina.campo_monto_lista)
    app.processEvents()

    assert pagina.campo_descuento.hasFocus()


def test_enter_en_con_iva_guarda(app, conexion):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados
    pagina._al_elegir_cliente(cliente_id)
    pagina.campo_numero.setText("1")
    pagina.campo_monto_lista.setValue(1000)

    _enter(pagina.campo_con_iva)

    assert pagina.tabla_sesion.rowCount() == 1


def test_editar_seleccionado_carga_el_formulario(app, conexion):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados
    pagina._al_elegir_cliente(cliente_id)
    pagina.campo_numero.setText("1")
    pagina.campo_monto_lista.setValue(1000)
    pagina._guardar()

    pagina.tabla_sesion.selectRow(0)
    pagina._editar_seleccionado()

    assert pagina._comprobante_en_edicion == pagina._ids_sesion[0]
    assert pagina.campo_numero.text() == "1"
    assert pagina.boton_cancelar_edicion.isVisible()


def test_editar_actualiza_la_fila_en_vez_de_crear_otra(app, conexion):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados
    pagina._al_elegir_cliente(cliente_id)
    pagina.campo_numero.setText("1")
    pagina.campo_monto_lista.setValue(1000)
    pagina._guardar()

    pagina.tabla_sesion.selectRow(0)
    pagina._editar_seleccionado()
    pagina.campo_numero.setText("2")
    pagina._guardar()

    assert len(pagina._ids_sesion) == 1
    assert pagina.tabla_sesion.rowCount() == 1
    assert pagina.tabla_sesion.item(0, 0).text() == "2"


def test_comprobante_con_pagos_aplicados_bloquea_monto_descuento_iva(monkeypatch, app, conexion):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))

    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    efectivo_id = conexion.execute(
        "SELECT id FROM formas_pago WHERE nombre = 'Efectivo'"
    ).fetchone()["id"]

    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados
    pagina._al_elegir_cliente(cliente_id)
    pagina.campo_numero.setText("1")
    pagina.campo_monto_lista.setValue(1000)
    pagina._guardar()
    comprobante_id = pagina._ids_sesion[0]

    asentar_cobranza(
        conexion, cliente_id, "2024-03-10",
        pagos=[Pago(efectivo_id, Decimal("1000"))],
        aplicaciones=[AplicacionARemito(comprobante_id, Decimal("1000"))],
    )

    pagina.tabla_sesion.selectRow(0)
    pagina._editar_seleccionado()

    assert not pagina.campo_monto_lista.isEnabled()
    assert not pagina.campo_descuento.isEnabled()
    assert not pagina.campo_con_iva.isEnabled()
    assert pagina.campo_numero.isEnabled()
    assert pagina.campo_fecha.isEnabled()


def test_anular_seleccionado_lo_quita_de_la_tabla(monkeypatch, app, conexion):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados
    pagina._al_elegir_cliente(cliente_id)
    pagina.campo_numero.setText("1")
    pagina.campo_monto_lista.setValue(1000)
    pagina._guardar()
    comprobante_id = pagina._ids_sesion[0]

    pagina.tabla_sesion.selectRow(0)
    pagina._anular_seleccionado()

    assert pagina.tabla_sesion.rowCount() == 0
    comprobante = datos_comprobantes.obtener_comprobante(conexion, comprobante_id)
    assert comprobante["estado"] == "anulado"


def test_cambiar_de_cliente_vacia_la_sesion(app, conexion):
    croma_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    mirage_id = servicio_clientes.alta_cliente(conexion, nombre="Mirage")
    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados
    pagina._al_elegir_cliente(croma_id)
    pagina.campo_numero.setText("1")
    pagina.campo_monto_lista.setValue(1000)
    pagina._guardar()
    assert pagina.tabla_sesion.rowCount() == 1

    pagina._al_elegir_cliente(mirage_id)

    assert pagina.tabla_sesion.rowCount() == 0
    assert pagina.campo_numero.text() == ""


def test_reiniciar_deja_todo_en_blanco(app, conexion):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados
    pagina._al_elegir_cliente(cliente_id)
    pagina.campo_numero.setText("1")
    pagina.campo_monto_lista.setValue(1000)
    pagina._guardar()

    pagina.reiniciar()

    assert pagina._cliente_id is None
    assert pagina.tabla_sesion.rowCount() == 0
    assert not pagina.campo_numero.isEnabled()

    # Los datos guardados en la base no se tocan.
    comprobantes = datos_comprobantes.listar_comprobantes(conexion, cliente_id=cliente_id)
    assert len(comprobantes) == 1


def test_numero_repetido_mismo_cliente_pide_confirmar(monkeypatch, app, conexion):
    from PySide6.QtWidgets import QMessageBox
    respuestas = iter([QMessageBox.Yes])
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: next(respuestas)))

    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados
    pagina._al_elegir_cliente(cliente_id)
    pagina.campo_numero.setText("45126")
    pagina.campo_monto_lista.setValue(1000)
    pagina._guardar()
    pagina._limpiar_formulario_tras_guardar()

    pagina.campo_numero.setText("45126")
    pagina.campo_monto_lista.setValue(2000)
    pagina._guardar()  # dispara la confirmación (parcheada en "Sí")

    assert len(pagina._ids_sesion) == 2


def test_numero_repetido_otro_cliente_no_bloquea_y_avisa(app, conexion):
    croma_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    mirage_id = servicio_clientes.alta_cliente(conexion, nombre="Mirage")

    pagina = PaginaFacturacion(conexion)
    pagina.show()  # isVisible()/hasFocus() solo funcionan en widgets mostrados
    pagina._al_elegir_cliente(croma_id)
    pagina.campo_numero.setText("45142")
    pagina.campo_monto_lista.setValue(1000)
    pagina._guardar()

    pagina._al_elegir_cliente(mirage_id)
    pagina.campo_numero.setText("45142")
    pagina.campo_monto_lista.setValue(2000)
    pagina._guardar()  # no debería pedir confirmación: es otro cliente

    assert len(pagina._ids_sesion) == 1
    assert pagina._etiqueta_aviso.isVisible()
    assert "Croma" in pagina._etiqueta_aviso.text()
