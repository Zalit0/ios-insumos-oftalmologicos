"""Pruebas de creación de la base y de las migraciones."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data.db import conectar
from ios.data.migraciones import MIGRACIONES, version_actual

TABLAS_DEL_PLAN = {
    "clientes",
    "sucursales",
    "tipos_comprobante",
    "comprobantes",
    "formas_pago",
    "recibos",
    "recibo_pagos",
    "cheques",
    "aplicaciones_pago",
    "proveedores",
    "compras",
    "pagos_proveedor",
    "categorias_caja",
    "movimientos_caja",
    "cierres_caja",
    "cierres_caja_detalle",
    "configuracion",
}


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "ios_test.db")
    try:
        yield conexion
    finally:
        conexion.close()


def test_crea_todas_las_tablas_del_plan(conexion):
    filas = conexion.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    tablas = {fila["name"] for fila in filas}

    assert TABLAS_DEL_PLAN <= tablas


def test_version_queda_en_la_ultima_migracion(conexion):
    assert version_actual(conexion) == len(MIGRACIONES)


def test_abrir_de_nuevo_no_reaplica_migraciones(tmp_path: Path):
    ruta = tmp_path / "ios_test.db"

    primera = conectar(ruta)
    primera.close()

    segunda = conectar(ruta)
    try:
        clientes = segunda.execute("SELECT COUNT(*) AS n FROM clientes").fetchone()["n"]
        # Si las migraciones se reaplicaran, el INSERT de Particulares
        # fallaría (o duplicaría filas); con una sola fila alcanza.
        assert clientes == 1
    finally:
        segunda.close()


def test_tipo_comprobante_rto(conexion):
    fila = conexion.execute(
        "SELECT nombre, abreviatura, activo FROM tipos_comprobante"
    ).fetchone()

    assert fila["abreviatura"] == "RTO"
    assert fila["activo"] == 1


def test_formas_de_pago_iniciales(conexion):
    filas = conexion.execute(
        "SELECT nombre, tipo FROM formas_pago ORDER BY nombre"
    ).fetchall()
    formas = {(fila["nombre"], fila["tipo"]) for fila in filas}

    assert formas == {
        ("Efectivo", "efectivo"),
        ("Transferencia", "banco"),
        ("Cheque", "cheque"),
    }


def test_configuracion_por_defecto(conexion):
    fila = conexion.execute(
        "SELECT iva_pct, comision_pct, redondeo_decimales, numero_inicial_recibo "
        "FROM configuracion WHERE id = 1"
    ).fetchone()

    assert fila["iva_pct"] == Decimal("21")
    assert fila["comision_pct"] == Decimal("15")
    assert fila["redondeo_decimales"] == 2
    assert fila["numero_inicial_recibo"] == 1


def test_cliente_particulares(conexion):
    fila = conexion.execute(
        "SELECT es_particular, activo FROM clientes WHERE nombre = 'Particulares'"
    ).fetchone()

    assert fila is not None
    assert fila["es_particular"] == 1
    assert fila["activo"] == 1


def test_particulares_tiene_sucursal_principal(conexion):
    fila = conexion.execute(
        """
        SELECT s.nombre FROM sucursales s
        JOIN clientes c ON c.id = s.cliente_id
        WHERE c.nombre = 'Particulares'
        """
    ).fetchone()

    assert fila is not None
    assert fila["nombre"] == "Principal"


def test_foreign_keys_activadas(conexion):
    valor = conexion.execute("PRAGMA foreign_keys").fetchone()[0]
    assert valor == 1


def test_importes_se_leen_como_decimal(conexion):
    cliente_id = conexion.execute(
        "SELECT id FROM clientes WHERE nombre = 'Particulares'"
    ).fetchone()["id"]
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ?", (cliente_id,)
    ).fetchone()["id"]
    tipo_id = conexion.execute(
        "SELECT id FROM tipos_comprobante WHERE abreviatura = 'RTO'"
    ).fetchone()["id"]

    conexion.execute(
        """
        INSERT INTO comprobantes
            (tipo_comprobante_id, numero, fecha, cliente_id, sucursal_id,
             monto_lista, descuento_pct, monto_final, con_iva, iva_discriminado)
        VALUES (?, '1', '2024-03-01', ?, ?, ?, '20', ?, 1, ?)
        """,
        (tipo_id, cliente_id, sucursal_id, Decimal("4416.40"), Decimal("3533.12"),
         Decimal("613.19")),
    )
    conexion.commit()

    fila = conexion.execute(
        "SELECT monto_lista, monto_final, iva_discriminado FROM comprobantes"
    ).fetchone()

    assert fila["monto_lista"] == Decimal("4416.40")
    assert fila["monto_final"] == Decimal("3533.12")
    assert fila["iva_discriminado"] == Decimal("613.19")
    assert isinstance(fila["monto_final"], Decimal)


def test_columnas_de_importe_se_guardan_como_texto_no_como_real(conexion):
    """Si la columna tuviera afinidad NUMERIC (type DECIMAL en vez de
    DECIMAL_TEXT), SQLite guardaría esto como REAL y se perdería la
    precisión exacta del Decimal."""
    cliente_id = conexion.execute(
        "SELECT id FROM clientes WHERE nombre = 'Particulares'"
    ).fetchone()["id"]
    conexion.execute(
        "UPDATE clientes SET descuento_default = ? WHERE id = ?",
        (Decimal("12.345"), cliente_id),
    )
    conexion.commit()

    tipo_de_dato = conexion.execute(
        "SELECT typeof(descuento_default) AS t FROM clientes WHERE id = ?", (cliente_id,)
    ).fetchone()["t"]

    assert tipo_de_dato == "text"
