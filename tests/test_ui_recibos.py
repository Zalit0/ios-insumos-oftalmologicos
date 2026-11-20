"""Pantalla Recibos: que abra, cargue y filtre sin romperse
(docs/AJUSTES_V1.1.md, módulo de recibos), y que se pueda corregir la
forma de pago de una línea ya cargada."""

from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from ios.data import recibos as datos_recibos
from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services.cobranzas import Pago, anular_recibo, asentar_cobranza
from ios.ui.pages.recibos import PaginaRecibos


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
def formas_pago(conexion) -> dict[str, int]:
    filas = conexion.execute("SELECT id, nombre FROM formas_pago").fetchall()
    return {fila["nombre"]: fila["id"] for fila in filas}


def test_la_pantalla_abre_sin_datos(app, conexion):
    pagina = PaginaRecibos(conexion)
    assert pagina._tabla.rowCount() == 0


def test_ver_todo_sin_filtro_de_fecha_muestra_un_recibo_viejo(app, conexion, formas_pago):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    asentar_cobranza(
        conexion, cliente_id, "2020-01-01", pagos=[Pago(formas_pago["Efectivo"], Decimal("500"))],
        aplicaciones=[],
    )

    pagina = PaginaRecibos(conexion)
    pagina.actualizar()
    assert pagina._tabla.rowCount() == 0  # fuera del rango de fecha por defecto (mes actual)

    pagina._casilla_ver_todo.setChecked(True)
    assert pagina._tabla.rowCount() == 1


@pytest.fixture
def recibo_hoy(conexion, formas_pago) -> int:
    from datetime import date

    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    return asentar_cobranza(
        conexion, cliente_id, date.today().isoformat(),
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1000"))], aplicaciones=[],
    )


def test_sin_seleccionar_nada_avisa(app, conexion, monkeypatch):
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    pagina = PaginaRecibos(conexion)

    pagina._editar_forma_pago_seleccionado()  # no debe explotar


def test_editar_forma_de_pago_desde_la_pantalla(app, conexion, formas_pago, recibo_hoy, monkeypatch):
    def _exec_falso(self):
        fila = self._filas[0]
        fila.combo_forma.setCurrentIndex(fila.combo_forma.findData(formas_pago["Transferencia"]))
        self._guardar()
        return QDialog.Accepted

    monkeypatch.setattr(QDialog, "exec", _exec_falso)
    pagina = PaginaRecibos(conexion)
    pagina._casilla_ver_todo.setChecked(True)
    pagina._tabla.setCurrentCell(0, 0)

    pagina._editar_forma_pago_seleccionado()

    linea = datos_recibos.listar_recibo_pagos(conexion, recibo_hoy)[0]
    assert linea["forma_pago_id"] == formas_pago["Transferencia"]


def test_no_se_puede_editar_un_recibo_anulado(app, conexion, recibo_hoy, monkeypatch):
    anular_recibo(conexion, recibo_hoy, "2024-03-21")
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    pagina = PaginaRecibos(conexion)
    pagina._casilla_ver_todo.setChecked(True)
    pagina._campo_estado.setCurrentIndex(pagina._campo_estado.findData("anulado"))
    pagina._tabla.setCurrentCell(0, 0)

    pagina._editar_forma_pago_seleccionado()  # no debe explotar, solo avisa
