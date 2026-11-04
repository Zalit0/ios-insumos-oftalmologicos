"""Prueba de humo de la interfaz: arma la ventana principal con el menú
superior y recorre todas las opciones sin que explote. No verifica
apariencia (eso se revisó a mano con capturas), solo que cada pantalla se
construye, el título cambia y no tira excepciones (docs/AJUSTES_V1.1.md,
etapa 1)."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

PySide6 = pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ios.data.db import conectar
from ios.ui.dialogo_acerca_de import DialogoAcercaDeIOS
from ios.ui.main_window import MENUS, MainWindow
from ios.ui.pages.compras_proveedores import PaginaComprasProveedores


@pytest.fixture(scope="module")
def app():
    aplicacion = QApplication.instance() or QApplication([])
    yield aplicacion


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "ios_test.db")
    try:
        yield conexion
    finally:
        conexion.close()


def _todas_las_acciones(ventana):
    """(texto del menú, texto de la acción, QAction) de cada entrada de
    MENUS, en el mismo orden en que se agregaron a la barra de menú."""
    acciones = []
    indice_menu = 0
    for nombre_menu, opciones in MENUS:
        menu = ventana.menuBar().actions()[indice_menu].menu()
        for indice_opcion, opcion in enumerate(opciones):
            accion = menu.actions()[indice_opcion]
            acciones.append((nombre_menu, opcion.nombre, accion))
        indice_menu += 1
    return acciones


def test_no_queda_rastro_del_menu_lateral(app, conexion):
    ventana = MainWindow(conexion)
    assert not hasattr(ventana, "_menu")


def test_menu_superior_tiene_las_secciones_esperadas(app, conexion):
    ventana = MainWindow(conexion)
    nombres_menu = [accion.text() for accion in ventana.menuBar().actions()]
    # Los "&" marcan el atajo Alt+letra; el texto visible los conserva.
    esperado = ["&Inicio", "&Ventas", "&Compras", "Ca&ja", "&Reportes", "&Herramientas", "A&yuda"]
    assert nombres_menu == esperado


def test_compras_y_pagos_comparten_la_misma_pagina(app, conexion):
    ventana = MainWindow(conexion)
    pagina = ventana._paginas_por_fabrica[PaginaComprasProveedores]
    apariciones = sum(
        1 for i in range(ventana._paginas.count()) if ventana._paginas.widget(i) is pagina
    )
    assert apariciones == 1


def test_recorrer_todas_las_opciones_no_tira_excepciones_y_cambia_el_titulo(app, conexion):
    ventana = MainWindow(conexion)
    for nombre_menu, nombre_opcion, accion in _todas_las_acciones(ventana):
        accion.trigger()
        assert ventana.windowTitle() == f"IOS — {nombre_opcion}"


def test_pagos_a_proveedores_muestra_la_pestana_correcta(app, conexion):
    ventana = MainWindow(conexion)
    for _, nombre_opcion, accion in _todas_las_acciones(ventana):
        if nombre_opcion == "Pagos a proveedores":
            accion.trigger()
            break
    pagina = ventana._paginas_por_fabrica[PaginaComprasProveedores]
    assert pagina._pestanas.currentIndex() == pagina.INDICE_PESTANA_PAGOS


def test_atajos_de_teclado(app, conexion):
    ventana = MainWindow(conexion)
    atajos_esperados = {"Cobranzas": "F3", "Caja diaria": "F4", "Cuenta corriente": "F5"}
    encontrados = {}
    for _, nombre_opcion, accion in _todas_las_acciones(ventana):
        if nombre_opcion in atajos_esperados:
            encontrados[nombre_opcion] = accion.shortcut().toString()
    assert encontrados == atajos_esperados


def test_reiniciar_se_llama_al_salir_de_una_pantalla(app, conexion, monkeypatch):
    ventana = MainWindow(conexion)
    pagina_inicio = ventana._paginas.currentWidget()

    llamadas = []
    monkeypatch.setattr(pagina_inicio, "reiniciar", lambda: llamadas.append(True))

    for _, nombre_opcion, accion in _todas_las_acciones(ventana):
        if nombre_opcion == "Clientes":
            accion.trigger()
            break

    assert llamadas == [True]


def test_acerca_de_ios_abre_sin_bloquear(app, conexion, monkeypatch):
    monkeypatch.setattr(DialogoAcercaDeIOS, "exec", lambda self: None)
    ventana = MainWindow(conexion)

    menu_ayuda = ventana.menuBar().actions()[-1].menu()
    assert menu_ayuda.actions()[0].text() == "Acerca de IOS"
    menu_ayuda.actions()[0].trigger()  # no debe tirar excepción


def test_buscar_actualizacion_esta_en_el_menu_ayuda(app, conexion):
    ventana = MainWindow(conexion)
    menu_ayuda = ventana.menuBar().actions()[-1].menu()
    assert menu_ayuda.actions()[1].text() == "Buscar actualización"


def test_buscar_actualizacion_sin_novedades_no_tira_excepcion(app, conexion, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    import ios.ui.main_window as main_window

    monkeypatch.setattr(main_window, "buscar_actualizacion", lambda version_actual: None)
    avisos = []
    monkeypatch.setattr(
        QMessageBox, "information", staticmethod(lambda *a, **k: avisos.append(a) or QMessageBox.Ok)
    )

    ventana = MainWindow(conexion)
    menu_ayuda = ventana.menuBar().actions()[-1].menu()
    menu_ayuda.actions()[1].trigger()  # no debe tirar excepción

    assert len(avisos) == 1
