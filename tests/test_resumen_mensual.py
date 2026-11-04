"""Etapa 8: resumen mensual (equivalente a la hoja TOTALES)."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services import proveedores as servicio_proveedores
from ios.services.cobranzas import AplicacionARemito, Pago, asentar_cobranza
from ios.services.compras import alta_compra
from ios.services.pagos_proveedor import registrar_pago_proveedor
from ios.services.resumen_mensual import resumen_del_mes


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
def rto_id(conexion) -> int:
    return conexion.execute(
        "SELECT id FROM tipos_comprobante WHERE abreviatura = 'RTO'"
    ).fetchone()["id"]


def test_resumen_cierra_con_los_datos_de_prueba(conexion, rto_id, formas_pago):
    """Caso de aceptación de la etapa: carga comprobantes, cobranzas,
    compras y pagos a proveedores de un mes, y el resumen cierra."""
    conexion.execute("UPDATE configuracion SET comision_pct = '15' WHERE id = 1")
    conexion.commit()

    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=True
    )
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    proveedor_id = servicio_proveedores.alta_proveedor(conexion, nombre="Lentex")

    comprobante_id = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_id, Decimal("10000")
    )
    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("4000"))],
        aplicaciones=[AplicacionARemito(comprobante_id, Decimal("4000"))],
    )
    alta_compra(conexion, proveedor_id, "2024-03-07", "0001", Decimal("3000"), iva=Decimal("500"))
    registrar_pago_proveedor(
        conexion, proveedor_id, "2024-03-12", Decimal("3000"), formas_pago["Transferencia"]
    )

    resumen = resumen_del_mes(conexion, "2024-03")

    comprobante = servicio_comprobantes.listar_comprobantes(conexion, cliente_id=cliente_id)[0]
    assert resumen.total_venta == comprobante["monto_final"]
    assert resumen.total_pagos == Decimal("4000")
    assert resumen.total_saldos == resumen.total_venta - Decimal("4000")
    assert resumen.iva_venta == comprobante["iva_discriminado"]
    assert resumen.iva_compra == Decimal("500")
    assert resumen.iva_deuda == resumen.iva_venta - Decimal("500")
    assert resumen.comision == resumen.total_venta * Decimal("15") / Decimal(100)
    assert resumen.total_compras == Decimal("3000")
    assert resumen.depositos == Decimal("3000")
    assert resumen.ganancia_teorica == (
        resumen.total_venta - resumen.comision - resumen.total_compras - resumen.iva_deuda
    )


def test_recibo_de_abril_aplicado_a_remito_de_marzo_suma_en_los_pagos_de_marzo(
    conexion, rto_id, formas_pago
):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Mirage")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    comprobante_id = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-20", cliente_id, sucursal_id, Decimal("1000"),
        descuento_pct=Decimal("0"), con_iva=False,
    )

    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-04-05",  # el recibo es de abril
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1000"))],
        aplicaciones=[AplicacionARemito(comprobante_id, Decimal("1000"))],
    )

    resumen_marzo = resumen_del_mes(conexion, "2024-03")
    resumen_abril = resumen_del_mes(conexion, "2024-04")

    assert resumen_marzo.total_pagos == Decimal("1000")
    assert resumen_abril.total_pagos == Decimal("0")


def test_cambiar_de_mes_no_modifica_totales_de_otros_meses(conexion, rto_id, formas_pago):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Koral", descuento_default=Decimal("0"), con_iva_default=False
    )
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_id, Decimal("1000")
    )

    resumen_marzo_antes = resumen_del_mes(conexion, "2024-03")

    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-04-05", cliente_id, sucursal_id, Decimal("5000")
    )

    resumen_marzo_despues = resumen_del_mes(conexion, "2024-03")
    assert resumen_marzo_despues.total_venta == resumen_marzo_antes.total_venta
