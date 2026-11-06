"""Pruebas funcionales de la pantalla Recepción de pedidos (plan de detalle
de comprobantes, etapa 4/5.3): resolver cristal por cristal (recibido,
recibido con diferencia, pendiente o cancelado) con los botones de acción
de cada fila (sin seleccionar una fila aparte) en las tablas separadas de
reposición y especiales, cerrar el pedido recién cuando no queda ninguna
sin resolver, y la factura de compra asociada."""

import os
from decimal import Decimal
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

from ios.data import compras as datos_compras
from ios.data.db import conectar
from ios.services import comprobantes as servicio_comprobantes
from ios.services import proveedores as servicio_proveedores
from ios.services.comprobantes import RenglonDetalle
from ios.services.pedidos_proveedor import (
    agregar_linea_especial,
    alta_pedido,
    generar_lineas_reposicion,
    listar_lineas_pedido,
    listar_pedidos,
    marcar_linea_pendiente,
    marcar_linea_recibida,
    marcar_pedido_realizado,
)
from ios.services.tipos_cristal import alta_tipo_cristal
from ios.ui.pages.recepcion_pedidos import PaginaRecepcionPedidos


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
def proveedor_id(conexion) -> int:
    return servicio_proveedores.alta_proveedor(conexion, nombre="Essilor")


def _pedido_realizado(conexion, proveedor_id, *descripciones):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    for descripcion in descripciones:
        agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion=descripcion)
    marcar_pedido_realizado(conexion, pedido_id)
    return pedido_id


def test_solo_lista_pedidos_realizados(app, conexion, proveedor_id):
    pedido_realizado_id = _pedido_realizado(conexion, proveedor_id, "Cristal")
    alta_pedido(conexion, proveedor_id, "2026-03-15")  # queda en carga, no debería listarse

    pagina = PaginaRecepcionPedidos(conexion)

    assert pagina._campo_pedido.count() == 1
    assert pagina._campo_pedido.currentData() == pedido_realizado_id


def test_separa_reposicion_de_especiales_en_tablas_distintas(app, conexion, rto_id, proveedor_id):
    from ios.services import clientes as servicio_clientes

    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"),
        con_iva_default=False, sucursales=["Croma"],
    )
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    servicio_comprobantes.alta_comprobante_con_detalle(
        conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
        renglones=[RenglonDetalle(graduacion="Neutro", cantidad=2, tipo_cristal_id=organico)],
    )
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    generar_lineas_reposicion(conexion, pedido_id, "2026-03-01", "2026-03-31")
    agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Ultravex 1.74")
    marcar_pedido_realizado(conexion, pedido_id)

    pagina = PaginaRecepcionPedidos(conexion)

    assert pagina._tabla_especiales.rowCount() == 1
    assert pagina._tabla_especiales.item(0, 0).text() == "Ultravex 1.74"
    assert pagina._tabla_reposicion.rowCount() == 1
    assert pagina._tabla_reposicion.item(0, 0).text() == "Orgánico blanco"


def _linea_id(tabla, fila: int, columna_id: int = 0) -> int:
    return tabla.item(fila, columna_id).data(Qt.UserRole)


def test_marcar_linea_recibida_actualiza_la_tabla(monkeypatch, app, conexion, proveedor_id):
    from ios.ui.pages import recepcion_pedidos as modulo

    monkeypatch.setattr(modulo.QDialog, "exec", lambda self: QDialog.Accepted)
    _pedido_realizado(conexion, proveedor_id, "Cristal")
    pagina = PaginaRecepcionPedidos(conexion)

    pagina._marcar_linea_recibida(_linea_id(pagina._tabla_especiales, 0))

    assert pagina._tabla_especiales.item(0, 5).text() == "Recibida"


def test_el_dialogo_de_graduacion_recibida_precarga_la_solicitada(app, conexion):
    from ios.ui.pages.recepcion_pedidos import _DialogoGraduacionRecibida

    dialogo = _DialogoGraduacionRecibida("ESF -2.00 CIL +0.00")

    assert dialogo.campo_esferico.value() == pytest.approx(-2.00)
    assert dialogo.campo_cilindrico.value() == pytest.approx(0.00)


def test_marcar_linea_recibida_con_graduacion_distinta_la_distingue(monkeypatch, app, conexion, proveedor_id):
    """Si se recibió es porque el cliente lo aceptó así — no hace falta un
    paso de aprobación aparte; pero la tabla sí distingue que llegó
    distinto de lo pedido."""
    from ios.ui.pages import recepcion_pedidos as modulo

    def _exec_con_diferencia(self):
        self.campo_esferico.setValue(-2.25)
        return QDialog.Accepted

    monkeypatch.setattr(modulo.QDialog, "exec", _exec_con_diferencia)
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    agregar_linea_especial(
        conexion, pedido_id, cantidad=1, descripcion="Cristal",
        graduacion_solicitada="ESF -2.00 CIL +0.00",
    )
    marcar_pedido_realizado(conexion, pedido_id)
    pagina = PaginaRecepcionPedidos(conexion)

    pagina._marcar_linea_recibida(_linea_id(pagina._tabla_especiales, 0))

    assert pagina._tabla_especiales.item(0, 5).text() == "Recibida con diferencia"


