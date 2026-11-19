"""Pruebas del servicio de pagos a proveedores: registrar un pago y
corregirlo (monto, forma de pago, cheque entregado) sin dejar la caja
descuadrada ni duplicar movimientos si se corrige más de una vez."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data import caja as datos_caja
from ios.data import cheques as datos_cheques
from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import proveedores as servicio_proveedores
from ios.services.pagos_proveedor import (
    editar_pago_proveedor,
    listar_pagos_proveedor,
    registrar_pago_proveedor,
)


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "ios_test.db")
    try:
        yield conexion
    finally:
        conexion.close()


@pytest.fixture
def formas_pago(conexion) -> dict[str, int]:
    filas = conexion.execute("SELECT id, nombre FROM formas_pago").fetchall()
    return {fila["nombre"]: fila["id"] for fila in filas}


@pytest.fixture
def lentex(conexion) -> int:
    return servicio_proveedores.alta_proveedor(conexion, nombre="Lentex")


@pytest.fixture
def croma(conexion) -> int:
    return servicio_clientes.alta_cliente(conexion, nombre="Croma")


def _total_disponible(conexion, forma_pago_id: int) -> Decimal:
    movimientos = conexion.execute(
        "SELECT tipo, monto FROM movimientos_caja WHERE forma_pago_id = ?", (forma_pago_id,)
    ).fetchall()
    total = Decimal(0)
    for movimiento in movimientos:
        total += movimiento["monto"] if movimiento["tipo"] == "ingreso" else -movimiento["monto"]
    return total


def test_editar_el_monto_corrige_el_movimiento_de_caja(conexion, formas_pago, lentex):
    """El bug real: un monto cargado con el separador decimal equivocado
    quedó 100 veces más grande."""
    efectivo = formas_pago["Efectivo"]
    pago_id = registrar_pago_proveedor(conexion, lentex, "2024-03-10", Decimal("1500000"), efectivo)

    editar_pago_proveedor(conexion, pago_id, fecha_hoy="2024-03-11", monto=Decimal("15000"))

    pago = listar_pagos_proveedor(conexion)[0]
    assert pago["monto"] == Decimal("15000")
    # -15000 es lo único que debería haber salido de la caja en total.
    assert _total_disponible(conexion, efectivo) == Decimal("-15000")


def test_corregir_dos_veces_no_duplica_el_movimiento_anterior(conexion, formas_pago, lentex):
    efectivo = formas_pago["Efectivo"]
    pago_id = registrar_pago_proveedor(conexion, lentex, "2024-03-10", Decimal("1500000"), efectivo)

    editar_pago_proveedor(conexion, pago_id, fecha_hoy="2024-03-11", monto=Decimal("15000"))
    editar_pago_proveedor(conexion, pago_id, fecha_hoy="2024-03-12", monto=Decimal("16000"))

    assert _total_disponible(conexion, efectivo) == Decimal("-16000")


def test_editar_solo_la_referencia_no_toca_la_caja(conexion, formas_pago, lentex):
    efectivo = formas_pago["Efectivo"]
    pago_id = registrar_pago_proveedor(conexion, lentex, "2024-03-10", Decimal("15000"), efectivo)
    movimientos_antes = conexion.execute("SELECT COUNT(*) AS n FROM movimientos_caja").fetchone()["n"]

    editar_pago_proveedor(conexion, pago_id, fecha_hoy="2024-03-11", referencia="Factura 123")

    movimientos_despues = conexion.execute("SELECT COUNT(*) AS n FROM movimientos_caja").fetchone()["n"]
    assert movimientos_despues == movimientos_antes
    assert listar_pagos_proveedor(conexion)[0]["referencia"] == "Factura 123"


def test_cambiar_la_forma_de_pago_mueve_el_movimiento_a_la_nueva(conexion, formas_pago, lentex):
    efectivo = formas_pago["Efectivo"]
    transferencia = formas_pago["Transferencia"]
    pago_id = registrar_pago_proveedor(conexion, lentex, "2024-03-10", Decimal("15000"), efectivo)

    editar_pago_proveedor(conexion, pago_id, fecha_hoy="2024-03-11", forma_pago_id=transferencia)

    assert _total_disponible(conexion, efectivo) == Decimal("0")
    assert _total_disponible(conexion, transferencia) == Decimal("-15000")


def test_editar_con_un_cheque_nuevo_libera_el_viejo_y_ocupa_el_nuevo(conexion, formas_pago, lentex, croma):
    cheque_forma = formas_pago["Cheque"]
    cheque_viejo = datos_cheques.insertar_cheque(
        conexion, "1", croma, "Nación", Decimal("15000"), "2024-04-01", recibo_origen_id=None
    )
    cheque_nuevo = datos_cheques.insertar_cheque(
        conexion, "2", croma, "Nación", Decimal("15000"), "2024-04-01", recibo_origen_id=None
    )
    pago_id = registrar_pago_proveedor(
        conexion, lentex, "2024-03-10", Decimal("15000"), cheque_forma,
        cheque_entregado_id=cheque_viejo,
    )

    editar_pago_proveedor(conexion, pago_id, fecha_hoy="2024-03-11", cheque_entregado_id=cheque_nuevo)

    assert datos_cheques.obtener_cheque(conexion, cheque_viejo)["estado"] == "en_cartera"
    assert datos_cheques.obtener_cheque(conexion, cheque_nuevo)["estado"] == "entregado_a_proveedor"


def test_no_se_puede_usar_un_cheque_que_no_esta_en_cartera(conexion, formas_pago, lentex, croma):
    cheque_forma = formas_pago["Cheque"]
    cheque_ya_usado = datos_cheques.insertar_cheque(
        conexion, "1", croma, "Nación", Decimal("15000"), "2024-04-01", recibo_origen_id=None,
        estado="entregado_a_proveedor",
    )
    pago_id = registrar_pago_proveedor(conexion, lentex, "2024-03-10", Decimal("15000"), cheque_forma)

    with pytest.raises(ValueError):
        editar_pago_proveedor(conexion, pago_id, fecha_hoy="2024-03-11", cheque_entregado_id=cheque_ya_usado)


def test_editar_un_pago_inexistente_falla(conexion):
    with pytest.raises(ValueError):
        editar_pago_proveedor(conexion, 999, fecha_hoy="2024-03-11", monto=Decimal("1"))
