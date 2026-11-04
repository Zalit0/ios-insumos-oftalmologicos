"""Etapa 5: cuenta corriente, agrupada por sucursal, con total consolidado."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services.cobranzas import AplicacionARemito, Pago, anular_recibo, asentar_cobranza
from ios.services.comprobantes import anular_comprobante
from ios.services.cuenta_corriente import (
    desglose_pagos_del_periodo,
    estado_de_cuenta_cliente,
    estado_de_cuenta_periodo,
    estado_de_cuenta_solo_pendientes,
    historial_de_movimientos,
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


@pytest.fixture
def croma(conexion):
    cliente_id = servicio_clientes.alta_cliente(
        conexion,
        nombre="Croma",
        descuento_default=Decimal("25"),
        con_iva_default=False,
        sucursales=["Croma", "Croma Fdez."],
    )
    sucursales = conexion.execute(
        "SELECT id, nombre FROM sucursales WHERE cliente_id = ? ORDER BY id", (cliente_id,)
    ).fetchall()
    return cliente_id, {s["nombre"]: s["id"] for s in sucursales}


def test_estado_de_cuenta_muestra_ambas_sucursales_y_su_total(
    conexion, rto_id, formas_pago, croma
):
    cliente_id, sucursales = croma

    comprobante_croma = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )
    comprobante_fdez = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-03-06", cliente_id, sucursales["Croma Fdez."], Decimal("2000")
    )

    estado = estado_de_cuenta_cliente(conexion, cliente_id)

    nombres_sucursales = {s.nombre for s in estado.sucursales}
    assert nombres_sucursales == {"Croma", "Croma Fdez."}

    saldo_croma = next(s for s in estado.sucursales if s.nombre == "Croma").saldo
    saldo_fdez = next(s for s in estado.sucursales if s.nombre == "Croma Fdez.").saldo
    assert saldo_croma == Decimal("750")  # 1000 con 25% de descuento
    assert saldo_fdez == Decimal("1500")  # 2000 con 25% de descuento

    assert estado.saldo_comprobantes == Decimal("2250")
    assert estado.saldo_a_favor == Decimal("0")
    assert estado.saldo_consolidado == Decimal("2250")


def test_pago_reduce_el_saldo_de_la_sucursal_correspondiente(
    conexion, rto_id, formas_pago, croma
):
    cliente_id, sucursales = croma
    comprobante_croma = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )

    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("750"))],
        aplicaciones=[AplicacionARemito(comprobante_croma, Decimal("750"))],
    )

    estado = estado_de_cuenta_cliente(conexion, cliente_id)
    saldo_croma = next(s for s in estado.sucursales if s.nombre == "Croma").saldo
    assert saldo_croma == Decimal("0")
    assert estado.saldo_consolidado == Decimal("0")


def test_saldo_a_favor_reduce_el_consolidado_sin_tocar_sucursales(
    conexion, rto_id, formas_pago, croma
):
    cliente_id, sucursales = croma
    comprobante_croma = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )

    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1000"))],  # 250 de más
        aplicaciones=[AplicacionARemito(comprobante_croma, Decimal("750"))],
    )

    estado = estado_de_cuenta_cliente(conexion, cliente_id)
    saldo_croma = next(s for s in estado.sucursales if s.nombre == "Croma").saldo
    assert saldo_croma == Decimal("0")
    assert estado.saldo_a_favor == Decimal("250")
    assert estado.saldo_consolidado == Decimal("-250")


def test_agregar_cliente_no_afecta_el_estado_de_cuenta_de_otro(conexion, rto_id, formas_pago, croma):
    cliente_id, sucursales = croma
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )

    servicio_clientes.alta_cliente(conexion, nombre="Mirage")

    estado = estado_de_cuenta_cliente(conexion, cliente_id)
    assert estado.saldo_comprobantes == Decimal("750")


# --- Cuenta corriente con filtro de fechas/mes: arrastre de saldo ---


def test_saldo_impago_de_un_mes_se_arrastra_como_saldo_anterior_del_siguiente(
    conexion, rto_id, formas_pago, croma
):
    cliente_id, sucursales = croma
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-02-20", cliente_id, sucursales["Croma"], Decimal("1000")
    )

    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-03-01", "2024-03-31")

    croma_periodo = next(s for s in estado.sucursales if s.nombre == "Croma")
    assert croma_periodo.saldo_anterior == Decimal("750")  # 1000 con 25% de descuento
    assert croma_periodo.movimientos == []
    assert croma_periodo.saldo_cierre == Decimal("750")
    assert estado.saldo_consolidado_anterior == Decimal("750")
    assert estado.saldo_consolidado_cierre == Decimal("750")


def test_remito_del_periodo_se_lista_y_entra_en_el_saldo_de_cierre(
    conexion, rto_id, formas_pago, croma
):
    cliente_id, sucursales = croma
    comprobante = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )

    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-03-01", "2024-03-31")

    croma_periodo = next(s for s in estado.sucursales if s.nombre == "Croma")
    assert croma_periodo.saldo_anterior == Decimal("0")
    assert len(croma_periodo.movimientos) == 1
    assert croma_periodo.movimientos[0].comprobante_id == comprobante
    assert croma_periodo.movimientos[0].monto_final == Decimal("750")
    assert croma_periodo.movimientos[0].saldo == Decimal("750")  # sin pagar: saldo = monto final
    assert croma_periodo.saldo_cierre == Decimal("750")
    assert croma_periodo.saldo_del_periodo == Decimal("750")  # saldo_cierre - saldo_anterior


def test_remito_del_periodo_pagado_en_el_mismo_periodo_muestra_saldo_cero_en_el_movimiento(
    conexion, rto_id, formas_pago, croma
):
    """Caso reportado: en la vista de período el remito pagado debe verse
    con saldo $0 en su propia fila, igual que en la vista total."""
    cliente_id, sucursales = croma
    comprobante = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )
    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("750"))],
        aplicaciones=[AplicacionARemito(comprobante, Decimal("750"))],
    )

    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-03-01", "2024-03-31")

    croma_periodo = next(s for s in estado.sucursales if s.nombre == "Croma")
    assert len(croma_periodo.movimientos) == 1
    assert croma_periodo.movimientos[0].monto_final == Decimal("750")
    assert croma_periodo.movimientos[0].saldo == Decimal("0")
    assert croma_periodo.saldo_cierre == Decimal("0")


def test_remito_fuera_del_periodo_no_aparece_en_movimientos_pero_ya_esta_en_el_saldo_anterior(
    conexion, rto_id, formas_pago, croma
):
    cliente_id, sucursales = croma
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-04-02", cliente_id, sucursales["Croma"], Decimal("1000")
    )

    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-03-01", "2024-03-31")

    croma_periodo = next(s for s in estado.sucursales if s.nombre == "Croma")
    assert croma_periodo.saldo_anterior == Decimal("0")
    assert croma_periodo.movimientos == []
    assert croma_periodo.saldo_cierre == Decimal("0")


def test_recibo_del_periodo_aparece_listado_y_reduce_el_saldo_al_cierre(
    conexion, rto_id, formas_pago, croma
):
    """El pago es de este período (marzo), pero el remito que cubre es de
    febrero: como el saldo siempre es "a hoy", ese remito ya pagado no
    figura ni en el saldo anterior ni en el de cierre."""
    cliente_id, sucursales = croma
    comprobante = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-02-20", cliente_id, sucursales["Croma"], Decimal("1000")
    )
    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("750"))],
        aplicaciones=[AplicacionARemito(comprobante, Decimal("750"))],
    )

    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-03-01", "2024-03-31")

    croma_periodo = next(s for s in estado.sucursales if s.nombre == "Croma")
    assert croma_periodo.saldo_anterior == Decimal("0")
    assert croma_periodo.saldo_cierre == Decimal("0")
    assert len(estado.recibos_del_periodo) == 1
    assert estado.recibos_del_periodo[0].monto_total == Decimal("750")
    assert estado.saldo_consolidado_anterior == Decimal("0")
    assert estado.saldo_consolidado_cierre == Decimal("0")


def test_remito_viejo_pagado_en_un_mes_posterior_no_figura_como_saldo_al_consultar_su_propio_mes(
    conexion, rto_id, formas_pago, croma
):
    """Caso reportado: un remito de febrero se cobra recién en abril. Al
    consultar la cuenta de febrero (su propio mes) hoy, ya no debe figurar
    como saldo pendiente — el saldo siempre es el de hoy, no una foto fija
    de cómo estaba la cuenta en marzo."""
    cliente_id, sucursales = croma
    comprobante = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-02-20", cliente_id, sucursales["Croma"], Decimal("1000")
    )
    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-04-05",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("750"))],
        aplicaciones=[AplicacionARemito(comprobante, Decimal("750"))],
    )

    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-02-01", "2024-02-29")

    croma_periodo = next(s for s in estado.sucursales if s.nombre == "Croma")
    assert croma_periodo.saldo_anterior == Decimal("0")
    assert len(croma_periodo.movimientos) == 1
    assert croma_periodo.movimientos[0].saldo == Decimal("0")
    assert croma_periodo.saldo_cierre == Decimal("0")
    assert estado.saldo_consolidado_cierre == Decimal("0")


def test_remito_viejo_pagado_mas_tarde_tampoco_figura_al_consultar_un_mes_intermedio(
    conexion, rto_id, formas_pago, croma
):
    """Mismo caso, pero consultando un mes intermedio (marzo) en el que no
    pasó nada: tampoco debe figurar, porque a hoy ya está cobrado."""
    cliente_id, sucursales = croma
    comprobante = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-02-20", cliente_id, sucursales["Croma"], Decimal("1000")
    )
    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-04-05",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("750"))],
        aplicaciones=[AplicacionARemito(comprobante, Decimal("750"))],
    )

    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-03-01", "2024-03-31")

    croma_periodo = next(s for s in estado.sucursales if s.nombre == "Croma")
    assert croma_periodo.saldo_anterior == Decimal("0")
    assert croma_periodo.movimientos == []
    assert croma_periodo.saldo_cierre == Decimal("0")


def test_recibo_anterior_al_periodo_ya_esta_en_el_saldo_anterior_y_no_se_lista(
    conexion, rto_id, formas_pago, croma
):
    cliente_id, sucursales = croma
    comprobante = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-02-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )
    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-02-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("750"))],
        aplicaciones=[AplicacionARemito(comprobante, Decimal("750"))],
    )

    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-03-01", "2024-03-31")

    croma_periodo = next(s for s in estado.sucursales if s.nombre == "Croma")
    assert croma_periodo.saldo_anterior == Decimal("0")
    assert croma_periodo.saldo_cierre == Decimal("0")
    assert estado.recibos_del_periodo == []


def test_arrastre_de_saldo_a_favor_positivo_a_favor_del_cliente(
    conexion, rto_id, formas_pago, croma
):
    cliente_id, sucursales = croma
    comprobante = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-02-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )
    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-02-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1000"))],  # 250 de más
        aplicaciones=[AplicacionARemito(comprobante, Decimal("750"))],
    )

    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-03-01", "2024-03-31")

    assert estado.saldo_a_favor_anterior == Decimal("250")
    assert estado.saldo_a_favor_cierre == Decimal("250")
    assert estado.saldo_consolidado_anterior == Decimal("-250")
    assert estado.saldo_consolidado_cierre == Decimal("-250")


def test_saldo_del_periodo_no_incluye_la_deuda_arrastrada(conexion, rto_id, formas_pago, croma):
    """"Saldo del período" tiene que mostrar solo lo que generó ese mes
    (lo facturado menos lo cobrado de esos remitos), sin mezclar la deuda
    arrastrada de meses anteriores — a diferencia de "Saldo al cierre",
    que sí es el total acumulado."""
    cliente_id, sucursales = croma
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-02-20", cliente_id, sucursales["Croma"], Decimal("1000")
    )  # deuda vieja sin cobrar: $750
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-03-05", cliente_id, sucursales["Croma"], Decimal("2000")
    )  # remito del período: $1500

    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-03-01", "2024-03-31")

    croma_periodo = next(s for s in estado.sucursales if s.nombre == "Croma")
    assert croma_periodo.saldo_anterior == Decimal("750")
    assert croma_periodo.saldo_del_periodo == Decimal("1500")  # solo el remito de marzo
    assert croma_periodo.saldo_cierre == Decimal("2250")  # 750 + 1500
    assert estado.saldo_consolidado_del_periodo == Decimal("1500")


# --- Rediseño del estado de cuenta: campo "aplicado", modo "pendientes",
# desglose de pagos del período, historial combinado de movimientos
# (docs/AJUSTES_V1.1.md, rediseño del estado de cuenta corriente) ---


def test_saldo_comprobante_y_movimiento_remito_informan_lo_aplicado(
    conexion, rto_id, formas_pago, croma
):
    cliente_id, sucursales = croma
    comprobante = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )  # con 25% de descuento: monto final 750
    asentar_cobranza(
        conexion, cliente_id, "2024-03-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("300"))],
        aplicaciones=[AplicacionARemito(comprobante, Decimal("300"))],
    )

    estado_total = estado_de_cuenta_cliente(conexion, cliente_id)
    saldo_comprobante = next(s for s in estado_total.sucursales if s.nombre == "Croma").comprobantes[0]
    assert saldo_comprobante.aplicado == Decimal("300")
    assert saldo_comprobante.saldo == Decimal("450")

    estado_periodo = estado_de_cuenta_periodo(conexion, cliente_id, "2024-03-01", "2024-03-31")
    movimiento = next(s for s in estado_periodo.sucursales if s.nombre == "Croma").movimientos[0]
    assert movimiento.aplicado == Decimal("300")
    assert movimiento.saldo == Decimal("450")


def test_estado_de_cuenta_solo_pendientes_excluye_los_comprobantes_cancelados(
    conexion, rto_id, formas_pago, croma
):
    cliente_id, sucursales = croma
    pendiente = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-03-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )
    cancelado = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-03-06", cliente_id, sucursales["Croma"], Decimal("2000")
    )
    asentar_cobranza(
        conexion, cliente_id, "2024-03-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1500"))],
        aplicaciones=[AplicacionARemito(cancelado, Decimal("1500"))],
    )

    estado = estado_de_cuenta_solo_pendientes(conexion, cliente_id)

    croma_pendientes = next(s for s in estado.sucursales if s.nombre == "Croma")
    assert [c.comprobante_id for c in croma_pendientes.comprobantes] == [pendiente]
    assert croma_pendientes.saldo == Decimal("750")  # el saldo de la sucursal no cambia, sigue siendo el real
    assert estado.saldo_consolidado == Decimal("750")


def test_desglose_pagos_comprobante_de_septiembre_cancelado_en_octubre(
    conexion, rto_id, formas_pago, croma
):
    """Escenario pedido: comprobante de septiembre, cancelado por un
    recibo de octubre. No debe asumirse que el pago es "del período" de
    octubre solo porque el recibo tiene esa fecha."""
    cliente_id, sucursales = croma
    comprobante = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-09-15", cliente_id, sucursales["Croma"], Decimal("1000")
    )
    asentar_cobranza(
        conexion, cliente_id, "2024-10-05",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("750"))],
        aplicaciones=[AplicacionARemito(comprobante, Decimal("750"))],
    )

    desglose = desglose_pagos_del_periodo(conexion, cliente_id, "2024-10-01", "2024-10-31")

    assert desglose.total_recibido == Decimal("750")
    assert desglose.aplicado_a_comprobantes_del_periodo == Decimal("0")
    assert desglose.aplicado_a_comprobantes_de_otros_periodos == Decimal("750")
    assert desglose.aplicado_a_comprobantes_anulados == Decimal("0")
    assert desglose.sin_aplicar == Decimal("0")


def test_desglose_pagos_comprobante_de_octubre_pendiente_no_cuenta_como_aplicado(
    conexion, rto_id, formas_pago, croma
):
    """Escenario pedido: comprobante de octubre todavía pendiente (sin
    ningún recibo que lo cubra) — no debe figurar en el desglose de
    pagos, pero sí en el total facturado del período."""
    cliente_id, sucursales = croma
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-10-10", cliente_id, sucursales["Croma"], Decimal("1000")
    )

    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-10-01", "2024-10-31")

    assert estado.total_comprobantes_emitidos == Decimal("750")
    assert estado.desglose_pagos.total_recibido == Decimal("0")
    assert estado.desglose_pagos.aplicado_a_comprobantes_del_periodo == Decimal("0")


def test_desglose_pagos_parciales(conexion, rto_id, formas_pago, croma):
    """Escenario pedido: pago parcial de un comprobante del período."""
    cliente_id, sucursales = croma
    comprobante = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-10-05", cliente_id, sucursales["Croma"], Decimal("2000")
    )  # monto final 1500
    asentar_cobranza(
        conexion, cliente_id, "2024-10-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("600"))],
        aplicaciones=[AplicacionARemito(comprobante, Decimal("600"))],
    )

    desglose = desglose_pagos_del_periodo(conexion, cliente_id, "2024-10-01", "2024-10-31")
    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-10-01", "2024-10-31")

    assert desglose.aplicado_a_comprobantes_del_periodo == Decimal("600")
    movimiento = next(s for s in estado.sucursales if s.nombre == "Croma").movimientos[0]
    assert movimiento.aplicado == Decimal("600")
    assert movimiento.saldo == Decimal("900")  # 1500 - 600: queda pendiente


def test_desglose_pagos_que_cancela_varios_comprobantes(conexion, rto_id, formas_pago, croma):
    """Escenario pedido: un mismo recibo aplicado a varios comprobantes
    del período, sin duplicar ni perder montos en el desglose."""
    cliente_id, sucursales = croma
    comprobante_1 = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-10-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )  # 750
    comprobante_2 = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-10-06", cliente_id, sucursales["Croma"], Decimal("1000")
    )  # 750
    asentar_cobranza(
        conexion, cliente_id, "2024-10-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1500"))],
        aplicaciones=[
            AplicacionARemito(comprobante_1, Decimal("750")),
            AplicacionARemito(comprobante_2, Decimal("750")),
        ],
    )

    desglose = desglose_pagos_del_periodo(conexion, cliente_id, "2024-10-01", "2024-10-31")

    assert desglose.total_recibido == Decimal("1500")
    assert desglose.aplicado_a_comprobantes_del_periodo == Decimal("1500")
    assert desglose.sin_aplicar == Decimal("0")


def test_desglose_pagos_con_saldo_a_favor_queda_sin_aplicar(conexion, rto_id, formas_pago, croma):
    """Escenario pedido: comprobante con saldo a favor (recibo que no se
    aplica a ningún remito)."""
    cliente_id, sucursales = croma
    asentar_cobranza(
        conexion, cliente_id, "2024-10-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("500"))],
        aplicaciones=[],
    )

    desglose = desglose_pagos_del_periodo(conexion, cliente_id, "2024-10-01", "2024-10-31")

    assert desglose.total_recibido == Decimal("500")
    assert desglose.sin_aplicar == Decimal("500")
    assert desglose.aplicado_a_comprobantes_del_periodo == Decimal("0")
    assert desglose.aplicado_a_comprobantes_de_otros_periodos == Decimal("0")


def test_desglose_pagos_excluye_lo_aplicado_a_un_comprobante_anulado_despues(
    conexion, rto_id, formas_pago, croma
):
    """Escenario pedido: anulación de un comprobante después de haber
    sido cobrado. No se borra ni se modifica el recibo histórico: el
    desglose lo identifica aparte, sin contarlo como deuda viva."""
    cliente_id, sucursales = croma
    comprobante = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-10-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )
    asentar_cobranza(
        conexion, cliente_id, "2024-10-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("750"))],
        aplicaciones=[AplicacionARemito(comprobante, Decimal("750"))],
    )
    anular_comprobante(conexion, comprobante)

    desglose = desglose_pagos_del_periodo(conexion, cliente_id, "2024-10-01", "2024-10-31")

    assert desglose.total_recibido == Decimal("750")
    assert desglose.aplicado_a_comprobantes_anulados == Decimal("750")
    assert desglose.aplicado_a_comprobantes_del_periodo == Decimal("0")


def test_desglose_pagos_excluye_un_recibo_anulado_por_completo(
    conexion, rto_id, formas_pago, croma
):
    """Escenario pedido: anulación de un recibo. Un recibo anulado no
    cuenta como "recibido" en el desglose del período (igual que ya no
    cuenta en el resto de la cuenta corriente)."""
    cliente_id, sucursales = croma
    comprobante = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-10-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )
    recibo_id = asentar_cobranza(
        conexion, cliente_id, "2024-10-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("750"))],
        aplicaciones=[AplicacionARemito(comprobante, Decimal("750"))],
    )
    anular_recibo(conexion, recibo_id, "2024-10-11")

    desglose = desglose_pagos_del_periodo(conexion, cliente_id, "2024-10-01", "2024-10-31")

    assert desglose.total_recibido == Decimal("0")


def test_recibo_del_periodo_informa_a_que_remitos_aplico(conexion, rto_id, formas_pago, croma):
    """Pedido explícito: en el modo "completo del período", cada recibo
    tiene que mostrar qué remitos cancela, no solo el monto."""
    cliente_id, sucursales = croma
    remito_viejo = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-02-20", cliente_id, sucursales["Croma"], Decimal("1000")
    )  # 750, de febrero
    remito_nuevo = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-03-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )  # 750, de marzo
    asentar_cobranza(
        conexion, cliente_id, "2024-03-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("900"))],
        aplicaciones=[
            AplicacionARemito(remito_viejo, Decimal("750")),
            AplicacionARemito(remito_nuevo, Decimal("150")),
        ],
    )

    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-03-01", "2024-03-31")

    recibo = estado.recibos_del_periodo[0]
    aplicaciones_por_numero = {a.comprobante_numero: a.monto for a in recibo.aplicaciones}
    assert aplicaciones_por_numero == {"1": Decimal("750"), "2": Decimal("150")}
    assert recibo.sin_aplicar == Decimal("0")

    # Cada aplicación informa la fecha de emisión del remito que cancela,
    # para distinguir un pago de deuda vieja de uno del propio período.
    fechas_por_numero = {a.comprobante_numero: a.comprobante_fecha for a in recibo.aplicaciones}
    assert fechas_por_numero == {"1": "2024-02-20", "2": "2024-03-05"}


def test_recibo_del_periodo_sin_aplicar_queda_marcado_como_saldo_a_favor(
    conexion, rto_id, formas_pago, croma
):
    cliente_id, sucursales = croma
    asentar_cobranza(
        conexion, cliente_id, "2024-03-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("300"))],
        aplicaciones=[],
    )

    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-03-01", "2024-03-31")

    recibo = estado.recibos_del_periodo[0]
    assert recibo.aplicaciones == []
    assert recibo.sin_aplicar == Decimal("300")


def test_historial_de_movimientos_mezcla_remitos_y_recibos_con_su_aplicacion(
    conexion, rto_id, formas_pago, croma
):
    cliente_id, sucursales = croma
    remito_viejo = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-09-15", cliente_id, sucursales["Croma"], Decimal("1000")
    )  # 750, de septiembre
    remito_nuevo = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-10-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )  # 750, de octubre
    # Un recibo de octubre paga el remito viejo (septiembre) y parte del nuevo.
    asentar_cobranza(
        conexion, cliente_id, "2024-10-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("950"))],
        aplicaciones=[
            AplicacionARemito(remito_viejo, Decimal("750")),
            AplicacionARemito(remito_nuevo, Decimal("200")),
        ],
    )

    historial = historial_de_movimientos(conexion, cliente_id, "2024-10-01", "2024-10-31")

    # Solo entra el remito de octubre (el de septiembre quedó fuera del rango de fechas).
    tipos_numeros = [(m.tipo, m.numero) for m in historial.movimientos]
    assert tipos_numeros == [("remito", "2"), ("recibo", "1")]

    movimiento_remito = historial.movimientos[0]
    assert movimiento_remito.saldo == Decimal("550")  # 750 - 200

    movimiento_recibo = historial.movimientos[1]
    aplicaciones_por_numero = {a.comprobante_numero: a.monto for a in movimiento_recibo.aplicaciones}
    assert aplicaciones_por_numero == {"1": Decimal("750"), "2": Decimal("200")}
    assert movimiento_recibo.sin_aplicar == Decimal("0")

    # El saldo final del historial tiene que coincidir con la cuenta corriente real.
    estado_real = estado_de_cuenta_cliente(conexion, cliente_id)
    assert historial.saldo_consolidado_cierre == estado_real.saldo_consolidado


def test_historial_de_movimientos_recibo_sin_aplicar_queda_como_saldo_a_favor(
    conexion, rto_id, formas_pago, croma
):
    cliente_id, sucursales = croma
    asentar_cobranza(
        conexion, cliente_id, "2024-10-10",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("400"))],
        aplicaciones=[],
    )

    historial = historial_de_movimientos(conexion, cliente_id, "2024-10-01", "2024-10-31")

    assert len(historial.movimientos) == 1
    movimiento = historial.movimientos[0]
    assert movimiento.tipo == "recibo"
    assert movimiento.aplicaciones == []
    assert movimiento.sin_aplicar == Decimal("400")
    assert historial.saldo_a_favor_cierre == Decimal("400")


def test_arrastre_de_saldo_es_independiente_por_sucursal(conexion, rto_id, formas_pago, croma):
    cliente_id, sucursales = croma
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "1", "2024-02-05", cliente_id, sucursales["Croma"], Decimal("1000")
    )
    servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "2", "2024-02-06", cliente_id, sucursales["Croma Fdez."], Decimal("2000")
    )

    estado = estado_de_cuenta_periodo(conexion, cliente_id, "2024-03-01", "2024-03-31")

    saldo_croma = next(s for s in estado.sucursales if s.nombre == "Croma").saldo_anterior
    saldo_fdez = next(s for s in estado.sucursales if s.nombre == "Croma Fdez.").saldo_anterior
    assert saldo_croma == Decimal("750")
    assert saldo_fdez == Decimal("1500")
    assert estado.saldo_consolidado_anterior == Decimal("2250")
