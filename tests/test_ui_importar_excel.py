"""Prueba funcional de la pantalla Importar desde Excel: leer un archivo
sintético, asignar una hoja como sucursal de otra, y confirmar."""

import os
from datetime import date
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import openpyxl
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox

from ios.data import clientes as datos_clientes
from ios.data.db import conectar
from ios.ui.pages.importar_excel import PaginaImportarExcel, _DialogoResumenConflictos

ENCABEZADO = [
    "FECHA", "TIPO", "NUM.", "MONTO", "DESC.", "FINAL", "SI/NO", "$", "MONTO",
    "RECIBO", "FECHA", "SALDOS", None,
]


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
def archivo_croma(tmp_path: Path) -> Path:
    libro = openpyxl.Workbook()
    libro.remove(libro.active)
    for nombre_hoja, numero, monto, final in (("CROMA", 1, 1000, 750), ("CROMA FDEZ.", 2, 2000, 1500)):
        ws = libro.create_sheet(nombre_hoja)
        ws.cell(row=1, column=2, value=nombre_hoja)
        for col, valor in enumerate(ENCABEZADO, start=2):
            ws.cell(row=4, column=col, value=valor)
        ws.cell(row=5, column=2, value=date(2024, 3, 1))
        ws.cell(row=5, column=3, value="RTO")
        ws.cell(row=5, column=4, value=numero)
        ws.cell(row=5, column=5, value=monto)
        ws.cell(row=5, column=6, value=25)
        ws.cell(row=5, column=7, value=final)
    ruta = tmp_path / "marzo.xlsx"
    libro.save(ruta)
    return ruta


def test_leer_y_confirmar_con_sucursal_asignada(monkeypatch, app, conexion, archivo_croma):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(_DialogoResumenConflictos, "exec", lambda self: None)

    pagina = PaginaImportarExcel(conexion)
    pagina._campo_ruta.setText(str(archivo_croma))
    pagina._campo_mes.setText("2024-03")
    pagina._leer_archivo()

    assert pagina._tabla_hojas.rowCount() == 2
    assert pagina._boton_confirmar.isEnabled()

    pagina._combos_sucursal["CROMA FDEZ."].setCurrentText("CROMA")
    pagina._confirmar()

    croma = datos_clientes.obtener_cliente_por_nombre(conexion, "CROMA")
    assert croma is not None
    assert datos_clientes.obtener_cliente_por_nombre(conexion, "CROMA FDEZ.") is None
    sucursales = {s["nombre"] for s in datos_clientes.listar_sucursales(conexion, croma["id"])}
    assert sucursales == {"Principal", "CROMA FDEZ."}

    assert pagina._tabla_hojas.rowCount() == 0
    assert not pagina._boton_confirmar.isEnabled()


def test_leer_archivo_invalido_muestra_error(monkeypatch, app, conexion, tmp_path):
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: QMessageBox.Ok))

    pagina = PaginaImportarExcel(conexion)
    pagina._campo_ruta.setText(str(tmp_path / "no_existe.xlsx"))
    pagina._campo_mes.setText("2024-03")
    pagina._leer_archivo()

    assert pagina._vista_previa is None
    assert not pagina._boton_confirmar.isEnabled()


# --- etapa 7: resolución de conflictos en la pantalla ---


@pytest.fixture
def archivo_con_remito_repetido(tmp_path: Path) -> Path:
    libro = openpyxl.Workbook()
    libro.remove(libro.active)
    ws = libro.create_sheet("LA OPTICA")
    ws.cell(row=1, column=2, value="LA OPTICA")
    for col, valor in enumerate(ENCABEZADO, start=2):
        ws.cell(row=4, column=col, value=valor)
    for i, (numero, monto, final) in enumerate([(45126, 1000, 800), (45126, 2000, 1600)]):
        fila = 5 + i
        ws.cell(row=fila, column=2, value=date(2024, 3, 1))
        ws.cell(row=fila, column=3, value="RTO")
        ws.cell(row=fila, column=4, value=numero)
        ws.cell(row=fila, column=5, value=monto)
        ws.cell(row=fila, column=6, value=20)
        ws.cell(row=fila, column=7, value=final)
    ruta = tmp_path / "con_conflicto.xlsx"
    libro.save(ruta)
    return ruta


