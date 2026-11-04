"""Etapa 2: alta, edición y baja lógica de clientes y sucursales."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data import clientes as datos
from ios.data.db import conectar
from ios.services import clientes as servicio


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "ios_test.db")
    try:
        yield conexion
    finally:
        conexion.close()


def test_particulares_ya_existe_desde_la_migracion(conexion):
    clientes = datos.listar_clientes(conexion)
    nombres = {c["nombre"] for c in clientes}

    assert "Particulares" in nombres


def test_alta_cliente_crea_sucursal_principal_por_defecto(conexion):
    cliente_id = servicio.alta_cliente(conexion, nombre="La Óptica")

    sucursales = datos.listar_sucursales(conexion, cliente_id)

    assert len(sucursales) == 1
    assert sucursales[0]["nombre"] == "Principal"


def test_alta_cliente_croma_con_dos_sucursales(conexion):
    cliente_id = servicio.alta_cliente(
        conexion,
        nombre="Croma",
        descuento_default=Decimal("25"),
        sucursales=["Croma", "Croma Fdez."],
    )

    sucursales = datos.listar_sucursales(conexion, cliente_id)
    nombres = [s["nombre"] for s in sucursales]

    assert nombres == ["Croma", "Croma Fdez."]
    assert all(s["cliente_id"] == cliente_id for s in sucursales)


def test_alta_cliente_sin_nombre_falla(conexion):
    with pytest.raises(ValueError):
        servicio.alta_cliente(conexion, nombre="   ")


def test_editar_cliente_actualiza_campos(conexion):
    cliente_id = servicio.alta_cliente(conexion, nombre="Crisol")

    servicio.editar_cliente(
        conexion, cliente_id, telefono="011-1234", descuento_default=Decimal("10")
    )

    cliente = datos.obtener_cliente(conexion, cliente_id)
    assert cliente["telefono"] == "011-1234"
    assert cliente["descuento_default"] == Decimal("10")
    assert cliente["nombre"] == "Crisol"  # no se tocó


def test_editar_cliente_inexistente_falla(conexion):
    with pytest.raises(ValueError):
        servicio.editar_cliente(conexion, 9999, telefono="x")


def test_baja_logica_no_borra_la_fila(conexion):
    cliente_id = servicio.alta_cliente(conexion, nombre="Mirage")

    servicio.baja_logica_cliente(conexion, cliente_id)

    cliente = datos.obtener_cliente(conexion, cliente_id)
    assert cliente is not None
    assert cliente["activo"] == 0


def test_listar_clientes_excluye_inactivos_por_defecto(conexion):
    cliente_id = servicio.alta_cliente(conexion, nombre="Del Pilar")
    servicio.baja_logica_cliente(conexion, cliente_id)

    activos = datos.listar_clientes(conexion)
    todos = datos.listar_clientes(conexion, incluir_inactivos=True)

    assert cliente_id not in {c["id"] for c in activos}
    assert cliente_id in {c["id"] for c in todos}


def test_alta_sucursal_agrega_una_sucursal_a_cliente_existente(conexion):
    cliente_id = servicio.alta_cliente(conexion, nombre="Koral")

    servicio.alta_sucursal(conexion, cliente_id, "Koral Norte")

    sucursales = datos.listar_sucursales(conexion, cliente_id)
    nombres = {s["nombre"] for s in sucursales}
    assert nombres == {"Principal", "Koral Norte"}


def test_editar_sucursal_cambia_el_nombre(conexion):
    cliente_id = servicio.alta_cliente(conexion, nombre="Koral")
    sucursal_id = datos.listar_sucursales(conexion, cliente_id)[0]["id"]

    servicio.editar_sucursal(conexion, sucursal_id, "Casa Central")

    sucursales = datos.listar_sucursales(conexion, cliente_id)
    assert sucursales[0]["nombre"] == "Casa Central"


def test_agregar_cliente_no_modifica_otros_clientes(conexion):
    croma_id = servicio.alta_cliente(conexion, nombre="Croma", descuento_default=Decimal("25"))

    servicio.alta_cliente(conexion, nombre="Mirage")

    croma = datos.obtener_cliente(conexion, croma_id)
    assert croma["nombre"] == "Croma"
    assert croma["descuento_default"] == Decimal("25")


# --- etapa 4: nombre no repetido ---


def test_alta_cliente_con_nombre_repetido_falla(conexion):
    servicio.alta_cliente(conexion, nombre="Croma")

    with pytest.raises(servicio.NombreDuplicadoError):
        servicio.alta_cliente(conexion, nombre="croma")  # sin distinguir mayúsculas


def test_editar_cliente_a_nombre_repetido_falla(conexion):
    servicio.alta_cliente(conexion, nombre="Croma")
    mirage_id = servicio.alta_cliente(conexion, nombre="Mirage")

    with pytest.raises(servicio.NombreDuplicadoError):
        servicio.editar_cliente(conexion, mirage_id, nombre="Croma")


def test_editar_cliente_puede_mantener_su_propio_nombre(conexion):
    cliente_id = servicio.alta_cliente(conexion, nombre="Croma")

    servicio.editar_cliente(conexion, cliente_id, nombre="Croma", telefono="011-1111")

    cliente = datos.obtener_cliente(conexion, cliente_id)
    assert cliente["telefono"] == "011-1111"


# --- etapa 4: reactivar cliente ---


def test_reactivar_cliente(conexion):
    cliente_id = servicio.alta_cliente(conexion, nombre="Mirage")
    servicio.baja_logica_cliente(conexion, cliente_id)

    servicio.reactivar_cliente(conexion, cliente_id)

    cliente = datos.obtener_cliente(conexion, cliente_id)
    assert cliente["activo"] == 1


def test_reactivar_cliente_inexistente_falla(conexion):
    with pytest.raises(ValueError):
        servicio.reactivar_cliente(conexion, 9999)


# --- etapa 4: desactivar/reactivar sucursal ---


def test_desactivar_sucursal_la_marca_inactiva(conexion):
    cliente_id = servicio.alta_cliente(conexion, nombre="Koral", sucursales=["Koral", "Koral Norte"])
    sucursales = datos.listar_sucursales(conexion, cliente_id)
    a_desactivar = sucursales[1]["id"]

    servicio.desactivar_sucursal(conexion, a_desactivar)

    activas = datos.listar_sucursales(conexion, cliente_id)
    todas = datos.listar_sucursales(conexion, cliente_id, incluir_inactivas=True)
    assert a_desactivar not in {s["id"] for s in activas}
    assert a_desactivar in {s["id"] for s in todas}


def test_no_se_puede_desactivar_la_unica_sucursal_activa(conexion):
    cliente_id = servicio.alta_cliente(conexion, nombre="Koral")
    sucursal_id = datos.listar_sucursales(conexion, cliente_id)[0]["id"]

    with pytest.raises(servicio.UltimaSucursalActivaError):
        servicio.desactivar_sucursal(conexion, sucursal_id)


def test_reactivar_sucursal(conexion):
    cliente_id = servicio.alta_cliente(conexion, nombre="Koral", sucursales=["Koral", "Koral Norte"])
    sucursal_id = datos.listar_sucursales(conexion, cliente_id)[1]["id"]
    servicio.desactivar_sucursal(conexion, sucursal_id)

    servicio.reactivar_sucursal(conexion, sucursal_id)

    activas = datos.listar_sucursales(conexion, cliente_id)
    assert sucursal_id in {s["id"] for s in activas}
