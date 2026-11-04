"""Casos de cálculo de docs/PLAN.md, sección "Pruebas y validaciones"
que corresponden a la etapa 1 (dominio puro, sin servicios ni base)."""

from decimal import Decimal

from ios.domain.calculos import (
    calcular_iva_discriminado,
    calcular_monto_final,
    calcular_saldo_a_favor,
    calcular_saldo_cliente,
    calcular_saldo_comprobante,
    calcular_totales_mes,
    cuantizar,
)

DECIMALES = 2
TASA_IVA = Decimal("21")


def test_remito_con_descuento_20_e_iva_si():
    final = calcular_monto_final(Decimal("4416.40"), Decimal("20"), DECIMALES)
    iva = calcular_iva_discriminado(final, True, TASA_IVA, DECIMALES)

    assert final == Decimal("3533.12")
    assert iva == Decimal("613.19")


def test_remito_con_descuento_25_croma():
    final = calcular_monto_final(Decimal("104544"), Decimal("25"), DECIMALES)
    iva = calcular_iva_discriminado(final, True, TASA_IVA, DECIMALES)

    assert final == Decimal("78408")
    assert iva == Decimal("13608")


def test_remito_con_iva_no():
    final = calcular_monto_final(Decimal("4416.40"), Decimal("20"), DECIMALES)
    iva = calcular_iva_discriminado(final, False, TASA_IVA, DECIMALES)

    assert iva == Decimal("0.00")
    assert final == Decimal("3533.12")  # el final no cambia por el IVA


def test_cambiar_tasa_iva_solo_afecta_remitos_nuevos():
    final = Decimal("3533.12")

    iva_con_tasa_actual = calcular_iva_discriminado(final, True, Decimal("21"), DECIMALES)
    iva_con_tasa_nueva = calcular_iva_discriminado(final, True, Decimal("22"), DECIMALES)

    # El remito ya cargado guardó su iva_discriminado; cambiar la tasa de
    # configuración no lo recalcula, solo afecta a los remitos que se
    # calculen de ahora en más (acá, simplemente, otro llamado a la función).
    iva_del_remito_ya_cargado = iva_con_tasa_actual
    assert iva_del_remito_ya_cargado == Decimal("613.19")
    assert iva_con_tasa_nueva != iva_del_remito_ya_cargado


def test_redondeo_configurable():
    valor = Decimal("1654.786115")

    assert cuantizar(valor, 2) == Decimal("1654.79")
    assert cuantizar(valor, 0) == Decimal("1655")


def test_saldo_comprobante():
    saldo = calcular_saldo_comprobante(Decimal("3533.12"), Decimal("1000"))
    assert saldo == Decimal("2533.12")


def test_saldo_a_favor_por_pago_en_exceso():
    saldo_a_favor = calcular_saldo_a_favor(Decimal("5000"), Decimal("3000"))
    assert saldo_a_favor == Decimal("2000")


def test_saldo_cliente_con_saldo_a_favor():
    saldos_comprobantes = [Decimal("1000"), Decimal("500")]
    saldo_a_favor = Decimal("2000")

    saldo_cliente = calcular_saldo_cliente(saldos_comprobantes, saldo_a_favor)

    # 1000 + 500 - 2000 = -500: negativo, el cliente tiene saldo a favor.
    assert saldo_cliente == Decimal("-500")


def test_totales_del_mes():
    totales = calcular_totales_mes(
        montos_finales_vigentes=[Decimal("2848734.135")],
        montos_aplicados_a_remitos_del_mes=[Decimal("1038852.72")],
        ivas_venta_vigentes=[Decimal("494535.09")],
        ivas_compra=[Decimal("10000")],
        montos_compras=[Decimal("50000")],
        montos_pagos_proveedor=[Decimal("30000")],
        comision_pct=Decimal("15"),
    )

    assert totales.total_venta == Decimal("2848734.135")
    assert totales.total_pagos == Decimal("1038852.72")
    assert totales.total_saldos == Decimal("1809881.415")
    assert totales.iva_deuda == Decimal("484535.09")
    assert totales.comision == totales.total_venta * Decimal("15") / Decimal(100)
    assert totales.depositos == Decimal("30000")
    assert totales.ganancia_teorica == (
        totales.total_venta - totales.comision - totales.total_compras - totales.iva_deuda
    )