def test_marcar_linea_pendiente_y_cancelar_linea(app, conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Pendiente")
    agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Cancelada")
    marcar_pedido_realizado(conexion, pedido_id)
    pagina = PaginaRecepcionPedidos(conexion)

    filas = {pagina._tabla_especiales.item(f, 0).text(): f for f in range(pagina._tabla_especiales.rowCount())}
    pagina._marcar_linea_pendiente(_linea_id(pagina._tabla_especiales, filas["Pendiente"]))
    pagina._cancelar_linea(_linea_id(pagina._tabla_especiales, filas["Cancelada"]))

    estados = {
        pagina._tabla_especiales.item(f, 0).text(): pagina._tabla_especiales.item(f, 5).text()
        for f in range(pagina._tabla_especiales.rowCount())
    }
    assert estados["Pendiente"] == "Pendiente (se pide de nuevo)"
    assert estados["Cancelada"] == "Cancelada"


def test_boton_marcar_recibido_deshabilitado_hasta_resolver_todo(monkeypatch, app, conexion, proveedor_id):
    from ios.ui.pages import recepcion_pedidos as modulo

    monkeypatch.setattr(modulo.QDialog, "exec", lambda self: QDialog.Accepted)
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Cristal")
    marcar_pedido_realizado(conexion, pedido_id)
    pagina = PaginaRecepcionPedidos(conexion)

    assert not pagina._boton_marcar_recibido.isEnabled()

    pagina._marcar_linea_recibida(_linea_id(pagina._tabla_especiales, 0))

    assert pagina._boton_marcar_recibido.isEnabled()


def test_marcar_pedido_recibido_sin_pendientes(monkeypatch, app, conexion, proveedor_id):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Rejected)
    pedido_id = _pedido_realizado(conexion, proveedor_id, "Cristal")
    linea_id = listar_lineas_pedido(conexion, pedido_id)[0]["id"]
    marcar_linea_recibida(conexion, linea_id, None)
    pagina = PaginaRecepcionPedidos(conexion)

    pagina._marcar_pedido_recibido()

    pedidos = {p["id"]: p["estado"] for p in listar_pedidos(conexion, proveedor_id=proveedor_id)}
    assert pedidos[pedido_id] == "recibido"
    assert pagina._campo_pedido.count() == 0  # ya no queda ningún pedido realizado


def test_marcar_pedido_recibido_usa_el_pedido_en_carga_existente(monkeypatch, app, conexion, proveedor_id):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Rejected)
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    linea_id = agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="No llegó")
    marcar_linea_pendiente(conexion, linea_id)
    marcar_pedido_realizado(conexion, pedido_id)
    pedido_en_carga_id = alta_pedido(conexion, proveedor_id, "2026-03-15")
    pagina = PaginaRecepcionPedidos(conexion)

    pagina._marcar_pedido_recibido()

    pedidos = listar_pedidos(conexion, proveedor_id=proveedor_id)
    estados = {p["id"]: p["estado"] for p in pedidos}
    assert estados[pedido_id] == "recibido"
    assert estados[pedido_en_carga_id] == "en_carga"
    assert len(pedidos) == 2  # no se creó un tercer pedido


def test_marcar_pedido_recibido_ofrece_crear_uno_nuevo_si_no_hay_en_carga(
    monkeypatch, app, conexion, proveedor_id
):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.Rejected)
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    linea_id = agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="No llegó")
    marcar_linea_pendiente(conexion, linea_id)
    marcar_pedido_realizado(conexion, pedido_id)
    pagina = PaginaRecepcionPedidos(conexion)

    pagina._marcar_pedido_recibido()

    pedidos = listar_pedidos(conexion, proveedor_id=proveedor_id)
    assert len(pedidos) == 2
    nuevo = [p for p in pedidos if p["id"] != pedido_id][0]
    assert nuevo["estado"] == "en_carga"


def test_marcar_pedido_recibido_abre_el_dialogo_de_compra_y_la_vincula(
    monkeypatch, app, conexion, proveedor_id
):
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    llamadas = []

    def _exec_falso(self):
        llamadas.append(self)
        self.campo_numero.setText("F-001")
        self.campo_monto.setValue(1000)
        self._guardar()
        return QDialog.Accepted

    monkeypatch.setattr(QDialog, "exec", _exec_falso)
    pedido_id = _pedido_realizado(conexion, proveedor_id, "Cristal")
    linea_id = listar_lineas_pedido(conexion, pedido_id)[0]["id"]
    marcar_linea_recibida(conexion, linea_id, None)
    pagina = PaginaRecepcionPedidos(conexion)

    pagina._marcar_pedido_recibido()

    assert len(llamadas) == 1
    compra = datos_compras.obtener_compra_por_pedido(conexion, pedido_id)
    assert compra is not None
    assert compra["numero_factura"] == "F-001"


@pytest.fixture
def rto_id(conexion) -> int:
    return conexion.execute(
        "SELECT id FROM tipos_comprobante WHERE abreviatura = 'RTO'"
    ).fetchone()["id"]
