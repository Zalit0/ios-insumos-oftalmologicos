"""Casos de uso de proveedores (docs/PLAN.md, etapa 6)."""

from __future__ import annotations

import sqlite3

from ios.data import proveedores as datos


def alta_proveedor(conexion: sqlite3.Connection, nombre: str, cuit: str | None = None) -> int:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre del proveedor es obligatorio.")

    proveedor_id = datos.insertar_proveedor(conexion, nombre, cuit)
    conexion.commit()
    return proveedor_id


def editar_proveedor(conexion: sqlite3.Connection, proveedor_id: int, **campos) -> None:
    if "nombre" in campos and not campos["nombre"].strip():
        raise ValueError("El nombre del proveedor es obligatorio.")
    if datos.obtener_proveedor(conexion, proveedor_id) is None:
        raise ValueError(f"No existe el proveedor {proveedor_id}.")

    datos.actualizar_proveedor(conexion, proveedor_id, campos)
    conexion.commit()
