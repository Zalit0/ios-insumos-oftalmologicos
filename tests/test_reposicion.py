"""Reporte de reposición: unidades vendidas de cristales de stock por tipo,
en un rango de fechas (plan de detalle de comprobantes, etapa 3)."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services.comprobantes import RenglonDetalle
from ios.services.reposicion import reporte_reposicion
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


def _cargar(conexion, rto_id, croma, numero, fecha, tipo_cristal_id, cantidad, graduacion="Neutro"):
    cliente_id, sucursal_id = croma
    return servicio_comprobantes.alta_comprobante_con_detalle(
        conexion, rto_id, numero, fecha, cliente_id, sucursal_id,
        renglones=[RenglonDetalle(graduacion=graduacion, cantidad=cantidad, tipo_cristal_id=tipo_cristal_id)],
    )


def test_reporte_vacio_sin_ventas(conexion):
    assert reporte_reposicion(conexion, "2026-01-01", "2026-01-31") == []


def test_reporte_suma_unidades_del_mismo_tipo_entre_varios_comprobantes(conexion, rto_id, croma):
    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    _cargar(conexion, rto_id, croma, "1001", "2026-03-05", organico, 2)
    _cargar(conexion, rto_id, croma, "1002", "2026-03-10", organico, 1)

    reporte = reporte_reposicion(conexion, "2026-03-01", "2026-03-31")

    assert len(reporte) == 1
    assert reporte[0].nombre == "Orgánico blanco"
    assert reporte[0].graduacion == "Neutro"
    assert reporte[0].cantidad_vendida == 3


def test_reporte_separa_el_mismo_tipo_por_graduacion_distinta(conexion, rto_id, croma):
    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    _cargar(conexion, rto_id, croma, "1001", "2026-03-05", organico, 1, graduacion="ESF +1.00 CIL +0.00")
    _cargar(conexion, rto_id, croma, "1002", "2026-03-06", organico, 2, graduacion="ESF -2.50 CIL +0.00")

    reporte = reporte_reposicion(conexion, "2026-03-01", "2026-03-31")

    por_graduacion = {item.graduacion: item.cantidad_vendida for item in reporte}
    assert por_graduacion == {"ESF +1.00 CIL +0.00": 1, "ESF -2.50 CIL +0.00": 2}


def test_reporte_agrupa_por_tipo_de_cristal(conexion, rto_id, croma):
    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    policarbonato = alta_tipo_cristal(conexion, "Policarbonato blanco", Decimal("13730"))
    _cargar(conexion, rto_id, croma, "1001", "2026-03-05", organico, 2)
    _cargar(conexion, rto_id, croma, "1002", "2026-03-06", policarbonato, 1)

    reporte = reporte_reposicion(conexion, "2026-03-01", "2026-03-31")

    por_nombre = {item.nombre: item.cantidad_vendida for item in reporte}
    assert por_nombre == {"Orgánico blanco": 2, "Policarbonato blanco": 1}


def test_reporte_excluye_fechas_fuera_de_rango(conexion, rto_id, croma):
    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    _cargar(conexion, rto_id, croma, "1001", "2026-02-28", organico, 2)

    assert reporte_reposicion(conexion, "2026-03-01", "2026-03-31") == []


def test_reporte_excluye_comprobantes_anulados(conexion, rto_id, croma):
    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    comprobante_id = _cargar(conexion, rto_id, croma, "1001", "2026-03-05", organico, 2)
    servicio_comprobantes.anular_comprobante(conexion, comprobante_id)

    assert reporte_reposicion(conexion, "2026-03-01", "2026-03-31") == []


def test_reporte_excluye_tipos_no_reponibles(conexion, rto_id, croma):
    mineral = alta_tipo_cristal(conexion, "Mineral blanco", Decimal("12000"), reponible=False)
    _cargar(conexion, rto_id, croma, "1001", "2026-03-05", mineral, 2)

    assert reporte_reposicion(conexion, "2026-03-01", "2026-03-31") == []


def test_reporte_excluye_lo_ya_marcado_como_incluido_en_otro_pedido(conexion, rto_id, croma):
    """Si ya se generó un pedido de reposición del día 1, y después se
    genera otro de los días 1 al 3, lo del día 1 no se tiene que volver a
    contar — si no, se termina pidiendo dos veces lo mismo."""
    from ios.services.reposicion import marcar_reposicion_generada

    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    _cargar(conexion, rto_id, croma, "1001", "2026-03-01", organico, 2)
    _cargar(conexion, rto_id, croma, "1002", "2026-03-03", organico, 1)

    primer_reporte = reporte_reposicion(conexion, "2026-03-01", "2026-03-01")
    assert primer_reporte[0].cantidad_vendida == 2
    marcar_reposicion_generada(conexion, primer_reporte[0])

    segundo_reporte = reporte_reposicion(conexion, "2026-03-01", "2026-03-03")

    assert len(segundo_reporte) == 1
    assert segundo_reporte[0].cantidad_vendida == 1  # solo lo del día 3, lo del 1 ya se pidió


def test_reporte_excluye_renglones_sin_tipo_de_cristal(conexion, rto_id, croma):
    cliente_id, sucursal_id = croma
    servicio_comprobantes.alta_comprobante_con_detalle(
        conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
        renglones=[RenglonDetalle(
            graduacion="Neutro", cantidad=1, descripcion="Cristal sin catálogo",
            precio_unitario=Decimal("1000"),
        )],
    )

    assert reporte_reposicion(conexion, "2026-03-01", "2026-03-31") == []
