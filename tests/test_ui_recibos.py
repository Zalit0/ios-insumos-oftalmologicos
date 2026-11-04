"""Pantalla Recibos: que abra, cargue y filtre sin romperse
(docs/AJUSTES_V1.1.md, módulo de recibos)."""

from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services.cobranzas import Pago, asentar_cobranza
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
