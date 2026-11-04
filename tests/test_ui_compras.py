"""Pruebas funcionales de la pestaña Compras: tasa de IVA seleccionable,
cálculo automático en vivo y marca de "IVA manual" al corregirlo
(docs/AJUSTES_V1.1.md, etapa 5, D2/D3)."""

import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ios.data import compras as datos_compras
from ios.data.db import conectar
from ios.services import proveedores as servicio_proveedores
from ios.ui.pages.compras_proveedores import PaginaComprasProveedores


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
def lentex(conexion) -> int:
    return servicio_proveedores.alta_proveedor(conexion, nombre="Lentex")


def _elegir_proveedor(pagina, proveedor_id) -> None:
    indice = pagina._campo_compra_proveedor.findData(proveedor_id)
    pagina._campo_compra_proveedor.setCurrentIndex(indice)


def test_tasa_iva_por_defecto_es_la_de_configuracion(app, conexion):
    pagina = PaginaComprasProveedores(conexion)
    assert pagina._campo_compra_tasa_iva.currentText() == "21%"


def test_cambiar_el_monto_recalcula_el_iva(app, conexion):
    pagina = PaginaComprasProveedores(conexion)
    pagina._campo_compra_monto.setValue(121000)
    assert pagina._campo_compra_iva.value() == pytest.approx(21000.0)


def test_cambiar_la_tasa_recalcula_el_iva(app, conexion):
    pagina = PaginaComprasProveedores(conexion)
    pagina._campo_compra_monto.setValue(110500)
    pagina._campo_compra_tasa_iva.setCurrentText("10,5%")
    assert pagina._campo_compra_iva.value() == pytest.approx(10500.0)


def test_guardar_factura_con_iva_calculado(app, conexion, lentex):
    pagina = PaginaComprasProveedores(conexion)
    _elegir_proveedor(pagina, lentex)
    pagina._campo_compra_numero.setText("0001")
    pagina._campo_compra_monto.setValue(121000)

    pagina._guardar_compra()

    compras = datos_compras.listar_compras(conexion)
    assert len(compras) == 1
    assert compras[0]["iva"] == Decimal("21000")
    assert compras[0]["iva_manual"] == 0


def test_guardar_factura_con_iva_corregido_a_mano(app, conexion, lentex):
    pagina = PaginaComprasProveedores(conexion)
    _elegir_proveedor(pagina, lentex)
    pagina._campo_compra_numero.setText("0001")
    pagina._campo_compra_monto.setValue(121000)
    pagina._campo_compra_iva.setValue(20998)  # corrección manual

    pagina._guardar_compra()

    compras = datos_compras.listar_compras(conexion)
    assert compras[0]["iva"] == Decimal("20998")
    assert compras[0]["iva_manual"] == 1


def test_guardar_factura_limpia_el_formulario_y_vuelve_a_la_tasa_por_defecto(app, conexion, lentex):
    pagina = PaginaComprasProveedores(conexion)
    _elegir_proveedor(pagina, lentex)
    pagina._campo_compra_numero.setText("0001")
    pagina._campo_compra_monto.setValue(121000)
    pagina._campo_compra_tasa_iva.setCurrentText("0%")

    pagina._guardar_compra()

    assert pagina._campo_compra_numero.text() == ""
    assert pagina._campo_compra_monto.value() == 0
    assert pagina._campo_compra_tasa_iva.currentText() == "21%"


def test_tabla_muestra_marca_manual(app, conexion, lentex):
    pagina = PaginaComprasProveedores(conexion)
    _elegir_proveedor(pagina, lentex)
    pagina._campo_compra_numero.setText("0001")
    pagina._campo_compra_monto.setValue(121000)
    pagina._campo_compra_iva.setValue(20998)

    pagina._guardar_compra()

    assert "(manual)" in pagina._tabla_compras.item(0, 5).text()


def test_tabla_no_muestra_marca_cuando_el_iva_es_calculado(app, conexion, lentex):
    pagina = PaginaComprasProveedores(conexion)
    _elegir_proveedor(pagina, lentex)
    pagina._campo_compra_numero.setText("0001")
    pagina._campo_compra_monto.setValue(121000)

    pagina._guardar_compra()

    assert "(manual)" not in pagina._tabla_compras.item(0, 5).text()
