"""Casos de uso de categorías de caja (gastos, retiros, aportes...)."""

from __future__ import annotations

import sqlite3

from ios.data import categorias_caja as datos

TIPOS_VALIDOS = {"ingreso", "egreso"}


def alta_categoria(conexion: sqlite3.Connection, nombre: str, tipo: str) -> int:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre de la categoría es obligatorio.")
    if tipo not in TIPOS_VALIDOS:
        raise ValueError(f"El tipo de categoría debe ser 'ingreso' o 'egreso', no '{tipo}'.")

    categoria_id = datos.insertar_categoria(conexion, nombre, tipo)
    conexion.commit()
    return categoria_id


def editar_categoria(conexion: sqlite3.Connection, categoria_id: int, **campos) -> None:
    if datos.obtener_categoria(conexion, categoria_id) is None:
        raise ValueError(f"No existe la categoría {categoria_id}.")

    datos.actualizar_categoria(conexion, categoria_id, campos)
    conexion.commit()


def baja_logica_categoria(conexion: sqlite3.Connection, categoria_id: int) -> None:
    editar_categoria(conexion, categoria_id, activo=0)
