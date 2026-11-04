"""Prueba funcional de la pantalla de Cobranzas: tildar remitos, cargar
formas de pago (con cheque) y confirmar, verificando que el recibo y las
aplicaciones queden bien en la base."""

import os
from datetime import date
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from ios.data import cheques as datos_cheques
from ios.data import cierres_caja as datos_cierres
from ios.data import recibos as datos_recibos
from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services.caja import abrir_caja
from ios.ui.pages.caja_diaria import DialogoAbrirCaja
from ios.ui.pages.cobranzas import COLUMNA_MONTO, PaginaCobranzas

FECHA_HOY = date.today().isoformat()


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
def del_pilar(conexion):
    rto_id = conexion.execute(
        "SELECT id FROM tipos_comprobante WHERE abreviatura = 'RTO'"
    ).fetchone()["id"]
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Del Pilar", descuento_default=Decimal("20"), con_iva_default=False
    )
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    comprobante_ids = [
        servicio_comprobantes.alta_comprobante(
            conexion, rto_id, str(45109 + i), f"2024-03-0{4 + i}", cliente_id, sucursal_id,
            Decimal(str(monto)),
        )
        for i, monto in enumerate([16334.8, 37630.8])
    ]
    return cliente_id, comprobante_ids


@pytest.fixture
def caja_abierta_hoy(conexion):
    abrir_caja(conexion, FECHA_HOY)


def test_tildar_y_confirmar_cobranza_con_efectivo_y_cheque(app, conexion, del_pilar, caja_abierta_hoy):
    cliente_id, comprobante_ids = del_pilar
    pagina = PaginaCobranzas(conexion)

    indice_cliente = pagina._campo_cliente.findData(cliente_id)
    pagina._campo_cliente.setCurrentIndex(indice_cliente)

    assert pagina._tabla.rowCount() == 2
    pagina._tabla.item(0, 0).setCheckState(Qt.Checked)
    pagina._tabla.item(1, 0).setCheckState(Qt.Checked)

    pagina._agregar_fila_pago()
    fila_efectivo = pagina._filas_pago[0]
    fila_efectivo.combo_forma.setCurrentIndex(fila_efectivo.combo_forma.findText("Efectivo"))
    fila_efectivo.monto.setValue(13067.84)

    pagina._agregar_fila_pago()
    fila_cheque = pagina._filas_pago[1]
    fila_cheque.combo_forma.setCurrentIndex(fila_cheque.combo_forma.findText("Cheque"))
    fila_cheque.monto.setValue(30104.64)
    fila_cheque.cheque_numero.setText("555")
    fila_cheque.cheque_banco.setText("Banco Nación")

    pagina._ofrecer_pdf_recibo = lambda recibo_id: None  # evita el QMessageBox de la captura
    pagina._confirmar_cobranza()

    recibos = datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente_id)
    assert len(recibos) == 1
    recibo = recibos[0]
    assert recibo["monto_total"] == Decimal("43172.48")

    aplicaciones = datos_recibos.listar_aplicaciones_de_recibo(conexion, recibo["id"])
    assert len(aplicaciones) == 2
    for comprobante_id in comprobante_ids:
        aplicado = datos_recibos.total_aplicado_a_comprobante(conexion, comprobante_id)
        assert aplicado > 0

    cheques = datos_cheques.listar_cheques_en_cartera(conexion)
    assert len(cheques) == 1
    assert cheques[0]["numero"] == "555"

    # La tabla se recargó: ya no quedan remitos pendientes (ambos se pagaron).
    assert pagina._tabla.rowCount() == 0


