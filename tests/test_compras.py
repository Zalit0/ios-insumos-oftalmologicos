"""Etapa 6: proveedores, compras (facturas con IVA) y pagos a proveedores."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data import cheques as datos_cheques
from ios.data.db import conectar
from ios.domain.calculos import calcular_totales_mes
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services import proveedores as servicio_proveedores
from ios.services.cobranzas import DatosCheque, Pago, asentar_cobranza
from ios.services.compras import alta_compra, listar_compras
from ios.services.pagos_proveedor import listar_pagos_proveedor, registrar_pago_proveedor


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


def test_alta_proveedor_sin_nombre_falla(conexion):
    with pytest.raises(ValueError):
        servicio_proveedores.alta_proveedor(conexion, nombre="  ")


def test_cargar_factura_de_lentex_baja_el_iva_deuda(conexion, lentex):
    iva_venta_del_mes = Decimal("1000")

    totales_antes = calcular_totales_mes(
        montos_finales_vigentes=[],
        montos_aplicados_a_remitos_del_mes=[],
        ivas_venta_vigentes=[iva_venta_del_mes],
        ivas_compra=[],
        montos_compras=[],
        montos_pagos_proveedor=[],
        comision_pct=Decimal("0"),
    )

    alta_compra(
        conexion, lentex, "2024-03-07", "0001-00012345", Decimal("5000"), iva=Decimal("1050")
    )
    compras_del_mes = listar_compras(conexion, mes="2024-03")

    totales_despues = calcular_totales_mes(
        montos_finales_vigentes=[],
        montos_aplicados_a_remitos_del_mes=[],
        ivas_venta_vigentes=[iva_venta_del_mes],
        ivas_compra=[c["iva"] for c in compras_del_mes],
        montos_compras=[c["monto"] for c in compras_del_mes],
        montos_pagos_proveedor=[],
        comision_pct=Decimal("0"),
    )

    assert totales_antes.iva_deuda == Decimal("1000")
    assert totales_despues.iva_deuda == Decimal("-50")  # 1000 - 1050
    assert totales_despues.iva_deuda < totales_antes.iva_deuda


def test_alta_compra_con_proveedor_inexistente_falla(conexion):
    with pytest.raises(ValueError):
        alta_compra(conexion, 9999, "2024-03-07", "1", Decimal("1000"), iva=Decimal("210"))


# --- etapa 5: IVA automático (D2, D3) ---


def test_iva_se_calcula_solo_con_la_tasa_por_defecto(conexion, lentex):
    compra_id = alta_compra(conexion, lentex, "2024-03-07", "0001", Decimal("121000"))

    compra = [c for c in listar_compras(conexion) if c["id"] == compra_id][0]
    assert compra["tasa_iva"] == Decimal("21")
    assert compra["iva"] == Decimal("21000")
    assert compra["iva_manual"] == 0


def test_iva_se_calcula_con_una_tasa_distinta(conexion, lentex):
    compra_id = alta_compra(
        conexion, lentex, "2024-03-07", "0001", Decimal("110500"), tasa_iva=Decimal("10.5")
    )

    compra = [c for c in listar_compras(conexion) if c["id"] == compra_id][0]
    assert compra["tasa_iva"] == Decimal("10.5")
    assert compra["iva"] == Decimal("10500")
    assert compra["iva_manual"] == 0


def test_iva_tasa_cero_no_discrimina_iva(conexion, lentex):
    compra_id = alta_compra(
        conexion, lentex, "2024-03-07", "0001", Decimal("5000"), tasa_iva=Decimal("0")
    )

    compra = [c for c in listar_compras(conexion) if c["id"] == compra_id][0]
    assert compra["iva"] == Decimal("0")
    assert compra["iva_manual"] == 0


def test_corregir_el_iva_a_mano_lo_marca_manual(conexion, lentex):
    # 121000 al 21% calcula 21000; se corrige por una diferencia de redondeo
    # del proveedor.
    compra_id = alta_compra(
        conexion, lentex, "2024-03-07", "0001", Decimal("121000"), iva=Decimal("20998")
    )

    compra = [c for c in listar_compras(conexion) if c["id"] == compra_id][0]
    assert compra["iva"] == Decimal("20998")
    assert compra["iva_manual"] == 1


def test_iva_manual_igual_al_calculado_no_se_marca_manual(conexion, lentex):
    compra_id = alta_compra(
        conexion, lentex, "2024-03-07", "0001", Decimal("121000"), iva=Decimal("21000")
    )

    compra = [c for c in listar_compras(conexion) if c["id"] == compra_id][0]
    assert compra["iva_manual"] == 0


def test_pago_a_proveedor_genera_egreso_de_caja(conexion, lentex, formas_pago):
    registrar_pago_proveedor(
        conexion, lentex, "2024-03-10", Decimal("5000"), formas_pago["Transferencia"]
    )

    egresos = conexion.execute(
        "SELECT SUM(monto) AS total FROM movimientos_caja WHERE tipo = 'egreso'"
    ).fetchone()["total"]
    assert egresos == Decimal("5000")

    pagos = listar_pagos_proveedor(conexion, proveedor_id=lentex)
    assert len(pagos) == 1
    assert pagos[0]["monto"] == Decimal("5000")


def test_pago_a_proveedor_con_cheque_en_cartera(conexion, lentex, formas_pago):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-05",
        pagos=[
            Pago(
                formas_pago["Cheque"],
                Decimal("5000"),
                cheque=DatosCheque("555", "Banco Nación", "2024-04-01"),
            )
        ],
        aplicaciones=[],
    )
    cheque_id = datos_cheques.listar_cheques_en_cartera(conexion)[0]["id"]

    registrar_pago_proveedor(
        conexion,
        lentex,
        "2024-03-10",
        Decimal("5000"),
        formas_pago["Cheque"],
        cheque_entregado_id=cheque_id,
    )

    cheque = datos_cheques.obtener_cheque(conexion, cheque_id)
    assert cheque["estado"] == "entregado_a_proveedor"

    egresos = conexion.execute(
        "SELECT SUM(monto) AS total FROM movimientos_caja WHERE tipo = 'egreso'"
    ).fetchone()["total"]
    assert egresos == Decimal("5000")


def test_no_se_puede_pagar_con_un_cheque_que_no_esta_en_cartera(conexion, lentex, formas_pago):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-05",
        pagos=[
            Pago(
                formas_pago["Cheque"],
                Decimal("5000"),
                cheque=DatosCheque("555", "Banco Nación", "2024-04-01"),
            )
        ],
        aplicaciones=[],
    )
    cheque_id = datos_cheques.listar_cheques_en_cartera(conexion)[0]["id"]
    registrar_pago_proveedor(
        conexion, lentex, "2024-03-10", Decimal("5000"), formas_pago["Cheque"],
        cheque_entregado_id=cheque_id,
    )

    with pytest.raises(ValueError):
        registrar_pago_proveedor(
            conexion, lentex, "2024-03-15", Decimal("5000"), formas_pago["Cheque"],
            cheque_entregado_id=cheque_id,
        )


def test_un_pago_a_proveedor_resta_de_la_caja_y_un_recibo_suma(conexion, lentex, formas_pago):
    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="Croma")
    asentar_cobranza(
        conexion,
        cliente_id,
        "2024-03-05",
        pagos=[Pago(formas_pago["Efectivo"], Decimal("3000"))],
        aplicaciones=[],
    )
    registrar_pago_proveedor(
        conexion, lentex, "2024-03-10", Decimal("1000"), formas_pago["Efectivo"]
    )

    saldo_efectivo = conexion.execute(
        """
        SELECT
            (SELECT COALESCE(SUM(monto), 0) FROM movimientos_caja
             WHERE tipo = 'ingreso' AND forma_pago_id = ?) -
            (SELECT COALESCE(SUM(monto), 0) FROM movimientos_caja
             WHERE tipo = 'egreso' AND forma_pago_id = ?) AS saldo
        """,
        (formas_pago["Efectivo"], formas_pago["Efectivo"]),
    ).fetchone()["saldo"]

    assert saldo_efectivo == Decimal("2000")
