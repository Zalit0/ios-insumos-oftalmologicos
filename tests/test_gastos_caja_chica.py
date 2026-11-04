"""Etapa 6.2 (D4): reporte "Gastos de caja chica": egresos manuales de
caja (gastos y retiros), por categoría."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data.db import conectar
from ios.services.caja import registrar_movimiento_manual
from ios.services.categorias_caja import alta_categoria
from ios.services.gastos_caja_chica import SIN_CATEGORIA, gastos_de_caja_chica


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "ios_test.db")
    try:
        yield conexion
    finally:
        conexion.close()


@pytest.fixture
def efectivo_id(conexion) -> int:
    return conexion.execute("SELECT id FROM formas_pago WHERE nombre = 'Efectivo'").fetchone()["id"]


@pytest.fixture
def transferencia_id(conexion) -> int:
    return conexion.execute("SELECT id FROM formas_pago WHERE nombre = 'Transferencia'").fetchone()["id"]


def test_sin_movimientos(conexion):
    resultado = gastos_de_caja_chica(conexion, "2024-03-01", "2024-03-31")
    assert resultado.filas == []
    assert resultado.total == Decimal("0")


def test_solo_toma_egresos_manuales(conexion, efectivo_id):
    categoria_id = alta_categoria(conexion, "Insumos", "egreso")
    registrar_movimiento_manual(
        conexion, "2024-03-05 10:00", "egreso", efectivo_id, Decimal("500"),
        categoria_id=categoria_id, concepto="Café",
    )
    # ingreso manual: no debe aparecer
    registrar_movimiento_manual(
        conexion, "2024-03-05 11:00", "ingreso", efectivo_id, Decimal("1000"),
        categoria_id=categoria_id,
    )

    resultado = gastos_de_caja_chica(conexion, "2024-03-01", "2024-03-31")

    assert len(resultado.filas) == 1
    assert resultado.filas[0].concepto == "Café"
    assert resultado.total == Decimal("500")


def test_excluye_egresos_que_no_son_manuales(conexion, efectivo_id):
    from ios.data import caja as datos_caja
    categoria_id = alta_categoria(conexion, "Insumos", "egreso")
    datos_caja.insertar_movimiento(
        conexion, "2024-03-05 10:00", "egreso", efectivo_id, Decimal("500"),
        origen="pago_proveedor", categoria_id=categoria_id,
    )
    conexion.commit()

    resultado = gastos_de_caja_chica(conexion, "2024-03-01", "2024-03-31")

    assert resultado.filas == []


def test_filtra_por_fecha(conexion, efectivo_id):
    categoria_id = alta_categoria(conexion, "Insumos", "egreso")
    registrar_movimiento_manual(
        conexion, "2024-02-20 10:00", "egreso", efectivo_id, Decimal("100"), categoria_id=categoria_id
    )
    registrar_movimiento_manual(
        conexion, "2024-03-10 10:00", "egreso", efectivo_id, Decimal("200"), categoria_id=categoria_id
    )

    resultado = gastos_de_caja_chica(conexion, "2024-03-01", "2024-03-31")

    assert resultado.total == Decimal("200")


def test_filtra_por_categoria(conexion, efectivo_id):
    insumos_id = alta_categoria(conexion, "Insumos", "egreso")
    alquiler_id = alta_categoria(conexion, "Alquiler", "egreso")
    registrar_movimiento_manual(
        conexion, "2024-03-05 10:00", "egreso", efectivo_id, Decimal("100"), categoria_id=insumos_id
    )
    registrar_movimiento_manual(
        conexion, "2024-03-06 10:00", "egreso", efectivo_id, Decimal("300"), categoria_id=alquiler_id
    )

    resultado = gastos_de_caja_chica(conexion, "2024-03-01", "2024-03-31", categoria_id=alquiler_id)

    assert len(resultado.filas) == 1
    assert resultado.total == Decimal("300")


def test_filtra_por_forma_de_pago(conexion, efectivo_id, transferencia_id):
    categoria_id = alta_categoria(conexion, "Insumos", "egreso")
    registrar_movimiento_manual(
        conexion, "2024-03-05 10:00", "egreso", efectivo_id, Decimal("100"), categoria_id=categoria_id
    )
    registrar_movimiento_manual(
        conexion, "2024-03-06 10:00", "egreso", transferencia_id, Decimal("300"), categoria_id=categoria_id
    )

    resultado = gastos_de_caja_chica(
        conexion, "2024-03-01", "2024-03-31", forma_pago_id=transferencia_id
    )

    assert len(resultado.filas) == 1
    assert resultado.total == Decimal("300")


def test_subtotal_por_categoria(conexion, efectivo_id):
    insumos_id = alta_categoria(conexion, "Insumos", "egreso")
    alquiler_id = alta_categoria(conexion, "Alquiler", "egreso")
    registrar_movimiento_manual(
        conexion, "2024-03-05 10:00", "egreso", efectivo_id, Decimal("100"), categoria_id=insumos_id
    )
    registrar_movimiento_manual(
        conexion, "2024-03-06 10:00", "egreso", efectivo_id, Decimal("50"), categoria_id=insumos_id
    )
    registrar_movimiento_manual(
        conexion, "2024-03-07 10:00", "egreso", efectivo_id, Decimal("300"), categoria_id=alquiler_id
    )

    resultado = gastos_de_caja_chica(conexion, "2024-03-01", "2024-03-31")

    subtotales = {s.nombre: s.monto for s in resultado.subtotales_por_categoria}
    assert subtotales["Insumos"] == Decimal("150")
    assert subtotales["Alquiler"] == Decimal("300")
    assert resultado.total == Decimal("450")


def test_egreso_sin_categoria_se_agrupa_aparte(conexion, efectivo_id):
    registrar_movimiento_manual(conexion, "2024-03-05 10:00", "egreso", efectivo_id, Decimal("100"))

    resultado = gastos_de_caja_chica(conexion, "2024-03-01", "2024-03-31")

    assert resultado.filas[0].categoria_nombre == SIN_CATEGORIA
    subtotales = {s.nombre: s.monto for s in resultado.subtotales_por_categoria}
    assert subtotales[SIN_CATEGORIA] == Decimal("100")
