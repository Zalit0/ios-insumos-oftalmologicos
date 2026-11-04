"""Etapa 6.3 (D5): datos para los gráficos del Resumen mensual."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data.db import conectar
from ios.domain.calculos import calcular_deuda_total
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services.caja import registrar_movimiento_manual
from ios.services.categorias_caja import alta_categoria
from ios.services.cobranzas import AplicacionARemito, Pago, asentar_cobranza
from ios.services.cuenta_corriente import estado_de_cuenta_cliente
from ios.services.graficos_resumen_mensual import (
    deuda_total_12_meses,
    egresos_del_mes_por_categoria,
    iva_venta_vs_compra_12_meses,
    top_clientes_del_mes,
    ultimos_n_meses,
    ultimo_dia_del_mes,
    venta_vs_cobranza_12_meses,
)


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "ios_test.db")
    try:
        yield conexion
    finally:
        conexion.close()


@pytest.fixture
def rto_id(conexion) -> int:
    return conexion.execute("SELECT id FROM tipos_comprobante WHERE abreviatura = 'RTO'").fetchone()["id"]


@pytest.fixture
def efectivo_id(conexion) -> int:
    return conexion.execute("SELECT id FROM formas_pago WHERE nombre = 'Efectivo'").fetchone()["id"]


# --- helpers de meses ---


def test_ultimos_n_meses_cruza_el_anio():
    assert ultimos_n_meses("2024-02", n=3) == ["2023-12", "2024-01", "2024-02"]


def test_ultimos_n_meses_12_termina_en_el_mes_de_referencia():
    meses = ultimos_n_meses("2024-03")
    assert len(meses) == 12
    assert meses[-1] == "2024-03"
    assert meses[0] == "2023-04"


def test_ultimo_dia_del_mes_bisiesto():
    assert ultimo_dia_del_mes("2024-02") == "2024-02-29"


# --- venta vs cobranza / IVA venta vs compra ---


def test_venta_vs_cobranza_usa_el_resumen_del_mes(conexion, rto_id, efectivo_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    comprobante_id = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_id, Decimal("10000")
    )
    asentar_cobranza(
        conexion, cliente_id, "2024-03-10",
        pagos=[Pago(efectivo_id, Decimal("4000"))],
        aplicaciones=[AplicacionARemito(comprobante_id, Decimal("4000"))],
    )

    puntos = venta_vs_cobranza_12_meses(conexion, "2024-03")

    assert len(puntos) == 12
    marzo = next(p for p in puntos if p.mes == "2024-03")
    assert marzo.venta == Decimal("10000")
    assert marzo.cobranza == Decimal("4000")
    assert all(p.venta == Decimal("0") for p in puntos if p.mes != "2024-03")


def test_iva_venta_vs_compra(conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_id, Decimal("12100"), con_iva=True
    )

    puntos = iva_venta_vs_compra_12_meses(conexion, "2024-03")

    marzo = next(p for p in puntos if p.mes == "2024-03")
    assert marzo.iva_venta == Decimal("2100")
    assert marzo.iva_compra == Decimal("0")


# --- deuda total ---


def test_calcular_deuda_total_formula():
    assert calcular_deuda_total(Decimal("10000"), Decimal("4000")) == Decimal("6000")


def test_deuda_total_coincide_con_la_suma_de_saldos_consolidados(conexion, rto_id, efectivo_id):
    croma_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    mirage_id = servicio_clientes.alta_cliente(conexion, nombre="Mirage")
    sucursal_croma = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (croma_id,)
    ).fetchone()["id"]
    sucursal_mirage = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (mirage_id,)
    ).fetchone()["id"]
    comprobante_id = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", croma_id, sucursal_croma, Decimal("10000")
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-03-06", mirage_id, sucursal_mirage, Decimal("5000")
    )
    asentar_cobranza(
        conexion, croma_id, "2024-03-10",
        pagos=[Pago(efectivo_id, Decimal("4000"))],
        aplicaciones=[AplicacionARemito(comprobante_id, Decimal("4000"))],
    )

    puntos = deuda_total_12_meses(conexion, "2024-03")
    marzo = next(p for p in puntos if p.mes == "2024-03")

    suma_consolidada = sum(
        (
            estado_de_cuenta_cliente(conexion, c).saldo_consolidado
            for c in (croma_id, mirage_id)
        ),
        Decimal(0),
    )
    assert marzo.deuda == suma_consolidada
    assert marzo.deuda == Decimal("11000")  # (10000-4000) + 5000


def test_deuda_total_no_cuenta_meses_posteriores(conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-04-05", cliente_id, sucursal_id, Decimal("10000")
    )

    puntos = deuda_total_12_meses(conexion, "2024-03")

    marzo = next(p for p in puntos if p.mes == "2024-03")
    assert marzo.deuda == Decimal("0")


# --- top clientes del mes ---


def test_top_clientes_del_mes_ordena_y_limita(conexion, rto_id):
    nombres_y_montos = [("Croma", "5000"), ("Mirage", "9000"), ("Koral", "1000")]
    for nombre, monto in nombres_y_montos:
        cliente_id = servicio_clientes.alta_cliente(conexion, nombre=nombre)
        sucursal_id = conexion.execute(
            "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
        ).fetchone()["id"]
        servicio_comprobantes.alta_comprobante(
            conexion, rto_id, "1", "2024-03-05", cliente_id, sucursal_id, Decimal(monto)
        )

    top = top_clientes_del_mes(conexion, "2024-03", top=2)

    assert [p.nombre for p in top] == ["Mirage", "Croma"]


# --- egresos de caja del mes por categoría ---


def test_egresos_del_mes_por_categoria_ordenado_de_mayor_a_menor(conexion, efectivo_id):
    insumos_id = alta_categoria(conexion, "Insumos", "egreso")
    alquiler_id = alta_categoria(conexion, "Alquiler", "egreso")
    registrar_movimiento_manual(
        conexion, "2024-03-05 10:00", "egreso", efectivo_id, Decimal("100"), categoria_id=insumos_id
    )
    registrar_movimiento_manual(
        conexion, "2024-03-06 10:00", "egreso", efectivo_id, Decimal("500"), categoria_id=alquiler_id
    )

    subtotales = egresos_del_mes_por_categoria(conexion, "2024-03")

    assert [s.nombre for s in subtotales] == ["Alquiler", "Insumos"]
