"""Pantalla Inicio (Dashboard directivo): que abra, cargue y actualice sin
romperse, con y sin datos (docs/AJUSTES_V1.1.md, rediseño del Dashboard)."""

from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.ui.pages.inicio import PaginaInicio


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
def rto_id(conexion) -> int:
    return conexion.execute(
        "SELECT id FROM tipos_comprobante WHERE abreviatura = 'RTO'"
    ).fetchone()["id"]


def test_la_pantalla_abre_y_carga_sin_datos(app, conexion):
    pagina = PaginaInicio(conexion)

    assert pagina._valor_deuda.text() != "—"
    assert pagina._etiqueta_error.isVisible() is False
    assert pagina._etiqueta_actualizado.text() != ""


def test_actualizar_con_datos_no_rompe_y_pinta_las_tarjetas(app, conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_id, Decimal("1000")
    )

    pagina = PaginaInicio(conexion)
    pagina.actualizar()

    assert pagina._etiqueta_error.isVisible() is False
    assert "$" in pagina._valor_deuda.text()
    assert pagina._tabla_clientes.rowCount() >= 1
