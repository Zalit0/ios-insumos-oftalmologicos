"""Casos de uso de clientes y sucursales (docs/PLAN.md, etapa 2).

Reglas de negocio:
- El nombre del cliente es obligatorio.
- Todo cliente tiene al menos una sucursal "Principal" (si no se indican
  sucursales propias, como en el caso Croma / Croma Fdez.).
- La baja de un cliente es lógica: nunca se borra la fila.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from ios.data import clientes as datos

SUCURSAL_POR_DEFECTO = "Principal"


class NombreDuplicadoError(ValueError):
    """Ya existe un cliente con ese nombre (docs/AJUSTES_V1.1.md, etapa 4:
    a diferencia del CUIT, esta validación bloquea)."""


class UltimaSucursalActivaError(ValueError):
    """No se puede desactivar: dejaría al cliente sin ninguna sucursal
    activa (docs/AJUSTES_V1.1.md, etapa 4)."""


def alta_cliente(
    conexion: sqlite3.Connection,
    nombre: str,
    cuit: str | None = None,
    telefono: str | None = None,
    direccion: str | None = None,
    localidad: str | None = None,
    descuento_default: Decimal = Decimal("0"),
    con_iva_default: bool = True,
    es_particular: bool = False,
    sucursales: list[str] | None = None,
) -> int:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre del cliente es obligatorio.")
    if datos.obtener_cliente_por_nombre(conexion, nombre) is not None:
        raise NombreDuplicadoError(f"Ya existe un cliente llamado '{nombre}'.")

    cliente_id = datos.insertar_cliente(
        conexion,
        nombre,
        cuit,
        telefono,
        direccion,
        localidad,
        descuento_default,
        con_iva_default,
        es_particular,
    )

    for nombre_sucursal in (sucursales or [SUCURSAL_POR_DEFECTO]):
        datos.insertar_sucursal(conexion, cliente_id, nombre_sucursal)

    conexion.commit()
    return cliente_id


def editar_cliente(conexion: sqlite3.Connection, cliente_id: int, **campos) -> None:
    if "nombre" in campos:
        nombre = campos["nombre"].strip()
        if not nombre:
            raise ValueError("El nombre del cliente es obligatorio.")
        campos["nombre"] = nombre

        existente = datos.obtener_cliente_por_nombre(conexion, nombre)
        if existente is not None and existente["id"] != cliente_id:
            raise NombreDuplicadoError(f"Ya existe un cliente llamado '{nombre}'.")

    if datos.obtener_cliente(conexion, cliente_id) is None:
        raise ValueError(f"No existe el cliente {cliente_id}.")

    datos.actualizar_cliente(conexion, cliente_id, campos)
    conexion.commit()


def baja_logica_cliente(conexion: sqlite3.Connection, cliente_id: int) -> None:
    if datos.obtener_cliente(conexion, cliente_id) is None:
        raise ValueError(f"No existe el cliente {cliente_id}.")

    datos.marcar_cliente_activo(conexion, cliente_id, activo=False)
    conexion.commit()


def reactivar_cliente(conexion: sqlite3.Connection, cliente_id: int) -> None:
    if datos.obtener_cliente(conexion, cliente_id) is None:
        raise ValueError(f"No existe el cliente {cliente_id}.")

    datos.marcar_cliente_activo(conexion, cliente_id, activo=True)
    conexion.commit()


def alta_sucursal(conexion: sqlite3.Connection, cliente_id: int, nombre: str) -> int:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre de la sucursal es obligatorio.")
    if datos.obtener_cliente(conexion, cliente_id) is None:
        raise ValueError(f"No existe el cliente {cliente_id}.")

    sucursal_id = datos.insertar_sucursal(conexion, cliente_id, nombre)
    conexion.commit()
    return sucursal_id


def editar_sucursal(conexion: sqlite3.Connection, sucursal_id: int, nombre: str) -> None:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre de la sucursal es obligatorio.")

    datos.actualizar_sucursal(conexion, sucursal_id, nombre)
    conexion.commit()


def desactivar_sucursal(conexion: sqlite3.Connection, sucursal_id: int) -> None:
    sucursal = datos.obtener_sucursal(conexion, sucursal_id)
    if sucursal is None:
        raise ValueError(f"No existe la sucursal {sucursal_id}.")

    if datos.contar_sucursales_activas(conexion, sucursal["cliente_id"]) <= 1:
        raise UltimaSucursalActivaError(
            "No se puede desactivar: el cliente quedaría sin ninguna sucursal activa."
        )

    datos.marcar_sucursal_activa(conexion, sucursal_id, activo=False)
    conexion.commit()


def reactivar_sucursal(conexion: sqlite3.Connection, sucursal_id: int) -> None:
    if datos.obtener_sucursal(conexion, sucursal_id) is None:
        raise ValueError(f"No existe la sucursal {sucursal_id}.")

    datos.marcar_sucursal_activa(conexion, sucursal_id, activo=True)
    conexion.commit()
