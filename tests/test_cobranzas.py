"""Etapa 4: cobranzas, recibos y cheques."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data import caja as datos_caja
from ios.data import cheques as datos_cheques
from ios.data import comprobantes as datos_comprobantes
from ios.data import recibos as datos_recibos
from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services.caja import abrir_caja, cerrar_caja
from ios.services.cobranzas import (
    AplicacionARemito,
    DatosCheque,
    Pago,
    anular_recibo,
    aplicar_saldo_a_favor,
    asentar_cobranza,
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
def del_pilar(conexion, rto_id):
    """Cliente Del Pilar con cinco remitos de 1000 cada uno."""
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Del Pilar")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]

    comprobante_ids = [
        servicio_comprobantes.alta_comprobante(
            conexion, rto_id, str(45200 + i), "2024-03-10", cliente_id, sucursal_id,
            Decimal("1000"), descuento_pct=Decimal("0"), con_iva=False,
        )
        for i in range(5)
    ]
    return cliente_id, comprobante_ids


def test_recibo_70011_cubre_cinco_remitos_y_deja_saldos_en_cero(conexion, formas_pago, del_pilar):
    cliente_id, comprobante_ids = del_pilar

    recibo_id = asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-20",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("5000"))],
        aplicaciones=[AplicacionARemito(cid, Decimal("1000")) for cid in comprobante_ids],
    )

    assert recibo_id is not None
    for comprobante_id in comprobante_ids:
        comprobante = datos_comprobantes.obtener_comprobante(conexion, comprobante_id)
        aplicado = datos_recibos.total_aplicado_a_comprobante(conexion, comprobante_id)
        assert comprobante["monto_final"] - aplicado == Decimal("0")


def test_recibo_con_efectivo_y_dos_cheques_genera_tres_movimientos_y_dos_cheques(
    conexion, formas_pago, del_pilar
):
    cliente_id, comprobante_ids = del_pilar

    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-20",
        pagos=[
            Pago(formas_pago["Efectivo"], Decimal("1000")),
            Pago(
                formas_pago["Cheque"],
                Decimal("1500"),
                cheque=DatosCheque("001", "Banco Nación", "2024-04-01"),
            ),
            Pago(
                formas_pago["Cheque"],
                Decimal("1500"),
                cheque=DatosCheque("002", "Banco Galicia", "2024-04-05"),
            ),
        ],
        aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("1000"))],
    )

    movimientos = datos_caja.listar_movimientos_por_concepto(conexion, "Recibo 1", "recibo")
    assert len(movimientos) == 3

    cheques_en_cartera = datos_cheques.listar_cheques_en_cartera(conexion)
    assert len(cheques_en_cartera) == 2
    assert {c["numero"] for c in cheques_en_cartera} == {"001", "002"}


def test_pago_parcial_deja_saldo_en_el_remito(conexion, formas_pago, del_pilar):
    cliente_id, comprobante_ids = del_pilar

    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-20",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("400"))],
        aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("400"))],
    )

    comprobante = datos_comprobantes.obtener_comprobante(conexion, comprobante_ids[0])
    aplicado = datos_recibos.total_aplicado_a_comprobante(conexion, comprobante_ids[0])
    assert comprobante["monto_final"] - aplicado == Decimal("600")


def test_pago_mayor_al_saldo_deja_excedente_como_saldo_a_favor(conexion, formas_pago, del_pilar):
    cliente_id, comprobante_ids = del_pilar

    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-20",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1500"))],
        aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("1000"))],
    )

    recibo = datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente_id)[0]
    disponible = recibo["monto_total"] - datos_recibos.total_aplicado_de_recibo(
        conexion, recibo["id"]
    )
    assert disponible == Decimal("500")


def test_aplicar_saldo_a_favor_a_remito_nuevo_no_genera_movimiento_de_caja(
    conexion, formas_pago, del_pilar
):
    cliente_id, comprobante_ids = del_pilar

    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-20",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1500"))],
        aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("1000"))],
    )
    movimientos_antes = len(
        datos_caja.listar_movimientos_por_concepto(conexion, "Recibo 1", "recibo")
    )

    aplicar_saldo_a_favor(
        conexion, cliente_id, [AplicacionARemito(comprobante_ids[1], Decimal("500"))]
    )

    aplicado = datos_recibos.total_aplicado_a_comprobante(conexion, comprobante_ids[1])
    assert aplicado == Decimal("500")
    movimientos_despues = len(
        datos_caja.listar_movimientos_por_concepto(conexion, "Recibo 1", "recibo")
    )
    assert movimientos_despues == movimientos_antes


def test_aplicar_mas_saldo_a_favor_del_disponible_falla(conexion, formas_pago, del_pilar):
    cliente_id, comprobante_ids = del_pilar

    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-20",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1500"))],
        aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("1000"))],
    )

    with pytest.raises(ValueError):
        aplicar_saldo_a_favor(
            conexion, cliente_id, [AplicacionARemito(comprobante_ids[1], Decimal("501"))]
        )


def test_recibo_anulado_libera_saldos_anula_cheques_y_genera_contramovimiento(
    conexion, formas_pago, del_pilar
):
    cliente_id, comprobante_ids = del_pilar

    recibo_id = asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-20",
        pagos=[
            Pago(formas_pago["Efectivo"], Decimal("500")),
            Pago(
                formas_pago["Cheque"],
                Decimal("500"),
                cheque=DatosCheque("010", "Banco Nación", "2024-04-10"),
            ),
        ],
        aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("1000"))],
    )
    cheque_id = datos_cheques.listar_cheques_de_recibo_origen(conexion, recibo_id)[0]["id"]

    anular_recibo(conexion, recibo_id, fecha_anulacion="2024-03-21")

    comprobante = datos_comprobantes.obtener_comprobante(conexion, comprobante_ids[0])
    aplicado = datos_recibos.total_aplicado_a_comprobante(conexion, comprobante_ids[0])
    assert comprobante["monto_final"] - aplicado == comprobante["monto_final"]  # saldo liberado

    cheque = datos_cheques.obtener_cheque(conexion, cheque_id)
    assert cheque["estado"] == "anulado"

    recibo = datos_recibos.obtener_recibo(conexion, recibo_id)
    assert recibo["estado"] == "anulado"

    contramovimientos = conexion.execute(
        "SELECT * FROM movimientos_caja WHERE origen = 'anulacion'"
    ).fetchall()
    assert len(contramovimientos) == 2
    assert all(c["tipo"] == "egreso" for c in contramovimientos)
    assert sum((c["monto"] for c in contramovimientos), Decimal(0)) == Decimal("1000")


def test_no_se_puede_anular_dos_veces(conexion, formas_pago, del_pilar):
    cliente_id, comprobante_ids = del_pilar
    recibo_id = asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-20",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1000"))],
        aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("1000"))],
    )
    anular_recibo(conexion, recibo_id, "2024-03-21")

    with pytest.raises(ValueError):
        anular_recibo(conexion, recibo_id, "2024-03-22")


def test_recibo_en_efectivo_suma_a_la_caja_del_dia(conexion, formas_pago, del_pilar):
    cliente_id, comprobante_ids = del_pilar

    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-20",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1000"))],
        aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("1000"))],
    )

    ingresos = conexion.execute(
        """
        SELECT SUM(monto) AS total FROM movimientos_caja
        WHERE tipo = 'ingreso' AND forma_pago_id = ?
        """,
        (formas_pago["Efectivo"],),
    ).fetchone()["total"]
    assert ingresos == Decimal("1000")


def test_recibo_importado_no_genera_movimiento_de_caja(conexion, formas_pago, del_pilar):
    cliente_id, comprobante_ids = del_pilar

    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-20",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1000"))],
        aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("1000"))],
        origen="importado",
    )

    movimientos = conexion.execute("SELECT * FROM movimientos_caja").fetchall()
    assert movimientos == []


def test_numero_de_recibo_correlativo_salta_el_ya_usado(conexion, formas_pago, del_pilar):
    cliente_id, comprobante_ids = del_pilar

    # Simula un recibo importado con número 70011 ya tomado.
    conexion.execute(
        "INSERT INTO recibos (numero, fecha, cliente_id, monto_total, origen, estado) "
        "VALUES (70011, '2024-03-01', ?, '1', 'importado', 'vigente')",
        (cliente_id,),
    )
    conexion.execute(
        "UPDATE configuracion SET numero_inicial_recibo = 70001 WHERE id = 1"
    )
    conexion.commit()

    recibo_id = asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-20",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1000"))],
        aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("1000"))],
    )

    recibo = datos_recibos.obtener_recibo(conexion, recibo_id)
    assert recibo["numero"] == 70012


def test_no_se_puede_aplicar_mas_que_el_saldo_pendiente_del_remito(
    conexion, formas_pago, del_pilar
):
    cliente_id, comprobante_ids = del_pilar

    with pytest.raises(ValueError):
        asentar_cobranza(
            conexion,
            cliente_id,
            "2024-03-20",
            pagos=[Pago(formas_pago["Efectivo"], Decimal("2000"))],
            aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("1500"))],
        )


def test_no_se_puede_aplicar_un_recibo_a_un_remito_de_otro_cliente(
    conexion, formas_pago, rto_id, del_pilar
):
    cliente_id, comprobante_ids = del_pilar
    otro_cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Mirage")
    otra_sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (otro_cliente_id,)
    ).fetchone()["id"]
    comprobante_de_otro = servicio_comprobantes.alta_comprobante(
        conexion, rto_id, "99999", "2024-03-10", otro_cliente_id, otra_sucursal_id,
        Decimal("1000"), descuento_pct=Decimal("0"), con_iva=False,
    )

    with pytest.raises(ValueError):
        asentar_cobranza(
            conexion,
            cliente_id,
            "2024-03-20",
            pagos=[Pago(formas_pago["Efectivo"], Decimal("1000"))],
            aplicaciones=[AplicacionARemito(comprobante_de_otro, Decimal("1000"))],
        )


def test_cobro_con_fecha_de_caja_ya_cerrada_se_registra_en_la_caja_de_hoy(
    conexion, formas_pago, del_pilar
):
    """Si te olvidaste de cargar un pago y la caja de esa fecha ya se
    cerró, el recibo mantiene la fecha real del pago (para la cuenta
    corriente) pero el movimiento de caja pasa a la de hoy, con una nota
    para quien hace el cierre."""
    cliente_id, comprobante_ids = del_pilar

    cierre_id = abrir_caja(conexion, "2024-03-20")
    cerrar_caja(conexion, cierre_id, arqueos={})

    recibo_id = asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-20",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1000"))],
        aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("1000"))],
        fecha_hoy="2024-03-22",
    )

    recibo = datos_recibos.obtener_recibo(conexion, recibo_id)
    assert recibo["fecha"] == "2024-03-20"  # la cuenta corriente ve la fecha real del pago

    movimiento = datos_caja.listar_movimientos_por_concepto(conexion, "Recibo 1", "recibo")[0]
    assert movimiento["fecha_hora"] == "2024-03-22"
    assert movimiento["nota"] is not None and "2024-03-20" in movimiento["nota"]


def test_cobro_con_fecha_de_caja_abierta_no_se_redirige(conexion, formas_pago, del_pilar):
    """Si la caja de la fecha del recibo todavía está abierta (no cerrada),
    el pago se registra normalmente en esa fecha, sin aclaración."""
    cliente_id, comprobante_ids = del_pilar
    abrir_caja(conexion, "2024-03-20")

    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-20",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1000"))],
        aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("1000"))],
        fecha_hoy="2024-03-22",
    )

    movimiento = datos_caja.listar_movimientos_por_concepto(conexion, "Recibo 1", "recibo")[0]
    assert movimiento["fecha_hora"] == "2024-03-20"
    assert movimiento["nota"] is None


def test_cobro_sin_fecha_hoy_mantiene_el_comportamiento_anterior(conexion, formas_pago, del_pilar):
    """Si no se informa fecha_hoy (compatibilidad con llamadas existentes),
    el movimiento se sigue registrando con la fecha del recibo, aunque esa
    caja ya esté cerrada."""
    cliente_id, comprobante_ids = del_pilar
    cierre_id = abrir_caja(conexion, "2024-03-20")
    cerrar_caja(conexion, cierre_id, arqueos={})

    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-20",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("1000"))],
        aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("1000"))],
    )

    movimiento = datos_caja.listar_movimientos_por_concepto(conexion, "Recibo 1", "recibo")[0]
    assert movimiento["fecha_hora"] == "2024-03-20"
    assert movimiento["nota"] is None


def test_no_se_puede_registrar_un_recibo_con_fecha_posterior_a_hoy(conexion, formas_pago, del_pilar):
    cliente_id, comprobante_ids = del_pilar

    with pytest.raises(ValueError):
        asentar_cobranza(
            conexion,
            cliente_id,
            "2024-03-25",
            pagos=[Pago(formas_pago["Efectivo"], Decimal("1000"))],
            aplicaciones=[AplicacionARemito(comprobante_ids[0], Decimal("1000"))],
            fecha_hoy="2024-03-20",
        )
