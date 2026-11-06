"""Catálogo de tipos de cristal (plan de detalle de comprobantes, etapa 1)."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data import tipos_cristal as datos
from ios.data.db import conectar
from ios.services.tipos_cristal import (
    alta_tipo_cristal,
    baja_logica_tipo_cristal,
    editar_tipo_cristal,
    precio_unitario,
)


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "ios_test.db")
    try:
        yield conexion
    finally:
        conexion.close()


def test_alta_tipo_cristal_valores_por_defecto(conexion):
    tipo_id = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))

    tipo = datos.obtener_tipo_cristal(conexion, tipo_id)
    assert tipo["nombre"] == "Orgánico blanco"
    assert tipo["precio_lista"] == Decimal("4770")
    assert tipo["vendido_por"] == "par"
    assert tipo["requiere_graduacion"] == 1
    assert tipo["reponible"] == 1
    assert tipo["activo"] == 1


def test_alta_tipo_cristal_accesorio_sin_graduacion(conexion):
    tipo_id = alta_tipo_cristal(
        conexion, "Pegatina Bluecut 24mm", Decimal("75000"),
        categoria="Pegatinas", vendido_por="unidad", requiere_graduacion=False,
    )

    tipo = datos.obtener_tipo_cristal(conexion, tipo_id)
    assert tipo["vendido_por"] == "unidad"
    assert tipo["requiere_graduacion"] == 0


def test_alta_tipo_cristal_no_reponible(conexion):
    tipo_id = alta_tipo_cristal(
        conexion, "Mineral blanco", Decimal("12000"), categoria="Minerales", reponible=False,
    )

    assert datos.obtener_tipo_cristal(conexion, tipo_id)["reponible"] == 0


def test_alta_tipo_cristal_nombre_vacio_falla(conexion):
    with pytest.raises(ValueError):
        alta_tipo_cristal(conexion, "   ", Decimal("100"))


def test_alta_tipo_cristal_precio_negativo_falla(conexion):
    with pytest.raises(ValueError):
        alta_tipo_cristal(conexion, "Cristal", Decimal("-1"))


def test_alta_tipo_cristal_vendido_por_invalido_falla(conexion):
    with pytest.raises(ValueError):
        alta_tipo_cristal(conexion, "Cristal", Decimal("100"), vendido_por="docena")


def test_editar_tipo_cristal_actualiza_precio(conexion):
    tipo_id = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))

    editar_tipo_cristal(conexion, tipo_id, precio_lista=Decimal("5000"))

    assert datos.obtener_tipo_cristal(conexion, tipo_id)["precio_lista"] == Decimal("5000")


def test_editar_tipo_cristal_inexistente_falla(conexion):
    with pytest.raises(ValueError):
        editar_tipo_cristal(conexion, 999, precio_lista=Decimal("100"))


def test_baja_logica_tipo_cristal_lo_oculta_del_listado_activo(conexion):
    tipo_id = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))

    baja_logica_tipo_cristal(conexion, tipo_id)

    assert tipo_id not in {t["id"] for t in datos.listar_tipos_cristal(conexion)}
    assert tipo_id in {
        t["id"] for t in datos.listar_tipos_cristal(conexion, incluir_inactivos=True)
    }


def test_precio_unitario_par_es_la_mitad(conexion):
    tipo_id = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    tipo = datos.obtener_tipo_cristal(conexion, tipo_id)

    assert precio_unitario(tipo) == Decimal("2385")


def test_precio_unitario_unidad_es_el_precio_de_lista(conexion):
    tipo_id = alta_tipo_cristal(
        conexion, "Pegatina", Decimal("75000"), vendido_por="unidad", requiere_graduacion=False,
    )
    tipo = datos.obtener_tipo_cristal(conexion, tipo_id)

    assert precio_unitario(tipo) == Decimal("75000")


def test_listar_tipos_cristal_incluir_inactivos(conexion):
    activo_id = alta_tipo_cristal(conexion, "Activo", Decimal("100"))
    inactivo_id = alta_tipo_cristal(conexion, "Inactivo", Decimal("100"))
    baja_logica_tipo_cristal(conexion, inactivo_id)

    activos = {t["id"] for t in datos.listar_tipos_cristal(conexion)}
    assert activos == {activo_id}
