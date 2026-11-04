"""Pruebas funcionales de la pantalla Cuenta corriente: buscador de
cliente, vista total por defecto, y filtro por mes con arrastre de saldo
(docs/AJUSTES_V1.1.md, Cuenta corriente con filtro de fechas/mes)."""

import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.ui.pages.cuenta_corriente import PaginaCuentaCorriente


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


def test_elegir_cliente_con_el_buscador_muestra_la_vista_total(app, conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_id, Decimal("1000")
    )

    pagina = PaginaCuentaCorriente(conexion)
    pagina._al_elegir_cliente(cliente_id)

    assert pagina._etiqueta_cliente.text() == "Croma"
    assert pagina._pestanas_sucursales.count() == 1
    pestana = pagina._pestanas_sucursales.widget(0)
    tabla = pestana.layout().itemAt(0).widget()
    assert tabla.columnCount() == 4  # Remito, Fecha, Monto final, Saldo (vista total)
    assert tabla.rowCount() == 1


def test_usar_mes_completa_fechas_y_arrastra_el_saldo_anterior(app, conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-02-20", cliente_id, sucursal_id, Decimal("1000")
    )

    pagina = PaginaCuentaCorriente(conexion)
    pagina._al_elegir_cliente(cliente_id)

    pagina._campo_mes.setCurrentIndex(2)  # Marzo
    pagina._campo_anio.setValue(2024)
    pagina._usar_mes()

    assert pagina._campo_desde.date() == QDate(2024, 3, 1)
    assert pagina._campo_hasta.date() == QDate(2024, 3, 31)
    assert pagina._modo_periodo is True

    pestana = pagina._pestanas_sucursales.widget(0)
    etiquetas = [
        pestana.layout().itemAt(i).widget().text()
        for i in range(pestana.layout().count())
        if hasattr(pestana.layout().itemAt(i).widget(), "text")
    ]
    assert any("Saldo anterior: $ 1.000,00" in texto for texto in etiquetas)


def test_ver_todo_vuelve_a_la_vista_sin_filtro(app, conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_id, Decimal("1000")
    )

    pagina = PaginaCuentaCorriente(conexion)
    pagina._al_elegir_cliente(cliente_id)
    pagina._consultar_periodo()
    assert pagina._modo_periodo is True

    pagina._ver_todo()

    assert pagina._modo_periodo is False
    pestana = pagina._pestanas_sucursales.widget(0)
    tabla = pestana.layout().itemAt(0).widget()
    assert tabla.columnCount() == 4  # Remito, Fecha, Monto final, Saldo (vista total)


def _preparar_pagina_para_exportar(conexion, rto_id, tmp_path):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_id, Decimal("1000")
    )

    pagina = PaginaCuentaCorriente(conexion)
    pagina._al_elegir_cliente(cliente_id)
    pagina._campo_desde.setDate(QDate(2024, 3, 1))
    pagina._campo_hasta.setDate(QDate(2024, 3, 31))
    pagina._consultar_periodo()
    return pagina


def test_modalidad_por_defecto_es_solo_pendientes(app, conexion, rto_id, tmp_path):
    pagina = _preparar_pagina_para_exportar(conexion, rto_id, tmp_path)
    assert pagina._campo_modo_pdf.currentData() == "pendientes"


def test_exportar_en_modo_pendientes_llama_al_reporte_de_pendientes(
    monkeypatch, app, conexion, rto_id, tmp_path
):
    pagina = _preparar_pagina_para_exportar(conexion, rto_id, tmp_path)

    ruta_salida = tmp_path / "estado.pdf"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(ruta_salida), ""))
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))

    llamadas = []
    monkeypatch.setattr(
        "ios.ui.pages.cuenta_corriente.generar_pdf_estado_cuenta_pendientes",
        lambda *a, **k: llamadas.append("pendientes"),
    )

    pagina._exportar_pdf()

    assert llamadas == ["pendientes"]


def test_exportar_en_modo_completo_llama_al_reporte_de_periodo(
    monkeypatch, app, conexion, rto_id, tmp_path
):
    pagina = _preparar_pagina_para_exportar(conexion, rto_id, tmp_path)
    indice = pagina._campo_modo_pdf.findData("completo")
    pagina._campo_modo_pdf.setCurrentIndex(indice)

    ruta_salida = tmp_path / "estado.pdf"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(ruta_salida), ""))
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))

    pagina._exportar_pdf()

    assert ruta_salida.exists()


def test_exportar_en_modo_historial_llama_al_reporte_de_historial(
    monkeypatch, app, conexion, rto_id, tmp_path
):
    pagina = _preparar_pagina_para_exportar(conexion, rto_id, tmp_path)
    indice = pagina._campo_modo_pdf.findData("historial")
    pagina._campo_modo_pdf.setCurrentIndex(indice)

    ruta_salida = tmp_path / "estado.pdf"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(ruta_salida), ""))
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))

    pagina._exportar_pdf()

    assert ruta_salida.exists()
