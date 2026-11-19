"""Pruebas funcionales del botón "Editar pago seleccionado" de la
pestaña Pagos a proveedores: corregir un monto mal cargado desde la
pantalla, sin tener que tocar la base a mano."""

import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from ios.data import pagos_proveedor as datos_pagos
from ios.data.db import conectar
from ios.services import proveedores as servicio_proveedores
from ios.services.pagos_proveedor import registrar_pago_proveedor
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


@pytest.fixture
def efectivo(conexion) -> int:
    return conexion.execute(
        "SELECT id FROM formas_pago WHERE nombre = 'Efectivo'"
    ).fetchone()["id"]


def test_sin_seleccionar_nada_avisa(app, conexion, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    pagina = PaginaComprasProveedores(conexion)

    pagina._editar_pago_seleccionado()  # no debe explotar


def test_editar_pago_corrige_el_monto_en_la_tabla(app, conexion, lentex, efectivo, monkeypatch):
    pago_id = registrar_pago_proveedor(conexion, lentex, "2024-03-10", Decimal("1500000"), efectivo)

    def _exec_falso(self):
        self.campo_monto.setValue(15000)
        self._guardar()
        return QDialog.Accepted

    monkeypatch.setattr(QDialog, "exec", _exec_falso)
    pagina = PaginaComprasProveedores(conexion)
    pagina._tabla_pagos.setCurrentCell(0, 0)

    pagina._editar_pago_seleccionado()

    assert pagina._tabla_pagos.item(0, 2).text() == "$ 15.000,00"
    assert datos_pagos.obtener_pago_proveedor(conexion, pago_id)["monto"] == Decimal("15000")


def test_cancelar_el_dialogo_no_cambia_nada(app, conexion, lentex, efectivo, monkeypatch):
    registrar_pago_proveedor(conexion, lentex, "2024-03-10", Decimal("15000"), efectivo)
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Rejected)
    pagina = PaginaComprasProveedores(conexion)
    pagina._tabla_pagos.setCurrentCell(0, 0)

    pagina._editar_pago_seleccionado()

    assert pagina._tabla_pagos.item(0, 2).text() == "$ 15.000,00"