def test_conflicto_aparece_con_la_sugerida_preseleccionada(app, conexion, archivo_con_remito_repetido):
    pagina = PaginaImportarExcel(conexion)
    pagina._campo_ruta.setText(str(archivo_con_remito_repetido))
    pagina._campo_mes.setText("2024-03")
    pagina._leer_archivo()

    assert pagina._tabla_conflictos.rowCount() == 1
    conflicto = pagina._vista_previa.conflictos[0]
    combo = pagina._combos_conflicto[conflicto.id]
    assert combo.currentText() == conflicto.sugerida


def test_filtrar_por_tipo_conserva_la_decision_elegida(app, conexion, archivo_con_remito_repetido):
    pagina = PaginaImportarExcel(conexion)
    pagina._campo_ruta.setText(str(archivo_con_remito_repetido))
    pagina._campo_mes.setText("2024-03")
    pagina._leer_archivo()

    conflicto = pagina._vista_previa.conflictos[0]
    pagina._combos_conflicto[conflicto.id].setCurrentText("Omitir este")

    # Filtrar por el tipo del conflicto y volver a "Todos los tipos": la
    # decisión no se pierde al reconstruirse la tabla.
    pagina._campo_filtro_tipo.setCurrentIndex(1)
    pagina._campo_filtro_tipo.setCurrentIndex(0)

    assert pagina._decisiones[conflicto.id] == "Omitir este"
    assert pagina._combos_conflicto[conflicto.id].currentText() == "Omitir este"


def test_aplicar_sugerida_al_filtro_restaura_la_decision(app, conexion, archivo_con_remito_repetido):
    pagina = PaginaImportarExcel(conexion)
    pagina._campo_ruta.setText(str(archivo_con_remito_repetido))
    pagina._campo_mes.setText("2024-03")
    pagina._leer_archivo()

    conflicto = pagina._vista_previa.conflictos[0]
    pagina._combos_conflicto[conflicto.id].setCurrentText("Omitir este")

    pagina._aplicar_sugerida_al_filtro()

    assert pagina._decisiones[conflicto.id] == conflicto.sugerida
    assert pagina._combos_conflicto[conflicto.id].currentText() == conflicto.sugerida


def test_confirmar_respeta_la_decision_de_omitir(monkeypatch, app, conexion, archivo_con_remito_repetido):
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(_DialogoResumenConflictos, "exec", lambda self: None)

    pagina = PaginaImportarExcel(conexion)
    pagina._campo_ruta.setText(str(archivo_con_remito_repetido))
    pagina._campo_mes.setText("2024-03")
    pagina._leer_archivo()

    conflicto = pagina._vista_previa.conflictos[0]
    pagina._combos_conflicto[conflicto.id].setCurrentText("Omitir este")
    pagina._confirmar()

    from ios.data import comprobantes as datos_comprobantes

    cliente = datos_clientes.obtener_cliente_por_nombre(conexion, "LA OPTICA")
    comprobantes = datos_comprobantes.listar_comprobantes(conexion, cliente_id=cliente["id"])
    assert len(comprobantes) == 1


def test_resumen_de_conflictos_exporta_a_excel(monkeypatch, app, conexion, tmp_path, archivo_con_remito_repetido):
    from ios.services.importacion_excel import leer_archivo

    vista = leer_archivo(str(archivo_con_remito_repetido), "2024-03")
    conflicto = vista.conflictos[0]
    dialogo = _DialogoResumenConflictos(vista.conflictos, {conflicto.id: "Omitir este"})

    ruta_salida = tmp_path / "resumen.xlsx"
    monkeypatch.setattr(
        "ios.ui.pages.importar_excel.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: (str(ruta_salida), "")),
    )
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))

    dialogo._exportar_excel()

    assert ruta_salida.exists()
