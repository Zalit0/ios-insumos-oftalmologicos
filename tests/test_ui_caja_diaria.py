"""Pruebas funcionales del diálogo Abrir caja (docs/AJUSTES_V1.1.md,
etapa 3.2): propone el saldo del último cierre, deja corregirlo, y exige
nota cuando se corrige."""

import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QDialog

from ios.data import cierres_caja as datos_cierres
from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services.caja import abrir_caja, cerrar_caja
from ios.services.cobranzas import Pago, asentar_cobranza
from ios.ui.pages.caja_diaria import PaginaCajaDiaria, DialogoAbrirCaja


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


def test_primer_dia_propone_cero(app, conexion):
    dialogo = DialogoAbrirCaja(conexion, "2024-03-01")
    propuesto, campo = dialogo._campos[next(iter(dialogo._campos))]
    assert propuesto == Decimal("0")
    assert campo.value() == 0.0


def test_propone_el_saldo_del_ultimo_cierre(app, conexion, efectivo_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    cierre_id = abrir_caja(conexion, "2024-03-01")
    asentar_cobranza(
        conexion, cliente_id, "2024-03-01", pagos=[Pago(efectivo_id, Decimal("1000"))], aplicaciones=[]
    )
    cerrar_caja(conexion, cierre_id, arqueos={efectivo_id: Decimal("1000")})

    dialogo = DialogoAbrirCaja(conexion, "2024-03-02")
    propuesto, campo = dialogo._campos[efectivo_id]
    assert propuesto == Decimal("1000")
    assert campo.value() == 1000.0


def test_confirmar_sin_cambios_no_exige_nota(app, conexion):
    dialogo = DialogoAbrirCaja(conexion, "2024-03-01")
    dialogo._confirmar()
    assert dialogo.modificados == []
    assert dialogo.result() == QDialog.Accepted


def test_confirmar_con_cambio_sin_nota_no_cierra_el_dialogo(monkeypatch, app, conexion, efectivo_id):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Ok))

    dialogo = DialogoAbrirCaja(conexion, "2024-03-01")
    _, campo = dialogo._campos[efectivo_id]
    campo.setValue(500)

    dialogo._confirmar()

    assert dialogo.result() != QDialog.Accepted


def test_confirmar_con_cambio_y_nota_registra_el_ajuste(app, conexion, efectivo_id):
    dialogo = DialogoAbrirCaja(conexion, "2024-03-01")
    _, campo = dialogo._campos[efectivo_id]
    campo.setValue(500)
    dialogo.campo_nota.setText("Se contó mal el día anterior")

    dialogo._confirmar()

    assert dialogo.result() == QDialog.Accepted
    assert dialogo.modificados == [(efectivo_id, Decimal("500"))]
    assert dialogo.nota == "Se contó mal el día anterior"


def test_abrir_caja_desde_la_pantalla_aplica_el_ajuste(monkeypatch, app, conexion, efectivo_id):
    pagina = PaginaCajaDiaria(conexion)

    def exec_falso(self):
        _, campo = self._campos[efectivo_id]
        campo.setValue(500)
        self.campo_nota.setText("Ajuste de prueba")
        self._confirmar()  # llama a self.accept(), fija result() en Accepted
        return self.result()

    monkeypatch.setattr(DialogoAbrirCaja, "exec", exec_falso)
    pagina._abrir_caja()

    cierre_id = datos_cierres.obtener_cierre_por_fecha(conexion, pagina._fecha_hoy)["id"]
    cerrar_caja(conexion, cierre_id, arqueos={efectivo_id: Decimal("500")})
    detalle = datos_cierres.listar_detalle_de_cierre(conexion, cierre_id)[0]
    assert detalle["saldo_teorico"] == Decimal("500")


def test_actualizar_cierra_sola_una_caja_de_ayer_que_quedo_abierta(app, conexion, efectivo_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    abrir_caja(conexion, "2024-03-01")
    asentar_cobranza(
        conexion, cliente_id, "2024-03-01", pagos=[Pago(efectivo_id, Decimal("1000"))], aplicaciones=[]
    )

    pagina = PaginaCajaDiaria(conexion)
    pagina._fecha_hoy = "2024-03-02"
    pagina.actualizar()

    cierre_ayer = datos_cierres.obtener_cierre_por_fecha(conexion, "2024-03-01")
    assert cierre_ayer["estado"] == "cerrado"
    detalle = datos_cierres.listar_detalle_de_cierre(conexion, cierre_ayer["id"])[0]
    assert detalle["arqueo"] == Decimal("1000")
    assert detalle["diferencia"] == Decimal("0")
    assert datos_cierres.obtener_cierre_por_fecha(conexion, "2024-03-02") is None
