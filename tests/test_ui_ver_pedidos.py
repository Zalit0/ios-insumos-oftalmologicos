"""Pruebas funcionales de la pantalla Ver pedidos (plan de detalle de
comprobantes, etapa 4): listado con filtros (proveedor, fecha, número) y
detalle de líneas del pedido seleccionado."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication

from ios.data.db import conectar
from ios.services import proveedores as servicio_proveedores
from ios.services.pedidos_proveedor import agregar_linea_especial, alta_pedido
from ios.ui.pages.ver_pedidos import PaginaVerPedidos


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


def test_lista_todos_los_pedidos_del_proveedor(app, conexion, proveedor_id):
    alta_pedido(conexion, proveedor_id, "2026-03-10")
    pagina = PaginaVerPedidos(conexion)
    pagina._casilla_ver_todo.setChecked(True)

    assert pagina._tabla_listado.rowCount() == 1


def test_filtro_de_fecha_excluye_pedidos_fuera_de_rango(app, conexion, proveedor_id):
    alta_pedido(conexion, proveedor_id, "2026-01-05")
    pagina = PaginaVerPedidos(conexion)
    pagina._campo_desde.setDate(QDate(2026, 3, 1))
    pagina._campo_hasta.setDate(QDate(2026, 3, 31))

    assert pagina._tabla_listado.rowCount() == 0


def test_filtro_por_numero(app, conexion, proveedor_id):
    primero_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    pagina = PaginaVerPedidos(conexion)
    pagina._casilla_ver_todo.setChecked(True)
    assert pagina._tabla_listado.rowCount() == 1

    pagina._campo_numero.setText(str(primero_id))

    assert pagina._tabla_listado.rowCount() == 1
    assert pagina._tabla_listado.item(0, 0).text() == str(primero_id)


def test_elegir_pedido_muestra_el_detalle(app, conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Ultravex 1.74")
    pagina = PaginaVerPedidos(conexion)
    pagina._casilla_ver_todo.setChecked(True)

    pagina._tabla_listado.setCurrentCell(0, 0)

    assert pagina._tabla_detalle_especiales.rowCount() == 1
    assert pagina._tabla_detalle_especiales.item(0, 0).text() == "Ultravex 1.74"
    assert pagina._tabla_detalle_reposicion.rowCount() == 0


def test_boton_generar_pdf_solo_se_habilita_con_un_pedido_elegido(app, conexion, proveedor_id):
    alta_pedido(conexion, proveedor_id, "2026-03-10")
    pagina = PaginaVerPedidos(conexion)
    pagina._casilla_ver_todo.setChecked(True)
    assert not pagina._boton_generar_pdf.isEnabled()

    pagina._tabla_listado.setCurrentCell(0, 0)

    assert pagina._boton_generar_pdf.isEnabled()


def test_generar_pdf_lo_abre(monkeypatch, app, conexion, proveedor_id, tmp_path):
    from ios.ui.pages import ver_pedidos as modulo

    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Ultravex 1.74")
    monkeypatch.setattr(modulo, "ruta_pdf_automatica", lambda nombre, subcarpeta=None: tmp_path / nombre)
    rutas_abiertas = []
    monkeypatch.setattr(modulo, "abrir_pdf", lambda ruta: rutas_abiertas.append(ruta))

    pagina = PaginaVerPedidos(conexion)
    pagina._casilla_ver_todo.setChecked(True)
    pagina._tabla_listado.setCurrentCell(0, 0)

    pagina._generar_pdf()

    assert len(rutas_abiertas) == 1
    assert rutas_abiertas[0].exists()
