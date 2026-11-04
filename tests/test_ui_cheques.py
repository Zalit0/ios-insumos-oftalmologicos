"""Prueba funcional de la pantalla de Cheques: cobrar y rechazar desde la
UI, y que la tabla de cartera se actualice."""

import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ios.data import cheques as datos_cheques
from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services.cobranzas import DatosCheque, Pago, asentar_cobranza
from ios.ui.pages.cheques import PaginaCheques


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
def cheque_en_cartera(conexion) -> int:
    cheque_forma_id = conexion.execute(
        "SELECT id FROM formas_pago WHERE nombre = 'Cheque'"
    ).fetchone()["id"]
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    asentar_cobranza(
        conexion, cliente_id, "2024-03-05",
        pagos=[Pago(cheque_forma_id, Decimal("5000"), cheque=DatosCheque("777", "Banco Nación", "2024-04-01"))],
        aplicaciones=[],
    )
    return datos_cheques.listar_cheques_en_cartera(conexion)[0]["id"]


def test_cobrar_desde_la_pantalla_actualiza_estado_y_tabla(app, conexion, cheque_en_cartera):
    pagina = PaginaCheques(conexion)
    assert pagina._tabla.rowCount() == 1

    pagina._tabla.selectRow(0)
    pagina._cobrar()

    cheque = datos_cheques.obtener_cheque(conexion, cheque_en_cartera)
    assert cheque["estado"] == "cobrado"
    assert pagina._tabla.rowCount() == 0


def test_rechazar_desde_la_pantalla_actualiza_estado_y_tabla(monkeypatch, app, conexion, cheque_en_cartera):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    pagina = PaginaCheques(conexion)
    pagina._tabla.selectRow(0)
    pagina._rechazar()

    cheque = datos_cheques.obtener_cheque(conexion, cheque_en_cartera)
    assert cheque["estado"] == "rechazado"
    assert pagina._tabla.rowCount() == 0
