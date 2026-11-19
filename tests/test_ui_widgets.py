"""Pruebas de CampoDecimal: tiene que interpretar bien un monto tipeado
con punto o con coma como separador decimal, sin importar la
configuración regional de Windows de la PC donde corra -- el bug real
fue un pago a un proveedor cargado con punto que la config regional (en
coma) tomó como separador de miles y lo multiplicó por 100."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ios.ui.widgets import CampoDecimal, CampoGraduacion


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("6000,00", 6000.0),
        ("6000.00", 6000.0),  # el bug real: punto en vez de coma
        ("1.234,56", 1234.56),  # miles con punto + decimal con coma
        ("1234.56", 1234.56),
        ("1234", 1234.0),
        ("-150,50", -150.5),
        ("-150.50", -150.5),
        ("", 0.0),
    ],
)
def test_valueFromText_acepta_coma_o_punto_como_decimal(app, texto, esperado):
    campo = CampoDecimal()
    campo.setRange(-99_999_999, 99_999_999)
    campo.setDecimals(2)

    assert campo.valueFromText(texto) == pytest.approx(esperado)


def test_campo_graduacion_tambien_acepta_punto_como_decimal(app):
    campo = CampoGraduacion()
    campo.setRange(-30, 30)
    campo.setDecimals(2)

    assert campo.valueFromText("+1.25") == pytest.approx(1.25)
    assert campo.valueFromText("-0.25") == pytest.approx(-0.25)