def test_resumen_se_actualiza_al_tildar_y_destildar(app, conexion, del_pilar):
    cliente_id, comprobante_ids = del_pilar
    pagina = PaginaCobranzas(conexion)
    pagina._campo_cliente.setCurrentIndex(pagina._campo_cliente.findData(cliente_id))

    assert pagina._etiqueta_seleccionados.text() == "Remitos seleccionados: 0 — $ 0,00"

    pagina._tabla.item(0, 0).setCheckState(Qt.Checked)
    assert "Remitos seleccionados: 1" in pagina._etiqueta_seleccionados.text()
    assert "$ 13.067,84" in pagina._etiqueta_seleccionados.text()

    pagina._tabla.item(1, 0).setCheckState(Qt.Checked)
    assert "Remitos seleccionados: 2" in pagina._etiqueta_seleccionados.text()
    assert "$ 43.172,48" in pagina._etiqueta_seleccionados.text()

    pagina._tabla.item(0, 0).setCheckState(Qt.Unchecked)
    assert "Remitos seleccionados: 1" in pagina._etiqueta_seleccionados.text()
    assert "$ 30.104,64" in pagina._etiqueta_seleccionados.text()


def test_resumen_muestra_falta_y_excedente(app, conexion, del_pilar):
    cliente_id, comprobante_ids = del_pilar
    pagina = PaginaCobranzas(conexion)
    pagina._campo_cliente.setCurrentIndex(pagina._campo_cliente.findData(cliente_id))
    pagina._tabla.item(0, 0).setCheckState(Qt.Checked)  # $13.067,84

    pagina._agregar_fila_pago()
    fila = pagina._filas_pago[0]
    fila.combo_forma.setCurrentIndex(fila.combo_forma.findText("Efectivo"))

    fila.monto.setValue(5000)
    assert "Falta $ 8.067,84" in pagina._etiqueta_diferencia.text()

    fila.monto.setValue(13067.84)
    assert pagina._etiqueta_diferencia.text() == "Diferencia: Coincide"

    fila.monto.setValue(15000)
    assert "Excedente" in pagina._etiqueta_diferencia.text()
    assert "saldo a favor" in pagina._etiqueta_diferencia.text()


def test_seleccionar_todos(app, conexion, del_pilar):
    cliente_id, comprobante_ids = del_pilar
    pagina = PaginaCobranzas(conexion)
    pagina._campo_cliente.setCurrentIndex(pagina._campo_cliente.findData(cliente_id))

    pagina._seleccionar_todos()

    assert all(
        pagina._tabla.item(fila, 0).checkState() == Qt.Checked
        for fila in range(pagina._tabla.rowCount())
    )
    assert "Remitos seleccionados: 2" in pagina._etiqueta_seleccionados.text()


def test_completar_con_total_seleccionado(app, conexion, del_pilar):
    cliente_id, comprobante_ids = del_pilar
    pagina = PaginaCobranzas(conexion)
    pagina._campo_cliente.setCurrentIndex(pagina._campo_cliente.findData(cliente_id))
    pagina._seleccionar_todos()  # $13.067,84 + $30.104,64 = $43.172,48

    pagina._agregar_fila_pago()
    primera = pagina._filas_pago[0]
    primera.combo_forma.setCurrentIndex(primera.combo_forma.findText("Efectivo"))
    primera.monto.setValue(10000)

    pagina._agregar_fila_pago()
    segunda = pagina._filas_pago[1]
    segunda.combo_forma.setCurrentIndex(segunda.combo_forma.findText("Transferencia"))

    pagina._completar_con_total_seleccionado()

    assert segunda.monto.value() == pytest.approx(33172.48)
    assert pagina._etiqueta_diferencia.text() == "Diferencia: Coincide"


