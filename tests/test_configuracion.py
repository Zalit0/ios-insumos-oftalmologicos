"""Servicios de configuración y formas de pago."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data.db import conectar
from ios.services.configuracion import actualizar_configuracion, obtener_configuracion
from ios.services.formas_pago import alta_forma_pago


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "ios_test.db")
    try:
        yield conexion
    finally:
        conexion.close()


def test_actualizar_configuracion(conexion):
    actualizar_configuracion(conexion, iva_pct=Decimal("22"), comision_pct=Decimal("10"))
    config = obtener_configuracion(conexion)
    assert config["iva_pct"] == Decimal("22")
    assert config["comision_pct"] == Decimal("10")


def test_actualizar_configuracion_rechaza_iva_negativo(conexion):
    with pytest.raises(ValueError):
        actualizar_configuracion(conexion, iva_pct=Decimal("-1"))


def test_actualizar_configuracion_rechaza_numero_inicial_recibo_invalido(conexion):
    with pytest.raises(ValueError):
        actualizar_configuracion(conexion, numero_inicial_recibo=0)


def test_actualizar_configuracion_rechaza_campo_desconocido(conexion):
    with pytest.raises(ValueError):
        actualizar_configuracion(conexion, campo_inventado=1)


def test_alta_forma_pago(conexion):
    forma_id = alta_forma_pago(conexion, "Mercado Pago", "otro")
    fila = conexion.execute("SELECT * FROM formas_pago WHERE id = ?", (forma_id,)).fetchone()
    assert fila["nombre"] == "Mercado Pago"
    assert fila["tipo"] == "otro"


def test_alta_forma_pago_rechaza_tipo_invalido(conexion):
    with pytest.raises(ValueError):
        alta_forma_pago(conexion, "Bitcoin", "cripto")
