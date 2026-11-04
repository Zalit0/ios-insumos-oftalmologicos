"""Pruebas funcionales de la pantalla Clientes: buscador, filtro de
estado, diálogo de alta/edición (Datos + Sucursales), baja lógica y
reactivación (docs/AJUSTES_V1.1.md, etapa 4)."""

import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from ios.data import clientes as datos_clientes
from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.ui.pages.clientes import (
    FILTRO_ACTIVOS,
    FILTRO_DADOS_DE_BAJA,
    FILTRO_TODOS,
    PaginaClientes,
    _DialogoCliente,
)


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


def _nombres_en_tabla(pagina) -> list[str]:
    return [pagina._tabla.item(fila, 0).text() for fila in range(pagina._tabla.rowCount())]


# --- listado, buscador y filtro ---


def test_lista_inicial_solo_activos(app, conexion):
    servicio_clientes.alta_cliente(conexion, nombre="Croma")
    inactivo_id = servicio_clientes.alta_cliente(conexion, nombre="Mirage")
    servicio_clientes.baja_logica_cliente(conexion, inactivo_id)

    pagina = PaginaClientes(conexion)

    nombres = _nombres_en_tabla(pagina)
    assert "Croma" in nombres
    assert all("Mirage" not in n for n in nombres)


def test_filtro_dados_de_baja_muestra_solo_inactivos(app, conexion):
    servicio_clientes.alta_cliente(conexion, nombre="Croma")
    inactivo_id = servicio_clientes.alta_cliente(conexion, nombre="Mirage")
    servicio_clientes.baja_logica_cliente(conexion, inactivo_id)

    pagina = PaginaClientes(conexion)
    pagina._campo_filtro.setCurrentText(FILTRO_DADOS_DE_BAJA)

    nombres = _nombres_en_tabla(pagina)
    assert any("Mirage" in n for n in nombres)
    assert all("Croma" != n for n in nombres)


def test_filtro_todos_muestra_ambos(app, conexion):
    servicio_clientes.alta_cliente(conexion, nombre="Croma")
    inactivo_id = servicio_clientes.alta_cliente(conexion, nombre="Mirage")
    servicio_clientes.baja_logica_cliente(conexion, inactivo_id)

    pagina = PaginaClientes(conexion)
    pagina._campo_filtro.setCurrentText(FILTRO_TODOS)

    nombres = _nombres_en_tabla(pagina)
    assert any(n.startswith("Croma") for n in nombres)
    assert any(n.startswith("Mirage") for n in nombres)


def test_buscador_filtra_sin_distinguir_acentos_ni_mayusculas(app, conexion):
    servicio_clientes.alta_cliente(conexion, nombre="Óptica Ciudad")
    servicio_clientes.alta_cliente(conexion, nombre="Croma")

    pagina = PaginaClientes(conexion)
    pagina._campo_buscar.setText("optica")

    nombres = _nombres_en_tabla(pagina)
    assert nombres == ["Óptica Ciudad"]


def test_buscador_filtra_por_localidad(app, conexion):
    servicio_clientes.alta_cliente(conexion, nombre="Croma", localidad="Rosario")
    servicio_clientes.alta_cliente(conexion, nombre="Mirage", localidad="Córdoba")

    pagina = PaginaClientes(conexion)
    pagina._campo_buscar.setText("cordoba")

    assert _nombres_en_tabla(pagina) == ["Mirage"]


# --- diálogo: alta ---


def test_alta_cliente_desde_el_dialogo(app, conexion):
    dialogo = _DialogoCliente(conexion, None)
    dialogo._campo_nombre.setText("Óptica Nueva")
    dialogo._campo_localidad.setText("Rosario")

    dialogo._confirmar()

    assert dialogo.result() == QDialog.Accepted
    cliente = datos_clientes.obtener_cliente(conexion, dialogo.cliente_id)
    assert cliente["nombre"] == "Óptica Nueva"
    assert cliente["localidad"] == "Rosario"


def test_alta_con_nombre_repetido_no_cierra_el_dialogo(monkeypatch, app, conexion):
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    servicio_clientes.alta_cliente(conexion, nombre="Croma")

    dialogo = _DialogoCliente(conexion, None)
    dialogo._campo_nombre.setText("Croma")
    dialogo._confirmar()

    assert dialogo.result() != QDialog.Accepted


