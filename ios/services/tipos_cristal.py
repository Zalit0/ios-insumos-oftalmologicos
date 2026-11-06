"""Casos de uso del catálogo de tipos de cristal (plan de detalle de
comprobantes, etapa 1)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from ios.data import tipos_cristal as datos

VENDIDO_POR_VALIDOS = {"par", "unidad"}


def alta_tipo_cristal(
    conexion: sqlite3.Connection,
    nombre: str,
    precio_lista: Decimal,
    categoria: str | None = None,
    vendido_por: str = "par",
    requiere_graduacion: bool = True,
    reponible: bool = True,
) -> int:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre del tipo de cristal es obligatorio.")
    if vendido_por not in VENDIDO_POR_VALIDOS:
        raise ValueError(f"'vendido_por' tiene que ser 'par' o 'unidad', no {vendido_por!r}.")
    if precio_lista < 0:
        raise ValueError("El precio de lista no puede ser negativo.")

    categoria = categoria.strip() if categoria else None
    tipo_id = datos.insertar_tipo_cristal(
        conexion, nombre, precio_lista, categoria, vendido_por,
        requiere_graduacion, reponible,
    )
    conexion.commit()
    return tipo_id


def editar_tipo_cristal(conexion: sqlite3.Connection, tipo_id: int, **campos) -> None:
    if datos.obtener_tipo_cristal(conexion, tipo_id) is None:
        raise ValueError(f"No existe el tipo de cristal {tipo_id}.")
    if "vendido_por" in campos and campos["vendido_por"] not in VENDIDO_POR_VALIDOS:
        raise ValueError(
            f"'vendido_por' tiene que ser 'par' o 'unidad', no {campos['vendido_por']!r}."
        )
    if "precio_lista" in campos and campos["precio_lista"] < 0:
        raise ValueError("El precio de lista no puede ser negativo.")

    datos.actualizar_tipo_cristal(conexion, tipo_id, campos)
    conexion.commit()


def baja_logica_tipo_cristal(conexion: sqlite3.Connection, tipo_id: int) -> None:
    editar_tipo_cristal(conexion, tipo_id, activo=0)


def precio_unitario(tipo_cristal: sqlite3.Row) -> Decimal:
    """Precio de una sola unidad (un lente): la mitad del precio de lista si
    se vende por par (medio par = 1 unidad), o el precio de lista directo si
    se vende por unidad (accesorios, p. ej. pegatinas)."""
    if tipo_cristal["vendido_por"] == "par":
        return tipo_cristal["precio_lista"] / 2
    return tipo_cristal["precio_lista"]
