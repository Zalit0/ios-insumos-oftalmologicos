"""Pruebas funcionales de la pestaña Mantenimiento de Configuración:
reiniciar la base de datos pidiendo confirmación por palabra
(docs/AJUSTES_V1.1.md, Instalación limpia)."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QInputDialog, QMessageBox

from ios.data.db import conectar
from ios.ui.pages.configuracion import PaginaConfiguracion


@pytest.fixture(scope="module")
def app():
    yield QApplication.instance() or QApplication([])


@pytest.fixture
def ruta_db(tmp_path: Path) -> Path:
    return tmp_path / "ios_test.db"


@pytest.fixture
def conexion(ruta_db):
    conexion = conectar(ruta_db)
    try:
        yield conexion
    finally:
        try:
            conexion.close()
        except Exception:
            pass


def _preparar(monkeypatch, ruta_db, respuesta_confirmacion=QMessageBox.Yes, palabra="BORRAR", confirmado=True):
    monkeypatch.setattr("ios.ui.pages.configuracion.ruta_base_de_datos", lambda: ruta_db)
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: respuesta_confirmacion))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **k: (palabra, confirmado)))


def test_palabra_incorrecta_no_toca_nada(monkeypatch, app, conexion, ruta_db):
    _preparar(monkeypatch, ruta_db, palabra="borrar")  # minúscula: no coincide
    cierres_llamado = []
    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: type(
        "Falso", (), {"quit": lambda self: cierres_llamado.append(True)}
    )()))

    pagina = PaginaConfiguracion(conexion)
    pagina._reiniciar_base_de_datos()

    assert ruta_db.exists()
    assert cierres_llamado == []
    # la conexión sigue viva: se puede seguir usando el programa
    conexion.execute("SELECT 1")


def test_cancelar_el_dialogo_de_confirmacion_no_toca_nada(monkeypatch, app, conexion, ruta_db):
    _preparar(monkeypatch, ruta_db, confirmado=False)

    pagina = PaginaConfiguracion(conexion)
    pagina._reiniciar_base_de_datos()

    assert ruta_db.exists()
    conexion.execute("SELECT 1")


def test_rechazar_el_aviso_inicial_no_toca_nada(monkeypatch, app, conexion, ruta_db):
    _preparar(monkeypatch, ruta_db, respuesta_confirmacion=QMessageBox.No)

    pagina = PaginaConfiguracion(conexion)
    pagina._reiniciar_base_de_datos()

    assert ruta_db.exists()
    conexion.execute("SELECT 1")


def test_palabra_correcta_mueve_el_archivo_y_cierra_la_app(monkeypatch, app, conexion, ruta_db):
    _preparar(monkeypatch, ruta_db)
    cierres_llamado = []
    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: type(
        "Falso", (), {"quit": lambda self: cierres_llamado.append(True)}
    )()))

    pagina = PaginaConfiguracion(conexion)
    pagina._reiniciar_base_de_datos()

    assert not ruta_db.exists()
    assert any(p.name.startswith("ios_test_respaldo_") for p in ruta_db.parent.iterdir())
    assert cierres_llamado == [True]
