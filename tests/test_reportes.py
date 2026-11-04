"""Reportes en PDF y Excel (docs/PLAN.md, sección "Reportes y
dashboard")."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from ios.data.db import conectar
from ios.reports.cheques import generar_pdf_cheques_en_cartera
from ios.reports.cierre_caja import generar_pdf_cierre_caja
from ios.reports.deudores import generar_excel_deudores, generar_pdf_deudores
from ios.reports.estado_cuenta import (
    _mes_anio,
    generar_pdf_estado_cuenta,
    generar_pdf_estado_cuenta_pendientes,
    generar_pdf_estado_cuenta_periodo,
    generar_pdf_historial_movimientos,
)
from ios.reports.exportacion_contador import generar_excel_exportacion_contador
from ios.reports.flujo_caja import generar_excel_flujo_caja
from ios.reports.iva_mes import generar_excel_iva_mes
from ios.reports.recibo import generar_pdf_recibo
from ios.reports.resumen_mensual import generar_excel_resumen_mensual, generar_pdf_resumen_mensual
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services import proveedores as servicio_proveedores
from ios.services.caja import abrir_caja, cerrar_caja, registrar_movimiento_manual
from ios.services.cobranzas import AplicacionARemito, DatosCheque, Pago, asentar_cobranza
from ios.services.compras import alta_compra
from ios.services.pagos_proveedor import registrar_pago_proveedor


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


@pytest.fixture
def escenario(conexion, rto_id, formas_pago):
    """Croma con un remito, un pago mixto (efectivo + cheque), y un
    segundo remito sin pagar: deja saldo y un cheque en cartera."""
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("25"), con_iva_default=True,
        sucursales=["Croma", "Croma Fdez."],
    )
    sucursales = conexion.execute(
        "SELECT id, nombre FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchall()
    sucursal_croma = next(s["id"] for s in sucursales if s["nombre"] == "Croma")

    comprobante_1 = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_croma, Decimal("1000")
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-01-01", cliente_id, sucursal_croma, Decimal("2000")
    )

    recibo_id = asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-10",
        pagos=[
            Pago(formas_pago["Efectivo"], Decimal("500")),
            Pago(formas_pago["Cheque"], Decimal("250"),
                 cheque=DatosCheque("001", "Banco Nación", "2024-04-01")),
        ],
        aplicaciones=[AplicacionARemito(comprobante_1, Decimal("750"))],
    )

    return {"cliente_id": cliente_id, "recibo_id": recibo_id}


def test_pdf_recibo_se_genera(conexion, escenario, tmp_path):
    ruta = generar_pdf_recibo(conexion, escenario["recibo_id"], tmp_path / "recibo.pdf")
    assert ruta.exists()
    assert ruta.stat().st_size > 0


def test_pdf_estado_cuenta_se_genera(conexion, escenario, tmp_path):
    ruta = generar_pdf_estado_cuenta(conexion, escenario["cliente_id"], tmp_path / "estado.pdf")
    assert ruta.exists()
    assert ruta.stat().st_size > 0


def test_pdf_estado_cuenta_periodo_se_genera(conexion, escenario, tmp_path):
    ruta = generar_pdf_estado_cuenta_periodo(
        conexion, escenario["cliente_id"], "2024-03-01", "2024-03-31", tmp_path / "estado_periodo.pdf"
    )
    assert ruta.exists()
    assert ruta.stat().st_size > 0


def test_mes_anio_formatea_solo_mes_y_anio():
    assert _mes_anio("2024-02-20") == "02/2024"
    assert _mes_anio(None) == "?"


def test_pdf_estado_cuenta_pendientes_se_genera(conexion, escenario, tmp_path):
    ruta = generar_pdf_estado_cuenta_pendientes(
        conexion, escenario["cliente_id"], tmp_path / "estado_pendientes.pdf"
    )
    assert ruta.exists()
    assert ruta.stat().st_size > 0


def test_pdf_historial_movimientos_se_genera(conexion, escenario, tmp_path):
    ruta = generar_pdf_historial_movimientos(
        conexion, escenario["cliente_id"], "2024-01-01", "2024-03-31", tmp_path / "historial.pdf"
    )
    assert ruta.exists()
    assert ruta.stat().st_size > 0


def test_pdf_cierre_caja_se_genera(conexion, formas_pago, escenario, tmp_path):
    cierre_id = abrir_caja(conexion, "2024-03-10")
    cerrar_caja(conexion, cierre_id, arqueos={
        formas_pago["Efectivo"]: Decimal("500"), formas_pago["Cheque"]: Decimal("250"),
    })

    ruta = generar_pdf_cierre_caja(conexion, cierre_id, tmp_path / "cierre.pdf")
    assert ruta.exists()
    assert ruta.stat().st_size > 0


def test_pdf_cheques_en_cartera_se_genera(conexion, escenario, tmp_path):
    ruta = generar_pdf_cheques_en_cartera(conexion, tmp_path / "cheques.pdf")
    assert ruta.exists()
    assert ruta.stat().st_size > 0


def test_pdf_y_excel_deudores(conexion, escenario, tmp_path):
    ruta_pdf = generar_pdf_deudores(conexion, "2024-03-20", tmp_path / "deudores.pdf")
    assert ruta_pdf.exists()

    ruta_excel = generar_excel_deudores(conexion, "2024-03-20", tmp_path / "deudores.xlsx")
    libro = openpyxl.load_workbook(ruta_excel)
    ws = libro["Deudores"]
    fila = [c.value for c in ws[2]]
    assert fila[0] == "Croma"
    # saldo: remito1 250 pendiente + remito2 1500 pendiente = 1750
    # remito1 (final 750) queda pago; remito2 (final 1500) queda pendiente.
    assert fila[1] == 1500.0
    assert fila[3] == (date(2024, 3, 20) - date(2024, 1, 1)).days


def test_pdf_y_excel_resumen_mensual(conexion, escenario, tmp_path):
    ruta_pdf = generar_pdf_resumen_mensual(conexion, "2024-03", tmp_path / "resumen.pdf")
    assert ruta_pdf.exists()

    ruta_excel = generar_excel_resumen_mensual(conexion, "2024-03", tmp_path / "resumen.xlsx")
    libro = openpyxl.load_workbook(ruta_excel)
    ws = libro["Resumen"]
    valores = {fila[0].value: fila[1].value for fila in ws.iter_rows(min_row=3) if fila[0].value}
    assert valores["Total venta"] == 750.0


def test_excel_iva_mes(conexion, rto_id, tmp_path):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("25"), con_iva_default=True
    )
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_id, Decimal("104544")
    )
    proveedor_id = servicio_proveedores.alta_proveedor(conexion, nombre="Lentex")
    alta_compra(conexion, proveedor_id, "2024-03-07", "0001", Decimal("5000"), iva=Decimal("1000"))

    ruta = generar_excel_iva_mes(conexion, "2024-03", tmp_path / "iva.xlsx")
    libro = openpyxl.load_workbook(ruta)
    ws = libro["Resumen"]
    assert ws.cell(row=2, column=2).value == 13608.0
    assert ws.cell(row=3, column=2).value == 1000.0
    assert ws.cell(row=4, column=2).value == 12608.0

    assert libro["Ventas"].max_row == 2
    assert libro["Compras"].max_row == 2


def test_excel_flujo_caja(conexion, formas_pago, escenario, tmp_path):
    registrar_movimiento_manual(
        conexion, "2024-03-10", "egreso", formas_pago["Efectivo"], Decimal("50")
    )

    ruta = generar_excel_flujo_caja(conexion, "2024-03-01", "2024-03-31", tmp_path / "flujo.xlsx")
    libro = openpyxl.load_workbook(ruta)
    ws = libro["Por día"]
    fila = [c.value for c in ws[2]]
    assert fila[0] == "2024-03-10"
    assert fila[1] == 750.0  # 500 efectivo + 250 cheque
    assert fila[2] == 50.0
    assert fila[4] == 700.0  # saldo acumulado


def test_excel_exportacion_contador(conexion, escenario, tmp_path):
    ruta = generar_excel_exportacion_contador(
        conexion, "2024-01-01", "2024-03-31", tmp_path / "export.xlsx"
    )
    libro = openpyxl.load_workbook(ruta)
    assert libro["Comprobantes"].max_row == 3  # encabezado + 2 remitos
    assert libro["Recibos"].max_row == 2  # encabezado + 1 recibo
    assert libro["Movimientos de caja"].max_row == 3  # efectivo + cheque
