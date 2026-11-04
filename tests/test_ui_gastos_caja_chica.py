"""Pruebas funcionales de la pantalla Gastos de caja chica: filtros por
categoría y forma de pago, subtotal por categoría
(docs/AJUSTES_V1.1.md, etapa 6.2, D4)."""

import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ios.data.db import conectar
from ios.services.caja import registrar_movimiento_manual
from ios.services.categorias_caja import alta_categoria
from ios.ui.pages.gastos_caja_chica import PaginaGastosCajaChica


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
def efectivo_id(conexion) -> int:
    return conexion.execute("SELECT id FROM formas_pago WHERE nombre = 'Efectivo'").fetchone()["id"]


def test_lista_los_egresos_manuales_del_rango(app, conexion, efectivo_id):
    categoria_id = alta_categoria(conexion, "Insumos", "egreso")
    hoy = conexion.execute("SELECT date('now')").fetchone()[0]
    registrar_movimiento_manual(
        conexion, f"{hoy} 10:00", "egreso", efectivo_id, Decimal("500"),
        categoria_id=categoria_id, concepto="Café",
    )

    pagina = PaginaGastosCajaChica(conexion)

    assert pagina._tabla.rowCount() == 1
    assert pagina._tabla.item(0, 2).text() == "Café"


def test_combo_categoria_solo_lista_categorias_de_egreso(app, conexion):
    alta_categoria(conexion, "Insumos", "egreso")
    alta_categoria(conexion, "Depósito de cliente", "ingreso")

    pagina = PaginaGastosCajaChica(conexion)

    nombres = [pagina._campo_categoria.itemText(i) for i in range(pagina._campo_categoria.count())]
    assert "Insumos" in nombres
    assert "Depósito de cliente" not in nombres


def test_filtrar_por_categoria_actualiza_la_tabla(app, conexion, efectivo_id):
    insumos_id = alta_categoria(conexion, "Insumos", "egreso")
    alquiler_id = alta_categoria(conexion, "Alquiler", "egreso")
    hoy = conexion.execute("SELECT date('now')").fetchone()[0]
    registrar_movimiento_manual(
        conexion, f"{hoy} 10:00", "egreso", efectivo_id, Decimal("100"), categoria_id=insumos_id
    )
    registrar_movimiento_manual(
        conexion, f"{hoy} 11:00", "egreso", efectivo_id, Decimal("300"), categoria_id=alquiler_id
    )

    pagina = PaginaGastosCajaChica(conexion)
    indice = pagina._campo_categoria.findData(alquiler_id)
    pagina._campo_categoria.setCurrentIndex(indice)

    assert pagina._tabla.rowCount() == 1
    assert pagina._tabla.item(0, 1).text() == "Alquiler"


def test_subtotal_se_muestra_con_mas_de_una_categoria(app, conexion, efectivo_id):
    insumos_id = alta_categoria(conexion, "Insumos", "egreso")
    alquiler_id = alta_categoria(conexion, "Alquiler", "egreso")
    hoy = conexion.execute("SELECT date('now')").fetchone()[0]
    registrar_movimiento_manual(
        conexion, f"{hoy} 10:00", "egreso", efectivo_id, Decimal("100"), categoria_id=insumos_id
    )
    registrar_movimiento_manual(
        conexion, f"{hoy} 11:00", "egreso", efectivo_id, Decimal("300"), categoria_id=alquiler_id
    )

    pagina = PaginaGastosCajaChica(conexion)

    assert "Por categoría" in pagina._etiqueta_totales.text()
    assert "Total: $ 400,00" in pagina._etiqueta_totales.text()
