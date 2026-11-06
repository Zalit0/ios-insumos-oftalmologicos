"""Detalle (renglones) de comprobantes (plan de detalle de comprobantes,
etapa 2): opcional, el total sale de sumar los renglones."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data import detalle_comprobante as datos_detalle
from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio
from ios.services.comprobantes import RenglonDetalle
from ios.services.tipos_cristal import alta_tipo_cristal


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
        conexion, nombre="Croma", descuento_default=Decimal("0"),
        con_iva_default=False, sucursales=["Croma"],
    )
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ? AND nombre = 'Croma'", (cliente_id,)
    ).fetchone()["id"]
    return cliente_id, sucursal_id


@pytest.fixture
def organico_blanco(conexion) -> int:
    return alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))


@pytest.fixture
def pegatina(conexion) -> int:
    return alta_tipo_cristal(
        conexion, "Pegatina Bluecut", Decimal("75000"),
        vendido_por="unidad", requiere_graduacion=False,
    )


def test_alta_con_detalle_suma_los_subtotales_como_monto_lista(conexion, rto_id, croma, organico_blanco):
    cliente_id, sucursal_id = croma

    comprobante_id = servicio.alta_comprobante_con_detalle(
        conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
        renglones=[
            RenglonDetalle(graduacion="OD +1.00 OI +1.25", cantidad=2, tipo_cristal_id=organico_blanco),
        ],
    )

    comprobante = conexion.execute(
        "SELECT monto_lista, monto_final FROM comprobantes WHERE id = ?", (comprobante_id,)
    ).fetchone()
    # precio_unitario = 4770 / 2 = 2385 (medio par); cantidad 2 -> 4770
    assert comprobante["monto_lista"] == Decimal("4770")
    assert comprobante["monto_final"] == Decimal("4770")


def test_alta_con_detalle_guarda_los_renglones(conexion, rto_id, croma, organico_blanco):
    cliente_id, sucursal_id = croma

    comprobante_id = servicio.alta_comprobante_con_detalle(
        conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
        renglones=[
            RenglonDetalle(graduacion="Neutro", cantidad=1, tipo_cristal_id=organico_blanco),
            RenglonDetalle(graduacion="OD +2.00", cantidad=1, tipo_cristal_id=organico_blanco),
        ],
    )

    renglones = datos_detalle.listar_detalle_por_comprobante(conexion, comprobante_id)
    assert len(renglones) == 2
    assert {r["graduacion"] for r in renglones} == {"Neutro", "OD +2.00"}
    assert all(r["tipo_cristal_nombre"] == "Orgánico blanco" for r in renglones)


def test_alta_con_detalle_sin_renglones_falla(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    with pytest.raises(ValueError):
        servicio.alta_comprobante_con_detalle(
            conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id, renglones=[],
        )


def test_alta_con_detalle_graduacion_obligatoria_en_cristal(conexion, rto_id, croma, organico_blanco):
    cliente_id, sucursal_id = croma
    with pytest.raises(ValueError, match="graduación"):
        servicio.alta_comprobante_con_detalle(
            conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
            renglones=[RenglonDetalle(graduacion="", cantidad=1, tipo_cristal_id=organico_blanco)],
        )


def test_alta_con_detalle_accesorio_no_pide_graduacion(conexion, rto_id, croma, pegatina):
    cliente_id, sucursal_id = croma

    comprobante_id = servicio.alta_comprobante_con_detalle(
        conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
        renglones=[RenglonDetalle(graduacion="", cantidad=1, tipo_cristal_id=pegatina)],
    )

    renglon = datos_detalle.listar_detalle_por_comprobante(conexion, comprobante_id)[0]
    assert renglon["precio_unitario"] == Decimal("75000")


def test_alta_con_detalle_cantidad_invalida_falla(conexion, rto_id, croma, organico_blanco):
    cliente_id, sucursal_id = croma
    with pytest.raises(ValueError):
        servicio.alta_comprobante_con_detalle(
            conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
            renglones=[RenglonDetalle(graduacion="Neutro", cantidad=0, tipo_cristal_id=organico_blanco)],
        )


def test_alta_con_detalle_sin_tipo_ni_descripcion_falla(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    with pytest.raises(ValueError):
        servicio.alta_comprobante_con_detalle(
            conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
            renglones=[RenglonDetalle(graduacion="Neutro", cantidad=1)],
        )


def test_alta_con_detalle_descripcion_libre_requiere_graduacion(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    with pytest.raises(ValueError, match="graduación"):
        servicio.alta_comprobante_con_detalle(
            conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
            renglones=[RenglonDetalle(
                graduacion="", cantidad=1, descripcion="Cristal sin catálogo",
                precio_unitario=Decimal("1000"),
            )],
        )


def test_alta_con_detalle_descripcion_libre_con_precio_manual(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma

    comprobante_id = servicio.alta_comprobante_con_detalle(
        conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
        renglones=[RenglonDetalle(
            graduacion="Neutro", cantidad=3, descripcion="Cristal sin catálogo",
            precio_unitario=Decimal("1000"),
        )],
    )

    comprobante = conexion.execute(
        "SELECT monto_lista FROM comprobantes WHERE id = ?", (comprobante_id,)
    ).fetchone()
    assert comprobante["monto_lista"] == Decimal("3000")


def test_alta_con_detalle_numero_duplicado_mismo_cliente_falla(conexion, rto_id, croma, organico_blanco):
    cliente_id, sucursal_id = croma
    servicio.alta_comprobante_con_detalle(
        conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
        renglones=[RenglonDetalle(graduacion="Neutro", cantidad=1, tipo_cristal_id=organico_blanco)],
    )

    with pytest.raises(servicio.NumeroDuplicadoError):
        servicio.alta_comprobante_con_detalle(
            conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
            renglones=[RenglonDetalle(graduacion="Neutro", cantidad=1, tipo_cristal_id=organico_blanco)],
        )


def test_anular_comprobante_con_detalle_no_borra_los_renglones(conexion, rto_id, croma, organico_blanco):
    cliente_id, sucursal_id = croma
    comprobante_id = servicio.alta_comprobante_con_detalle(
        conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
        renglones=[RenglonDetalle(graduacion="Neutro", cantidad=1, tipo_cristal_id=organico_blanco)],
    )

    servicio.anular_comprobante(conexion, comprobante_id)

    assert len(datos_detalle.listar_detalle_por_comprobante(conexion, comprobante_id)) == 1


def test_listar_detalle_comprobante_vacio_para_carga_rapida(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    comprobante_id = servicio.alta_comprobante(
        conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id, Decimal("1000"),
    )

    assert servicio.listar_detalle_comprobante(conexion, comprobante_id) == []
