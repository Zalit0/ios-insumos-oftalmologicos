"""Etapa 8 y rediseño del Dashboard (docs/AJUSTES_V1.1.md): indicadores
de la pantalla de inicio."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services import proveedores as servicio_proveedores
from ios.services.caja import abrir_caja, cerrar_caja
from ios.services.cobranzas import AplicacionARemito, Pago, aplicar_saldo_a_favor, asentar_cobranza
from ios.services.compras import alta_compra
from ios.services.dashboard import (
    actividad_comercial_del_mes,
    comparacion_cobranzas,
    comparacion_ventas,
    deuda_de_lo_vendido_del_mes,
    deuda_total,
    estado_de_caja_del_dia,
    evolucion_ventas_cobranzas_12_meses,
    mes_anterior,
    porcentaje_deuda_mayor_a_30_dias,
    saldos_por_antiguedad,
    top_clientes_por_saldo,
    total_remitos_cobrados_del_mes,
    venta_y_cobranza_mes_actual_vs_anterior,
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
def rto_id(conexion) -> int:
    return conexion.execute(
        "SELECT id FROM tipos_comprobante WHERE abreviatura = 'RTO'"
    ).fetchone()["id"]


def _nueva_sucursal(conexion, cliente_id):
    return conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]


def test_mes_anterior():
    assert mes_anterior("2024-03") == "2024-02"
    assert mes_anterior("2024-01") == "2023-12"


def test_deuda_total_suma_solo_saldos_positivos(conexion, rto_id):
    croma_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", croma_id, _nueva_sucursal(conexion, croma_id),
        Decimal("1000"),
    )
    servicio_clientes.alta_cliente(conexion, nombre="Mirage")  # sin remitos, no suma deuda

    assert deuda_total(conexion) == Decimal("1000")


def test_top_clientes_por_saldo_ordena_de_mayor_a_menor(conexion, rto_id):
    croma_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    mirage_id = servicio_clientes.alta_cliente(
        conexion, nombre="Mirage", descuento_default=Decimal("0"), con_iva_default=False
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", croma_id, _nueva_sucursal(conexion, croma_id),
        Decimal("1000"),
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-03-05", mirage_id, _nueva_sucursal(conexion, mirage_id),
        Decimal("5000"),
    )

    top = top_clientes_por_saldo(conexion, cantidad=10)

    assert [c.nombre for c in top[:2]] == ["Mirage", "Croma"]


def test_venta_y_cobranza_mes_actual_vs_anterior(conexion, rto_id, formas_pago):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    sucursal_id = _nueva_sucursal(conexion, cliente_id)
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-02-05", cliente_id, sucursal_id, Decimal("1000")
    )
    comprobante_marzo = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-03-05", cliente_id, sucursal_id, Decimal("3000")
    )
    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("3000"))],
        aplicaciones=[AplicacionARemito(comprobante_marzo, Decimal("3000"))],
    )

    comparativo = venta_y_cobranza_mes_actual_vs_anterior(conexion, "2024-03")

    assert comparativo["venta_mes_actual"] == Decimal("3000")
    assert comparativo["venta_mes_anterior"] == Decimal("1000")
    assert comparativo["cobranza_mes_actual"] == Decimal("3000")
    assert comparativo["cobranza_mes_anterior"] == Decimal("0")


def test_saldos_por_antiguedad_agrupa_segun_dias_desde_la_fecha(conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    sucursal_id = _nueva_sucursal(conexion, cliente_id)
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-01", cliente_id, sucursal_id, Decimal("1000")
    )  # 10 días: bucket 0-30
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-01-01", cliente_id, sucursal_id, Decimal("2000")
    )  # 70 días: bucket 61-90

    totales = saldos_por_antiguedad(conexion, fecha_referencia="2024-03-11")

    assert totales["0-30"] == Decimal("1000")
    assert totales["61-90"] == Decimal("2000")
    assert totales["31-60"] == Decimal("0")
    assert totales["91+"] == Decimal("0")


def test_saldos_por_antiguedad_descuenta_el_saldo_a_favor_del_propio_cliente_del_remito_mas_viejo(
    conexion, rto_id, formas_pago
):
    """Reproduce la inconsistencia detectada en la auditoría: si no se
    descuenta el saldo a favor, la suma de los rangos quedaba por encima
    de la deuda total (docs/AJUSTES_V1.1.md, rediseño del Dashboard)."""
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    sucursal_id = _nueva_sucursal(conexion, cliente_id)
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-01-01", cliente_id, sucursal_id, Decimal("1000")
    )  # 70 días antes de la referencia: bucket 61-90 (el remito más viejo)
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-03-01", cliente_id, sucursal_id, Decimal("2000")
    )  # 10 días antes: bucket 0-30
    asentar_cobranza(
        conexion, cliente_id, "2024-03-05",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("500"))],
        aplicaciones=[],
    )  # $500 de saldo a favor, sin aplicar a ningún remito

    antiguedad = saldos_por_antiguedad(conexion, fecha_referencia="2024-03-11")

    assert deuda_total(conexion) == Decimal("2500")
    assert antiguedad["61-90"] == Decimal("500")  # el remito más viejo absorbe el crédito primero
    assert antiguedad["0-30"] == Decimal("2000")
    assert sum(antiguedad.values(), Decimal(0)) == deuda_total(conexion)


def test_saldos_por_antiguedad_no_usa_el_saldo_a_favor_de_un_cliente_para_compensar_a_otro(
    conexion, rto_id, formas_pago
):
    deudor_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    acreedor_id = servicio_clientes.alta_cliente(
        conexion, nombre="Mirage", descuento_default=Decimal("0"), con_iva_default=False
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-01", deudor_id, _nueva_sucursal(conexion, deudor_id),
        Decimal("1000"),
    )
    # Mirage tiene puro saldo a favor (sin remitos): no debe compensar la deuda de Croma.
    asentar_cobranza(
        conexion, acreedor_id, "2024-03-05",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("2000"))],
        aplicaciones=[],
    )

    antiguedad = saldos_por_antiguedad(conexion, fecha_referencia="2024-03-11")

    assert antiguedad["0-30"] == Decimal("1000")
    assert deuda_total(conexion) == Decimal("1000")


def test_comparacion_ventas_usa_el_mismo_rango_de_dias_no_el_mes_anterior_completo(conexion, rto_id):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    sucursal_id = _nueva_sucursal(conexion, cliente_id)
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-09-10", cliente_id, sucursal_id, Decimal("1000")
    )  # dentro del rango equivalente (01 al 20 de septiembre)
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-09-25", cliente_id, sucursal_id, Decimal("5000")
    )  # fuera del rango equivalente: no debe contar
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "3", "2024-10-15", cliente_id, sucursal_id, Decimal("3000")
    )

    comparacion = comparacion_ventas(conexion, date(2024, 10, 20))

    assert comparacion.total_actual == Decimal("3000")
    assert comparacion.variacion_mensual.monto == Decimal("2000")
    assert comparacion.variacion_mensual.porcentaje == Decimal("200")


def test_comparacion_cobranzas_usa_la_fecha_del_recibo_no_la_del_remito_que_cubre(
    conexion, rto_id, formas_pago
):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    sucursal_id = _nueva_sucursal(conexion, cliente_id)
    remito_viejo = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-08-01", cliente_id, sucursal_id, Decimal("1000")
    )
    asentar_cobranza(
        conexion, cliente_id, "2024-10-05",
        pagos=[
            Pago(formas_pago["Efectivo"], Decimal("600")),
            Pago(formas_pago["Transferencia"], Decimal("400")),
        ],
        aplicaciones=[AplicacionARemito(remito_viejo, Decimal("1000"))],
    )

    comparacion = comparacion_cobranzas(conexion, date(2024, 10, 20))

    # Se cobra en octubre (fecha del recibo), una sola vez (no 600 + 400
    # por separado): el remito es de agosto, pero eso no importa acá.
    assert comparacion.total_actual == Decimal("1000")


def test_aplicar_saldo_a_favor_no_genera_una_cobranza_nueva(conexion, rto_id, formas_pago):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    sucursal_id = _nueva_sucursal(conexion, cliente_id)
    remito_id = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-10-10", cliente_id, sucursal_id, Decimal("500")
    )
    asentar_cobranza(
        conexion, cliente_id, "2024-09-15",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("500"))],
        aplicaciones=[],
    )  # queda como saldo a favor, sin aplicar a nada

    aplicar_saldo_a_favor(conexion, cliente_id, [AplicacionARemito(remito_id, Decimal("500"))])

    comparacion = comparacion_cobranzas(conexion, date(2024, 10, 20))

    assert comparacion.total_actual == Decimal("0")  # nada se cobró en octubre


def test_evolucion_ventas_cobranzas_12_meses(conexion, rto_id, formas_pago):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    sucursal_id = _nueva_sucursal(conexion, cliente_id)
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-05-10", cliente_id, sucursal_id, Decimal("1000")
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-10-10", cliente_id, sucursal_id, Decimal("2000")
    )
    asentar_cobranza(
        conexion, cliente_id, "2024-10-12",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("2000"))],
        aplicaciones=[],
    )

    puntos = evolucion_ventas_cobranzas_12_meses(conexion, date(2024, 10, 20))

    assert len(puntos) == 12
    assert [p.mes for p in puntos][-1] == "2024-10"
    por_mes = {p.mes: p for p in puntos}
    assert por_mes["2024-05"].venta == Decimal("1000")
    assert por_mes["2024-05"].cobranza == Decimal("0")
    assert por_mes["2024-10"].venta == Decimal("2000")
    assert por_mes["2024-10"].cobranza == Decimal("2000")


def test_actividad_comercial_del_mes(conexion, rto_id):
    proveedor_id = servicio_proveedores.alta_proveedor(conexion, nombre="Lentes SA")
    alta_compra(conexion, proveedor_id, "2024-10-05", "F-1", Decimal("1000"))
    alta_compra(conexion, proveedor_id, "2024-10-15", "F-2", Decimal("500"))

    croma_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    sucursal_principal = _nueva_sucursal(conexion, croma_id)
    sucursal_fdez = servicio_clientes.alta_sucursal(conexion, croma_id, "Croma Fdez.")
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-10-10", croma_id, sucursal_principal, Decimal("1000")
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-10-12", croma_id, sucursal_fdez, Decimal("2000")
    )
    comprobante_anulado = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "3", "2024-10-14", croma_id, sucursal_principal, Decimal("500")
    )
    servicio_comprobantes.anular_comprobante(conexion, comprobante_anulado)

    actividad = actividad_comercial_del_mes(conexion, "2024-10")

    assert actividad.total_compras == Decimal("1500")
    assert actividad.clientes_activos == 1  # Croma cuenta una sola vez (dos sucursales)
    assert actividad.remitos_emitidos == 2  # el anulado no cuenta


def test_total_remitos_cobrados_del_mes_usa_la_fecha_del_remito_no_la_del_recibo(
    conexion, rto_id, formas_pago
):
    """Complementa a comparacion_cobranzas: mide cuánto de lo facturado
    EN el mes ya está cobrado, sin importar cuándo llegó el pago —lo
    opuesto a "Cobranzas del mes", que es por fecha del recibo
    (docs/AJUSTES_V1.1.md, rediseño del Dashboard)."""
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    sucursal_id = _nueva_sucursal(conexion, cliente_id)
    remito_octubre = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-10-10", cliente_id, sucursal_id, Decimal("1000")
    )
    remito_septiembre = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-09-10", cliente_id, sucursal_id, Decimal("2000")
    )
    # El recibo es de octubre, pero cobra un remito viejo (de septiembre):
    # no debe contar como "remito de octubre cobrado".
    asentar_cobranza(
        conexion, cliente_id, "2024-10-15",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("2800"))],
        aplicaciones=[
            AplicacionARemito(remito_octubre, Decimal("800")),
            AplicacionARemito(remito_septiembre, Decimal("2000")),
        ],
    )

    assert total_remitos_cobrados_del_mes(conexion, "2024-10") == Decimal("800")


def test_deuda_de_lo_vendido_del_mes_es_venta_del_mes_menos_lo_ya_cobrado_de_esos_remitos(
    conexion, rto_id, formas_pago
):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"), con_iva_default=False
    )
    sucursal_id = _nueva_sucursal(conexion, cliente_id)
    remito_octubre = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-10-10", cliente_id, sucursal_id, Decimal("1000")
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-10-12", cliente_id, sucursal_id, Decimal("2000")
    )  # sin cobrar
    asentar_cobranza(
        conexion, cliente_id, "2024-10-15",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("800"))],
        aplicaciones=[AplicacionARemito(remito_octubre, Decimal("800"))],
    )

    # Venta de octubre: 1000 + 2000 = 3000; cobrado de esos remitos: 800.
    assert deuda_de_lo_vendido_del_mes(conexion, "2024-10") == Decimal("2200")


def test_porcentaje_deuda_mayor_a_30_dias():
    antiguedad = {
        "0-30": Decimal("250"), "31-60": Decimal("750"), "61-90": Decimal("0"), "91+": Decimal("0"),
    }
    assert porcentaje_deuda_mayor_a_30_dias(antiguedad) == Decimal("75")


def test_porcentaje_deuda_mayor_a_30_dias_sin_deuda_no_calcula_un_porcentaje_enganoso():
    antiguedad = {
        "0-30": Decimal("0"), "31-60": Decimal("0"), "61-90": Decimal("0"), "91+": Decimal("0"),
    }
    assert porcentaje_deuda_mayor_a_30_dias(antiguedad) is None


def test_estado_de_caja_del_dia(conexion, formas_pago):
    assert estado_de_caja_del_dia(conexion, "2024-03-20")["cierre_id"] is None

    cierre_id = abrir_caja(conexion, "2024-03-20")
    estado_abierta = estado_de_caja_del_dia(conexion, "2024-03-20")
    assert estado_abierta["abierta"] is True
    assert estado_abierta["cierre_id"] == cierre_id

    cerrar_caja(conexion, cierre_id, arqueos={formas_pago["Efectivo"]: Decimal("0")})
    estado_cerrada = estado_de_caja_del_dia(conexion, "2024-03-20")
    assert estado_cerrada["cerrada"] is True
