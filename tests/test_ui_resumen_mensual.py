"""Pruebas funcionales de la pantalla Resumen mensual: pestañas Resumen
y Gráficos (docs/AJUSTES_V1.1.md, etapa 6.3, D5)."""

import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.ui.pages.resumen_mensual import PaginaResumenMensual


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
    return conexion.execute("SELECT id FROM tipos_comprobante WHERE abreviatura = 'RTO'").fetchone()["id"]


def test_tiene_dos_pestanas(app, conexion):
    pagina = PaginaResumenMensual(conexion)

    nombres = [pagina._pestanas.tabText(i) for i in range(pagina._pestanas.count())]
    assert nombres == ["Resumen", "Gráficos"]


def test_pestana_graficos_arma_los_cinco_graficos(app, conexion):
    pagina = PaginaResumenMensual(conexion)

    assert pagina._layout_graficos.count() == 5


def test_cambiar_de_mes_reconstruye_los_graficos(app, conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_id, Decimal("10000")
    )

    pagina = PaginaResumenMensual(conexion)
    indice_marzo = pagina._campo_mes.findData(3)
    pagina._campo_anio.setValue(2024)
    pagina._campo_mes.setCurrentIndex(indice_marzo)

    # El gráfico de venta vs. cobranza es el primero agregado.
    grafico_venta = pagina._layout_graficos.itemAt(0).widget()
    assert grafico_venta is not None
    assert pagina._layout_graficos.count() == 5  # se reconstruyen, no se acumulan
