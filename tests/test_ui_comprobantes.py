"""Pruebas funcionales de la pantalla Comprobantes como consulta
(docs/AJUSTES_V1.1.md, etapa 2.3): filtros, totales del pie, y el diálogo
de edición que bloquea monto/descuento/IVA si hay pagos aplicados."""

import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QApplication, QDialog

from ios.data import comprobantes as datos_comprobantes
from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services.cobranzas import AplicacionARemito, Pago, asentar_cobranza
from ios.ui.pages.comprobantes import PaginaComprobantes, _DialogoEditarComprobante


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


@pytest.fixture
def croma_con_remitos(conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    ids = [
        servicio_comprobantes.alta_comprobante(
            conexion, rto_id, str(numero), fecha, cliente_id, sucursal_id, Decimal(str(monto)),
            descuento_pct=Decimal("0"), con_iva=False,
        )
        for numero, fecha, monto in [
            ("1", "2024-03-05", 1000),
            ("2", "2024-03-10", 2000),
            ("3", "2024-02-20", 500),  # fuera de "este mes" si hoy no es febrero
        ]
    ]
    return cliente_id, ids


def _rango_2024(pagina) -> None:
    """Los datos de prueba son de 2024; "Este año" depende de la fecha
    real de la máquina, así que para esos casos fijamos el rango a mano."""
    pagina._campo_desde.setDate(QDate(2024, 1, 1))
    pagina._campo_hasta.setDate(QDate(2024, 12, 31))
    pagina._cargar_tabla()


def test_filtro_por_cliente(app, conexion, croma_con_remitos):
    cliente_id, ids = croma_con_remitos
    servicio_clientes.alta_cliente(conexion, nombre="Mirage")

    pagina = PaginaComprobantes(conexion)
    _rango_2024(pagina)
    pagina._al_elegir_cliente_filtro(cliente_id)

    assert pagina._tabla.rowCount() == 3
    assert pagina._etiqueta_cliente_filtro.text() == "Croma"


def test_quitar_filtro_cliente(app, conexion, croma_con_remitos):
    cliente_id, _ = croma_con_remitos
    pagina = PaginaComprobantes(conexion)
    _rango_2024(pagina)
    pagina._al_elegir_cliente_filtro(cliente_id)
    assert pagina._cliente_filtro_id == cliente_id

    pagina._quitar_filtro_cliente()

    assert pagina._cliente_filtro_id is None
    assert pagina._etiqueta_cliente_filtro.text() == "(todos)"


def test_rango_este_anio_incluye_un_remito_de_hoy(app, conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    hoy = QDate.currentDate().toString("yyyy-MM-dd")
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", hoy, cliente_id, sucursal_id, Decimal("1000"),
        descuento_pct=Decimal("0"), con_iva=False,
    )

    pagina = PaginaComprobantes(conexion)
    pagina._rango_este_anio()

    assert pagina._tabla.rowCount() == 1


def test_filtro_por_numero(app, conexion, croma_con_remitos):
    cliente_id, ids = croma_con_remitos
    pagina = PaginaComprobantes(conexion)
    _rango_2024(pagina)
    pagina._filtro_numero.setText("2")
    pagina._cargar_tabla()

    assert pagina._tabla.rowCount() == 1
    assert pagina._tabla.item(0, 1).text() == "2"


def test_totales_del_pie(app, conexion, croma_con_remitos):
    cliente_id, ids = croma_con_remitos
    pagina = PaginaComprobantes(conexion)
    _rango_2024(pagina)

    assert "3 comprobantes" in pagina._etiqueta_totales.text()
    assert "$ 3.500,00" in pagina._etiqueta_totales.text()  # 1000+2000+500


def test_editar_sin_pagos_permite_cambiar_monto(app, conexion, croma_con_remitos):
    cliente_id, ids = croma_con_remitos
    dialogo = _DialogoEditarComprobante(conexion, ids[0])
    assert dialogo.campo_monto_lista.isEnabled()

    dialogo.campo_monto_lista.setValue(5000)
    dialogo._guardar()

    comprobante = datos_comprobantes.obtener_comprobante(conexion, ids[0])
    assert comprobante["monto_lista"] == Decimal("5000")


def test_editar_con_pagos_bloquea_monto_pero_permite_numero(app, conexion, croma_con_remitos):
    cliente_id, ids = croma_con_remitos
    efectivo_id = conexion.execute(
        "SELECT id FROM formas_pago WHERE nombre = 'Efectivo'"
    ).fetchone()["id"]
    asentar_cobranza(
        conexion, cliente_id, "2024-03-06",
        pagos=[Pago(efectivo_id, Decimal("1000"))],
        aplicaciones=[AplicacionARemito(ids[0], Decimal("1000"))],
    )

    dialogo = _DialogoEditarComprobante(conexion, ids[0])
    assert not dialogo.campo_monto_lista.isEnabled()
    assert not dialogo.campo_descuento.isEnabled()
    assert not dialogo.campo_con_iva.isEnabled()

    dialogo.campo_numero.setText("999")
    dialogo._guardar()

    comprobante = datos_comprobantes.obtener_comprobante(conexion, ids[0])
    assert comprobante["numero"] == "999"
    assert comprobante["monto_lista"] == Decimal("1000")  # no cambió
