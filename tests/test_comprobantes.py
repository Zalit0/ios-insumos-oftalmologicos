"""Etapa 3: carga, edición, anulación y control de duplicados de comprobantes."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data import comprobantes as datos
from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio
from ios.services import tipos_comprobante as servicio_tipos


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "ios_test.db")
    try:
        yield conexion
    finally:
        conexion.close()


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
        con_iva_default=True,
        sucursales=["Croma", "Croma Fdez."],
    )
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ? AND nombre = 'Croma'", (cliente_id,)
    ).fetchone()["id"]
    return cliente_id, sucursal_id


def test_alta_usa_el_descuento_y_el_iva_del_cliente(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma

    comprobante_id = servicio.alta_comprobante(
        conexion,
        tipo_comprobante_id=rto_id,
        numero="45100",
        fecha="2024-03-05",
        cliente_id=cliente_id,
        sucursal_id=sucursal_id,
        monto_lista=Decimal("104544"),
    )

    comprobante = datos.obtener_comprobante(conexion, comprobante_id)
    assert comprobante["monto_final"] == Decimal("78408")
    assert comprobante["iva_discriminado"] == Decimal("13608")
    assert comprobante["descuento_pct"] == Decimal("25")
    assert comprobante["con_iva"] == 1
    assert comprobante["estado"] == "vigente"


def test_alta_permite_pisar_el_descuento_y_el_iva_del_remito(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma

    comprobante_id = servicio.alta_comprobante(
        conexion,
        tipo_comprobante_id=rto_id,
        numero="45101",
        fecha="2024-03-05",
        cliente_id=cliente_id,
        sucursal_id=sucursal_id,
        monto_lista=Decimal("4416.40"),
        descuento_pct=Decimal("20"),
        con_iva=False,
    )

    comprobante = datos.obtener_comprobante(conexion, comprobante_id)
    assert comprobante["monto_final"] == Decimal("3533.12")
    assert comprobante["iva_discriminado"] == Decimal("0.00")


def test_numero_repetido_se_rechaza_sin_forzar(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    servicio.alta_comprobante(
        conexion, rto_id, "45126", "2024-03-10", cliente_id, sucursal_id, Decimal("1000")
    )

    with pytest.raises(servicio.NumeroDuplicadoError):
        servicio.alta_comprobante(
            conexion, rto_id, "45126", "2024-03-11", cliente_id, sucursal_id, Decimal("2000")
        )


def test_numero_repetido_se_permite_forzando(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    servicio.alta_comprobante(
        conexion, rto_id, "45126", "2024-03-10", cliente_id, sucursal_id, Decimal("1000")
    )

    comprobante_id = servicio.alta_comprobante(
        conexion,
        rto_id,
        "45126",
        "2024-03-11",
        cliente_id,
        sucursal_id,
        Decimal("2000"),
        forzar_numero_repetido=True,
    )

    assert comprobante_id is not None
    comprobantes = datos.listar_comprobantes(conexion, cliente_id=cliente_id)
    assert len(comprobantes) == 2


def test_anular_comprobante_no_lo_borra(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    comprobante_id = servicio.alta_comprobante(
        conexion, rto_id, "45102", "2024-03-05", cliente_id, sucursal_id, Decimal("1000")
    )

    servicio.anular_comprobante(conexion, comprobante_id)

    comprobante = datos.obtener_comprobante(conexion, comprobante_id)
    assert comprobante is not None
    assert comprobante["estado"] == "anulado"


def test_registrar_devolucion_anula_el_comprobante(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    comprobante_id = servicio.alta_comprobante(
        conexion, rto_id, "45110", "2024-03-05", cliente_id, sucursal_id, Decimal("1000")
    )

    servicio.registrar_devolucion(conexion, comprobante_id)

    comprobante = datos.obtener_comprobante(conexion, comprobante_id)
    assert comprobante["estado"] == "anulado"


def test_registrar_devolucion_ya_repuesto_guarda_una_compensacion(conexion, rto_id, croma):
    from ios.data import compensaciones_reposicion as datos_compensaciones
    from ios.services.comprobantes import RenglonDetalle
    from ios.services.tipos_cristal import alta_tipo_cristal

    cliente_id, sucursal_id = croma
    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    comprobante_id = servicio.alta_comprobante_con_detalle(
        conexion, rto_id, "45111", "2024-03-05", cliente_id, sucursal_id,
        renglones=[RenglonDetalle(graduacion="Neutro", cantidad=2, tipo_cristal_id=organico)],
    )

    servicio.registrar_devolucion(conexion, comprobante_id, ya_repuesto=True)

    assert datos_compensaciones.obtener_cantidad_compensada(conexion, organico, "Neutro") == 2


def test_registrar_devolucion_sin_marcar_ya_repuesto_no_compensa(conexion, rto_id, croma):
    from ios.data import compensaciones_reposicion as datos_compensaciones
    from ios.services.comprobantes import RenglonDetalle
    from ios.services.tipos_cristal import alta_tipo_cristal

    cliente_id, sucursal_id = croma
    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    comprobante_id = servicio.alta_comprobante_con_detalle(
        conexion, rto_id, "45112", "2024-03-05", cliente_id, sucursal_id,
        renglones=[RenglonDetalle(graduacion="Neutro", cantidad=2, tipo_cristal_id=organico)],
    )

    servicio.registrar_devolucion(conexion, comprobante_id, ya_repuesto=False)

    assert datos_compensaciones.obtener_cantidad_compensada(conexion, organico, "Neutro") == 0


def test_numero_anulado_no_cuenta_como_repetido(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    primero_id = servicio.alta_comprobante(
        conexion, rto_id, "45103", "2024-03-05", cliente_id, sucursal_id, Decimal("1000")
    )
    servicio.anular_comprobante(conexion, primero_id)

    # No debería hacer falta forzar: el original está anulado.
    segundo_id = servicio.alta_comprobante(
        conexion, rto_id, "45103", "2024-03-06", cliente_id, sucursal_id, Decimal("2000")
    )
    assert segundo_id is not None


def test_editar_monto_lista_recalcula_final_e_iva(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    comprobante_id = servicio.alta_comprobante(
        conexion, rto_id, "45104", "2024-03-05", cliente_id, sucursal_id, Decimal("1000")
    )

    servicio.editar_comprobante(conexion, comprobante_id, monto_lista=Decimal("2000"))

    comprobante = datos.obtener_comprobante(conexion, comprobante_id)
    # 2000 con 25% de descuento (el de Croma) = 1500
    assert comprobante["monto_final"] == Decimal("1500")


def test_no_se_puede_editar_un_comprobante_anulado(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    comprobante_id = servicio.alta_comprobante(
        conexion, rto_id, "45105", "2024-03-05", cliente_id, sucursal_id, Decimal("1000")
    )
    servicio.anular_comprobante(conexion, comprobante_id)

    with pytest.raises(ValueError):
        servicio.editar_comprobante(conexion, comprobante_id, monto_lista=Decimal("2000"))


def test_tipos_de_comprobante_son_configurables(conexion):
    factura_id = servicio_tipos.alta_tipo_comprobante(conexion, "Factura", "FCA")

    cliente_id = servicio_clientes.alta_cliente(conexion, nombre="La Óptica")
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]

    comprobante_id = servicio.alta_comprobante(
        conexion, factura_id, "1", "2024-03-05", cliente_id, sucursal_id, Decimal("1000")
    )

    comprobante = datos.obtener_comprobante(conexion, comprobante_id)
    assert comprobante["tipo_comprobante_id"] == factura_id


def test_numero_repetido_en_otro_cliente_no_bloquea(conexion, rto_id, croma):
    """D1 (docs/AJUSTES_V1.1.md): entre clientes distintos nunca bloquea."""
    cliente_id, sucursal_id = croma
    servicio.alta_comprobante(
        conexion, rto_id, "45142", "2024-03-10", cliente_id, sucursal_id, Decimal("1000")
    )

    mirage_id = servicio_clientes.alta_cliente(conexion, nombre="Mirage")
    sucursal_mirage = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (mirage_id,)
    ).fetchone()["id"]

    # No hace falta forzar: es otro cliente.
    comprobante_id = servicio.alta_comprobante(
        conexion, rto_id, "45142", "2024-03-11", mirage_id, sucursal_mirage, Decimal("2000")
    )
    assert comprobante_id is not None


def test_buscar_coincidencias_numero_devuelve_el_detalle(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    servicio.alta_comprobante(
        conexion, rto_id, "45142", "2024-03-10", cliente_id, sucursal_id, Decimal("1000")
    )
    mirage_id = servicio_clientes.alta_cliente(conexion, nombre="Mirage")
    sucursal_mirage = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (mirage_id,)
    ).fetchone()["id"]
    servicio.alta_comprobante(
        conexion, rto_id, "45142", "2024-03-11", mirage_id, sucursal_mirage, Decimal("2000"),
        forzar_numero_repetido=True,
    )

    coincidencias = servicio.buscar_coincidencias_numero(conexion, rto_id, "45142")
    assert len(coincidencias) == 2
    nombres = {c.cliente_nombre for c in coincidencias}
    assert nombres == {"Croma", "Mirage"}


def test_editar_monto_falla_si_tiene_pagos_aplicados(conexion, rto_id, croma):
    from ios.services.cobranzas import AplicacionARemito, Pago, asentar_cobranza

    cliente_id, sucursal_id = croma
    comprobante_id = servicio.alta_comprobante(
        conexion, rto_id, "45200", "2024-03-05", cliente_id, sucursal_id, Decimal("1000"),
        descuento_pct=Decimal("0"), con_iva=False,
    )
    efectivo_id = conexion.execute(
        "SELECT id FROM formas_pago WHERE nombre = 'Efectivo'"
    ).fetchone()["id"]
    asentar_cobranza(
        conexion, cliente_id, "2024-03-06",
        pagos=[Pago(efectivo_id, Decimal("1000"))],
        aplicaciones=[AplicacionARemito(comprobante_id, Decimal("1000"))],
    )

    assert servicio.tiene_pagos_aplicados(conexion, comprobante_id) is True

    with pytest.raises(ValueError):
        servicio.editar_comprobante(conexion, comprobante_id, monto_lista=Decimal("2000"))

    # Número y fecha sí se pueden corregir aunque tenga pagos aplicados.
    servicio.editar_comprobante(conexion, comprobante_id, numero="45201", fecha="2024-03-07")
    comprobante = datos.obtener_comprobante(conexion, comprobante_id)
    assert comprobante["numero"] == "45201"
    assert comprobante["fecha"] == "2024-03-07"


def test_editar_numero_a_uno_repetido_del_mismo_cliente_pide_confirmar(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    servicio.alta_comprobante(
        conexion, rto_id, "45300", "2024-03-05", cliente_id, sucursal_id, Decimal("1000")
    )
    otro_id = servicio.alta_comprobante(
        conexion, rto_id, "45301", "2024-03-06", cliente_id, sucursal_id, Decimal("1000")
    )

    with pytest.raises(servicio.NumeroDuplicadoError):
        servicio.editar_comprobante(conexion, otro_id, numero="45300")

    # Con forzar, sí se puede.
    servicio.editar_comprobante(conexion, otro_id, forzar_numero_repetido=True, numero="45300")
    comprobante = datos.obtener_comprobante(conexion, otro_id)
    assert comprobante["numero"] == "45300"


def test_cargar_un_mes_de_remitos_sin_tocar_formulas(conexion, rto_id, croma):
    """Caso de aceptación de la etapa: cargar varios remitos de un mes y que
    el total de ventas sea la suma de sus montos finales, calculados cada
    uno con su propio descuento/IVA."""
    cliente_id, sucursal_id = croma

    datos_remitos = [
        ("45110", Decimal("104544"), None, None),  # usa el descuento/IVA de Croma
        ("45111", Decimal("4416.40"), Decimal("20"), True),
        ("45112", Decimal("1000"), Decimal("0"), False),
    ]

    for numero, monto_lista, descuento, con_iva in datos_remitos:
        servicio.alta_comprobante(
            conexion,
            rto_id,
            numero,
            "2024-03-15",
            cliente_id,
            sucursal_id,
            monto_lista,
            descuento_pct=descuento,
            con_iva=con_iva,
        )

    comprobantes = servicio.listar_comprobantes(conexion, cliente_id=cliente_id, mes="2024-03")
    assert len(comprobantes) == 3

    total_venta = sum((c["monto_final"] for c in comprobantes), Decimal(0))
    assert total_venta == Decimal("78408") + Decimal("3533.12") + Decimal("1000")


def test_siguiente_numero_comprobante_empieza_en_1_sin_remitos(conexion, rto_id):
    assert servicio.siguiente_numero_comprobante(conexion, rto_id) == "1"


def test_siguiente_numero_comprobante_sigue_al_mayor_existente(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    servicio.alta_comprobante(
        conexion, rto_id, "500", "2026-03-05", cliente_id, sucursal_id, Decimal("1000"),
    )

    assert servicio.siguiente_numero_comprobante(conexion, rto_id) == "501"


def test_siguiente_numero_comprobante_ignora_numeros_no_numericos(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    servicio.alta_comprobante(
        conexion, rto_id, "S/N", "2026-03-05", cliente_id, sucursal_id, Decimal("1000"),
    )

    assert servicio.siguiente_numero_comprobante(conexion, rto_id) == "1"


def test_siguiente_numero_comprobante_no_baja_si_el_mayor_esta_anulado(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    comprobante_id = servicio.alta_comprobante(
        conexion, rto_id, "500", "2026-03-05", cliente_id, sucursal_id, Decimal("1000"),
    )
    servicio.anular_comprobante(conexion, comprobante_id)

    assert servicio.siguiente_numero_comprobante(conexion, rto_id) == "501"


def test_siguiente_numero_comprobante_es_independiente_por_tipo(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    otro_tipo_id = servicio_tipos.alta_tipo_comprobante(conexion, "Factura", "FAC")
    servicio.alta_comprobante(
        conexion, rto_id, "500", "2026-03-05", cliente_id, sucursal_id, Decimal("1000"),
    )

    assert servicio.siguiente_numero_comprobante(conexion, otro_tipo_id) == "1"