def test_aplicar_saldo_a_favor_sin_caja(app, conexion, del_pilar, caja_abierta_hoy):
    cliente_id, comprobante_ids = del_pilar
    pagina = PaginaCobranzas(conexion)
    indice_cliente = pagina._campo_cliente.findData(cliente_id)
    pagina._campo_cliente.setCurrentIndex(indice_cliente)

    # Primero generamos saldo a favor con una cobranza de más.
    pagina._tabla.item(0, 0).setCheckState(Qt.Checked)
    pagina._agregar_fila_pago()
    fila = pagina._filas_pago[0]
    fila.combo_forma.setCurrentIndex(fila.combo_forma.findText("Efectivo"))
    fila.monto.setValue(20000)  # remito 1 vale 13067.84: sobran 6932.16
    pagina._ofrecer_pdf_recibo = lambda recibo_id: None
    pagina._confirmar_cobranza()

    movimientos_antes = conexion.execute("SELECT COUNT(*) AS n FROM movimientos_caja").fetchone()["n"]

    pagina._tabla.item(0, 0).setCheckState(Qt.Checked)  # el remito 2, ahora primero en la lista
    pagina._tabla.cellWidget(0, 4).setValue(6932.16)
    pagina._aplicar_saldo_a_favor()

    movimientos_despues = conexion.execute("SELECT COUNT(*) AS n FROM movimientos_caja").fetchone()["n"]
    assert movimientos_despues == movimientos_antes  # sin movimiento de caja


# --- Caja obligatoria para cobrar (docs/AJUSTES_V1.1.md) ---


def _cargar_pago_simple(pagina: PaginaCobranzas) -> None:
    pagina._tabla.item(0, 0).setCheckState(Qt.Checked)
    pagina._agregar_fila_pago()
    fila = pagina._filas_pago[0]
    fila.combo_forma.setCurrentIndex(fila.combo_forma.findText("Efectivo"))
    fila.monto.setValue(13067.84)
    pagina._ofrecer_pdf_recibo = lambda recibo_id: None


def test_confirmar_cobranza_sin_caja_abierta_pide_abrirla_y_sigue_si_se_acepta(
    monkeypatch, app, conexion, del_pilar
):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(DialogoAbrirCaja, "exec", lambda self: self.accept() or self.result())

    cliente_id, _ = del_pilar
    pagina = PaginaCobranzas(conexion)
    pagina._campo_cliente.setCurrentIndex(pagina._campo_cliente.findData(cliente_id))
    _cargar_pago_simple(pagina)

    pagina._confirmar_cobranza()

    assert len(datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente_id)) == 1
    assert datos_cierres.obtener_cierre_por_fecha(conexion, FECHA_HOY)["estado"] == "abierto"


def test_confirmar_cobranza_sin_caja_abierta_y_se_rechaza_el_aviso_no_asienta_nada(
    monkeypatch, app, conexion, del_pilar
):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))

    cliente_id, _ = del_pilar
    pagina = PaginaCobranzas(conexion)
    pagina._campo_cliente.setCurrentIndex(pagina._campo_cliente.findData(cliente_id))
    _cargar_pago_simple(pagina)

    pagina._confirmar_cobranza()

    assert datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente_id) == []
    assert datos_cierres.obtener_cierre_por_fecha(conexion, FECHA_HOY) is None


def test_confirmar_cobranza_acepta_el_aviso_pero_cancela_la_apertura_no_asienta_nada(
    monkeypatch, app, conexion, del_pilar
):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(DialogoAbrirCaja, "exec", lambda self: QDialog.Rejected)

    cliente_id, _ = del_pilar
    pagina = PaginaCobranzas(conexion)
    pagina._campo_cliente.setCurrentIndex(pagina._campo_cliente.findData(cliente_id))
    _cargar_pago_simple(pagina)

    pagina._confirmar_cobranza()

    assert datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente_id) == []
    assert datos_cierres.obtener_cierre_por_fecha(conexion, FECHA_HOY) is None


# --- Fecha del recibo: nunca posterior a hoy, aviso si es anterior ---


def test_el_campo_fecha_no_deja_elegir_un_dia_posterior_a_hoy(app, conexion, del_pilar):
    pagina = PaginaCobranzas(conexion)
    assert pagina._campo_fecha.maximumDate() == QDate.currentDate()