def test_cuit_invalido_pide_confirmacion_pero_no_bloquea(monkeypatch, app, conexion):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    dialogo = _DialogoCliente(conexion, None)
    dialogo._campo_nombre.setText("Óptica Nueva")
    dialogo._campo_cuit.setText("20-12345678-9")  # dígito verificador incorrecto
    dialogo._confirmar()

    assert dialogo.result() == QDialog.Accepted
    cliente = datos_clientes.obtener_cliente(conexion, dialogo.cliente_id)
    assert cliente["cuit"] == "20-12345678-9"


def test_cuit_invalido_si_se_rechaza_no_guarda(monkeypatch, app, conexion):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))

    dialogo = _DialogoCliente(conexion, None)
    dialogo._campo_nombre.setText("Óptica Nueva")
    dialogo._campo_cuit.setText("20-12345678-9")
    dialogo._confirmar()

    assert dialogo.result() != QDialog.Accepted


def test_sucursales_deshabilitadas_hasta_guardar_un_cliente_nuevo(app, conexion):
    dialogo = _DialogoCliente(conexion, None)
    assert dialogo._pestanas.isTabEnabled(1) is False


# --- diálogo: edición y sucursales ---


def test_editar_cliente_existente_carga_sus_datos(app, conexion):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma", telefono="011-1234")

    dialogo = _DialogoCliente(conexion, cliente_id)

    assert dialogo._campo_nombre.text() == "Croma"
    assert dialogo._campo_telefono.text() == "011-1234"
    assert dialogo._pestanas.isTabEnabled(1) is True


def test_agregar_y_desactivar_sucursal_desde_el_dialogo(app, conexion):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Koral")
    dialogo = _DialogoCliente(conexion, cliente_id)

    servicio_clientes.alta_sucursal(conexion, cliente_id, "Koral Norte")
    dialogo._cargar_sucursales()
    assert dialogo._lista_sucursales.count() == 2

    dialogo._lista_sucursales.setCurrentRow(0)
    dialogo._desactivar_sucursal()

    activas = datos_clientes.listar_sucursales(conexion, cliente_id)
    assert len(activas) == 1


def test_no_se_puede_desactivar_la_unica_sucursal_desde_el_dialogo(monkeypatch, app, conexion):
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Koral")
    dialogo = _DialogoCliente(conexion, cliente_id)
    dialogo._lista_sucursales.setCurrentRow(0)

    dialogo._desactivar_sucursal()

    activas = datos_clientes.listar_sucursales(conexion, cliente_id)
    assert len(activas) == 1


# --- pantalla principal: baja y reactivación ---


def test_dar_de_baja_desde_la_pantalla(monkeypatch, app, conexion):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")

    pagina = PaginaClientes(conexion)
    pagina._tabla.selectRow(0)
    pagina._dar_de_baja()

    cliente = datos_clientes.obtener_cliente(conexion, cliente_id)
    assert cliente["activo"] == 0


def test_reactivar_desde_la_pantalla(app, conexion):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    servicio_clientes.baja_logica_cliente(conexion, cliente_id)

    pagina = PaginaClientes(conexion)
    pagina._campo_filtro.setCurrentText(FILTRO_TODOS)
    pagina._tabla.selectRow(0)
    pagina._reactivar_cliente()

    cliente = datos_clientes.obtener_cliente(conexion, cliente_id)
    assert cliente["activo"] == 1


def test_botones_segun_estado_del_cliente_seleccionado(app, conexion):
    activo_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    inactivo_id = servicio_clientes.alta_cliente(conexion, nombre="Mirage")
    servicio_clientes.baja_logica_cliente(conexion, inactivo_id)

    pagina = PaginaClientes(conexion)
    pagina._campo_filtro.setCurrentText(FILTRO_TODOS)

    for fila in range(pagina._tabla.rowCount()):
        if pagina._tabla.item(fila, 0).data(Qt.UserRole) == activo_id:
            pagina._tabla.selectRow(fila)
            break
    assert pagina._boton_baja.isEnabled()
    assert not pagina._boton_reactivar.isEnabled()

    for fila in range(pagina._tabla.rowCount()):
        if pagina._tabla.item(fila, 0).data(Qt.UserRole) == inactivo_id:
            pagina._tabla.selectRow(fila)
            break
    assert not pagina._boton_baja.isEnabled()
    assert pagina._boton_reactivar.isEnabled()
