"""Etapa 7: caja diaria y cheques."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data import cheques as datos_cheques
from ios.data import cierres_caja as datos_cierres
from ios.data.db import conectar
from ios.services import categorias_caja as servicio_categorias
from ios.services import clientes as servicio_clientes
from ios.services import proveedores as servicio_proveedores
from ios.services.caja import (
    abrir_caja,
    ajustar_saldo_inicial,
    cerrar_caja,
    cerrar_cajas_vencidas,
    hay_caja_abierta_hoy,
    registrar_movimiento_manual,
    registrar_transferencia_interna,
    saldo_inicial_propuesto,
    total_disponible,
    vista_previa_cierre,
)
from ios.services.cheques import cobrar_cheque, rechazar_cheque
from ios.services.cobranzas import AplicacionARemito, DatosCheque, Pago, anular_recibo, asentar_cobranza
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
def croma(conexion) -> int:
    return servicio_clientes.alta_cliente(conexion, nombre="Croma")


@pytest.fixture
def lentex(conexion) -> int:
    return servicio_proveedores.alta_proveedor(conexion, nombre="Lentex")


def test_saldo_inicial_propuesto_es_cero_sin_cierres_previos(conexion, formas_pago):
    assert saldo_inicial_propuesto(conexion, formas_pago["Efectivo"]) == Decimal("0")


def test_no_se_puede_abrir_dos_veces_el_mismo_dia(conexion):
    abrir_caja(conexion, "2024-03-20")
    with pytest.raises(ValueError):
        abrir_caja(conexion, "2024-03-20")


def test_dia_con_cobros_mixtos_pago_gasto_y_deposito_cierra_con_diferencia_cero(
    conexion, formas_pago, croma, lentex
):
    """Caso de aceptación de la etapa."""
    efectivo = formas_pago["Efectivo"]
    transferencia = formas_pago["Transferencia"]
    cheque = formas_pago["Cheque"]
    fecha = "2024-03-20"

    cierre_id = abrir_caja(conexion, fecha)

    # Cobro mixto: efectivo + cheque.
    asentar_cobranza(
        conexion,
        croma,
        fecha,
        pagos=[
            Pago(efectivo, Decimal("1000")),
            Pago(cheque, Decimal("500"), cheque=DatosCheque("777", "Banco Nación", "2024-04-01")),
        ],
        aplicaciones=[],
    )

    # Un pago a proveedor (egreso en efectivo).
    registrar_pago_proveedor(conexion, lentex, fecha, Decimal("300"), efectivo)

    # Un gasto (egreso manual en efectivo).
    categoria_gastos = servicio_categorias.alta_categoria(conexion, "Gastos varios", "egreso")
    registrar_movimiento_manual(
        conexion, fecha, "egreso", efectivo, Decimal("50"), categoria_id=categoria_gastos
    )

    # Un depósito al banco: efectivo -> transferencia, no cambia el total disponible.
    registrar_transferencia_interna(
        conexion, fecha, efectivo, transferencia, Decimal("200"), "Depósito al banco"
    )

    # Efectivo: +1000 (cobro) -300 (proveedor) -50 (gasto) -200 (depósito) = 450
    # Transferencia: +200 (depósito) = 200
    # Cheque: +500 (cobro) = 500
    cerrar_caja(
        conexion,
        cierre_id,
        arqueos={efectivo: Decimal("450"), transferencia: Decimal("200"), cheque: Decimal("500")},
    )

    detalle = {
        d["forma_pago_id"]: d for d in datos_cierres.listar_detalle_de_cierre(conexion, cierre_id)
    }
    assert all(d["diferencia"] == Decimal("0") for d in detalle.values())
    assert detalle[efectivo]["saldo_teorico"] == Decimal("450")
    assert detalle[transferencia]["saldo_teorico"] == Decimal("200")
    assert detalle[cheque]["saldo_teorico"] == Decimal("500")


def test_vista_previa_cierre_coincide_con_el_cierre_real(conexion, formas_pago, croma):
    efectivo = formas_pago["Efectivo"]
    fecha = "2024-03-20"
    cierre_id = abrir_caja(conexion, fecha)
    asentar_cobranza(
        conexion, croma, fecha, pagos=[Pago(efectivo, Decimal("1000"))], aplicaciones=[]
    )
    registrar_movimiento_manual(conexion, fecha, "egreso", efectivo, Decimal("200"))

    vista_previa = vista_previa_cierre(conexion, fecha)
    assert len(vista_previa) == 1
    assert vista_previa[0].forma_pago_id == efectivo
    assert vista_previa[0].saldo_teorico == Decimal("800")

    cerrar_caja(conexion, cierre_id, arqueos={efectivo: Decimal("800")})
    detalle = datos_cierres.listar_detalle_de_cierre(conexion, cierre_id)[0]
    assert detalle["saldo_teorico"] == vista_previa[0].saldo_teorico


def test_cierre_con_diferencia_exige_nota(conexion, formas_pago, croma):
    efectivo = formas_pago["Efectivo"]
    fecha = "2024-03-20"
    cierre_id = abrir_caja(conexion, fecha)

    asentar_cobranza(
        conexion, croma, fecha, pagos=[Pago(efectivo, Decimal("1000"))], aplicaciones=[]
    )

    with pytest.raises(ValueError):
        cerrar_caja(conexion, cierre_id, arqueos={efectivo: Decimal("900")})

    # Con nota, cierra sin problema.
    cerrar_caja(
        conexion, cierre_id, arqueos={efectivo: Decimal("900")}, nota="Faltaron $100 en caja"
    )
    detalle = datos_cierres.listar_detalle_de_cierre(conexion, cierre_id)[0]
    assert detalle["diferencia"] == Decimal("-100")


def test_saldo_inicial_propone_el_arqueo_del_cierre_anterior(conexion, formas_pago, croma):
    efectivo = formas_pago["Efectivo"]

    cierre_1 = abrir_caja(conexion, "2024-03-20")
    asentar_cobranza(
        conexion, croma, "2024-03-20", pagos=[Pago(efectivo, Decimal("1000"))], aplicaciones=[]
    )
    cerrar_caja(conexion, cierre_1, arqueos={efectivo: Decimal("1000")})

    assert saldo_inicial_propuesto(conexion, efectivo) == Decimal("1000")

    cierre_2 = abrir_caja(conexion, "2024-03-21")
    cerrar_caja(conexion, cierre_2, arqueos={efectivo: Decimal("1000")})
    detalle = datos_cierres.listar_detalle_de_cierre(conexion, cierre_2)[0]
    assert detalle["saldo_inicial"] == Decimal("1000")
    assert detalle["diferencia"] == Decimal("0")


def test_modificar_saldo_inicial_sin_nota_falla(conexion, formas_pago):
    efectivo = formas_pago["Efectivo"]
    with pytest.raises(ValueError):
        ajustar_saldo_inicial(conexion, "2024-03-20 08:00", efectivo, Decimal("500"))


def test_modificar_saldo_inicial_genera_movimiento_de_ajuste_con_nota(
    conexion, formas_pago, croma
):
    efectivo = formas_pago["Efectivo"]
    fecha = "2024-03-20"
    cierre_id = abrir_caja(conexion, fecha)

    ajustar_saldo_inicial(
        conexion, f"{fecha} 08:00", efectivo, Decimal("500"), nota="Se contó mal el día anterior"
    )

    cerrar_caja(conexion, cierre_id, arqueos={efectivo: Decimal("500")})
    detalle = datos_cierres.listar_detalle_de_cierre(conexion, cierre_id)[0]
    assert detalle["diferencia"] == Decimal("0")


def test_un_deposito_de_efectivo_al_banco_no_cambia_el_total_disponible(
    conexion, formas_pago, croma
):
    efectivo = formas_pago["Efectivo"]
    transferencia = formas_pago["Transferencia"]
    fecha = "2024-03-20"

    asentar_cobranza(
        conexion, croma, fecha, pagos=[Pago(efectivo, Decimal("1000"))], aplicaciones=[]
    )
    antes = total_disponible(conexion, [efectivo, transferencia])

    registrar_transferencia_interna(conexion, fecha, efectivo, transferencia, Decimal("400"))

    despues = total_disponible(conexion, [efectivo, transferencia])
    assert despues == antes


def test_anular_recibo_de_un_dia_cerrado_no_modifica_el_cierre_anterior(
    conexion, formas_pago, croma
):
    efectivo = formas_pago["Efectivo"]

    cierre_1 = abrir_caja(conexion, "2024-03-20")
    recibo_id = asentar_cobranza(
        conexion, croma, "2024-03-20", pagos=[Pago(efectivo, Decimal("1000"))], aplicaciones=[]
    )
    cerrar_caja(conexion, cierre_1, arqueos={efectivo: Decimal("1000")})
    detalle_1_antes = dict(datos_cierres.listar_detalle_de_cierre(conexion, cierre_1)[0])

    cierre_2 = abrir_caja(conexion, "2024-03-21")
    anular_recibo(conexion, recibo_id, fecha_anulacion="2024-03-21")
    cerrar_caja(conexion, cierre_2, arqueos={efectivo: Decimal("0")})

    detalle_1_despues = dict(datos_cierres.listar_detalle_de_cierre(conexion, cierre_1)[0])
    assert detalle_1_despues == detalle_1_antes  # el cierre anterior no se tocó

    detalle_2 = datos_cierres.listar_detalle_de_cierre(conexion, cierre_2)[0]
    assert detalle_2["egresos"] == Decimal("1000")  # el contramovimiento cayó en el día actual
    assert detalle_2["diferencia"] == Decimal("0")


def test_cobrar_cheque_lo_pasa_a_cobrado_y_es_una_transferencia_interna(
    conexion, formas_pago, croma
):
    cheque_forma = formas_pago["Cheque"]
    transferencia = formas_pago["Transferencia"]

    asentar_cobranza(
        conexion,
        croma,
        "2024-03-20",
        pagos=[
            Pago(
                cheque_forma,
                Decimal("500"),
                cheque=DatosCheque("888", "Banco Nación", "2024-04-01"),
            )
        ],
        aplicaciones=[],
    )
    cheque_id = datos_cheques.listar_cheques_en_cartera(conexion)[0]["id"]

    cobrar_cheque(conexion, cheque_id, "2024-04-01", cheque_forma, transferencia)

    cheque = datos_cheques.obtener_cheque(conexion, cheque_id)
    assert cheque["estado"] == "cobrado"

    ingresos_transferencia = [
        m
        for m in conexion.execute(
            "SELECT * FROM movimientos_caja WHERE forma_pago_id = ? AND tipo = 'ingreso'",
            (transferencia,),
        ).fetchall()
    ]
    assert any(m["monto"] == Decimal("500") for m in ingresos_transferencia)


def test_rechazar_cheque_cambia_su_estado(conexion, formas_pago, croma):
    cheque_forma = formas_pago["Cheque"]
    asentar_cobranza(
        conexion,
        croma,
        "2024-03-20",
        pagos=[
            Pago(
                cheque_forma,
                Decimal("500"),
                cheque=DatosCheque("999", "Banco Nación", "2024-04-01"),
            )
        ],
        aplicaciones=[],
    )
    cheque_id = datos_cheques.listar_cheques_en_cartera(conexion)[0]["id"]

    rechazar_cheque(conexion, cheque_id)

    cheque = datos_cheques.obtener_cheque(conexion, cheque_id)
    assert cheque["estado"] == "rechazado"


def test_no_se_puede_cobrar_un_cheque_que_no_esta_en_cartera(conexion, formas_pago, croma):
    cheque_forma = formas_pago["Cheque"]
    transferencia = formas_pago["Transferencia"]
    asentar_cobranza(
        conexion,
        croma,
        "2024-03-20",
        pagos=[
            Pago(
                cheque_forma,
                Decimal("500"),
                cheque=DatosCheque("111", "Banco Nación", "2024-04-01"),
            )
        ],
        aplicaciones=[],
    )
    cheque_id = datos_cheques.listar_cheques_en_cartera(conexion)[0]["id"]
    rechazar_cheque(conexion, cheque_id)

    with pytest.raises(ValueError):
        cobrar_cheque(conexion, cheque_id, "2024-04-01", cheque_forma, transferencia)


# --- Caja obligatoria para cobrar: cierre automático de cajas vencidas ---


def test_cerrar_cajas_vencidas_cierra_una_caja_vieja_sin_pedir_nada(conexion, formas_pago, croma):
    efectivo = formas_pago["Efectivo"]
    abrir_caja(conexion, "2024-03-01")
    asentar_cobranza(
        conexion, croma, "2024-03-01", pagos=[Pago(efectivo, Decimal("1000"))], aplicaciones=[]
    )

    cerrar_cajas_vencidas(conexion, "2024-03-02")

    cierre = datos_cierres.obtener_cierre_por_fecha(conexion, "2024-03-01")
    assert cierre["estado"] == "cerrado"
    detalle = datos_cierres.listar_detalle_de_cierre(conexion, cierre["id"])[0]
    assert detalle["saldo_teorico"] == Decimal("1000")
    assert detalle["arqueo"] == Decimal("1000")
    assert detalle["diferencia"] == Decimal("0")


def test_cerrar_cajas_vencidas_no_toca_la_caja_de_hoy(conexion):
    abrir_caja(conexion, "2024-03-02")

    cerrar_cajas_vencidas(conexion, "2024-03-02")

    cierre = datos_cierres.obtener_cierre_por_fecha(conexion, "2024-03-02")
    assert cierre["estado"] == "abierto"


def test_cerrar_cajas_vencidas_no_falla_si_el_dia_viejo_no_tuvo_movimientos(conexion):
    abrir_caja(conexion, "2024-03-01")

    cerrar_cajas_vencidas(conexion, "2024-03-02")

    cierre = datos_cierres.obtener_cierre_por_fecha(conexion, "2024-03-01")
    assert cierre["estado"] == "cerrado"
    assert datos_cierres.listar_detalle_de_cierre(conexion, cierre["id"]) == []


def test_hay_caja_abierta_hoy_es_falso_si_la_abierta_es_de_un_dia_anterior(conexion):
    abrir_caja(conexion, "2024-03-01")

    assert hay_caja_abierta_hoy(conexion, "2024-03-02") is False
    assert datos_cierres.obtener_cierre_por_fecha(conexion, "2024-03-01")["estado"] == "cerrado"


def test_hay_caja_abierta_hoy_es_verdadero_con_una_caja_abierta_hoy(conexion):
    abrir_caja(conexion, "2024-03-02")

    assert hay_caja_abierta_hoy(conexion, "2024-03-02") is True