def test_fecha_anterior_a_hoy_pide_confirmacion_y_si_se_acepta_asienta(
    monkeypatch, app, conexion, del_pilar, caja_abierta_hoy
):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    cliente_id, _ = del_pilar
    pagina = PaginaCobranzas(conexion)
    pagina._campo_cliente.setCurrentIndex(pagina._campo_cliente.findData(cliente_id))
    _cargar_pago_simple(pagina)
    pagina._campo_fecha.setDate(QDate(2024, 3, 4))

    pagina._confirmar_cobranza()

    recibos = datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente_id)
    assert len(recibos) == 1
    assert recibos[0]["fecha"] == "2024-03-04"


def test_pago_menor_al_total_se_reparte_automatico_el_mas_viejo_primero(
    app, conexion, del_pilar, caja_abierta_hoy
):
    """Remito 1: $13.067,84; remito 2: $30.104,64. Si se tildan los dos y
    se paga $20.000, el remito 1 (más viejo) se cubre entero y el remito
    2 se queda con el resto ($6.932,16), sin tocar nada a mano."""
    cliente_id, comprobante_ids = del_pilar
    pagina = PaginaCobranzas(conexion)
    pagina._campo_cliente.setCurrentIndex(pagina._campo_cliente.findData(cliente_id))
    pagina._seleccionar_todos()

    pagina._agregar_fila_pago()
    fila = pagina._filas_pago[0]
    fila.combo_forma.setCurrentIndex(fila.combo_forma.findText("Efectivo"))
    fila.monto.setValue(20000)

    assert pagina._tabla.cellWidget(0, COLUMNA_MONTO).value() == pytest.approx(13067.84)
    assert pagina._tabla.cellWidget(1, COLUMNA_MONTO).value() == pytest.approx(6932.16)
    assert "Falta" in pagina._etiqueta_diferencia.text()

    pagina._ofrecer_pdf_recibo = lambda recibo_id: None
    pagina._confirmar_cobranza()

    aplicado_1 = datos_recibos.total_aplicado_a_comprobante(conexion, comprobante_ids[0])
    aplicado_2 = datos_recibos.total_aplicado_a_comprobante(conexion, comprobante_ids[1])
    assert aplicado_1 == Decimal("13067.84")
    assert aplicado_2 == Decimal("6932.16")


def test_si_alcanza_para_todo_se_completan_los_saldos_enteros(
    app, conexion, del_pilar, caja_abierta_hoy
):
    cliente_id, comprobante_ids = del_pilar
    pagina = PaginaCobranzas(conexion)
    pagina._campo_cliente.setCurrentIndex(pagina._campo_cliente.findData(cliente_id))
    pagina._seleccionar_todos()

    pagina._agregar_fila_pago()
    fila = pagina._filas_pago[0]
    fila.combo_forma.setCurrentIndex(fila.combo_forma.findText("Efectivo"))
    fila.monto.setValue(10000)  # primero paga de menos: reparte parcial

    assert pagina._tabla.cellWidget(1, COLUMNA_MONTO).value() == pytest.approx(0)

    fila.monto.setValue(43172.48)  # ahora alcanza para todo: se restituyen los saldos enteros

    assert pagina._tabla.cellWidget(0, COLUMNA_MONTO).value() == pytest.approx(13067.84)
    assert pagina._tabla.cellWidget(1, COLUMNA_MONTO).value() == pytest.approx(30104.64)
    assert pagina._etiqueta_diferencia.text() == "Diferencia: Coincide"


def test_fecha_anterior_a_hoy_si_se_rechaza_el_aviso_no_asienta_nada(
    monkeypatch, app, conexion, del_pilar, caja_abierta_hoy
):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.No))

    cliente_id, _ = del_pilar
    pagina = PaginaCobranzas(conexion)
    pagina._campo_cliente.setCurrentIndex(pagina._campo_cliente.findData(cliente_id))
    _cargar_pago_simple(pagina)
    pagina._campo_fecha.setDate(QDate(2024, 3, 4))

    pagina._confirmar_cobranza()

    assert datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente_id) == []
