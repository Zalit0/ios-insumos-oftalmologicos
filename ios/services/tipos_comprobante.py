"""Casos de uso de tipos de comprobante (configurable; viene cargado RTO)."""

from __future__ import annotations

import sqlite3

from ios.data import tipos_comprobante as datos


def alta_tipo_comprobante(conexion: sqlite3.Connection, nombre: str, abreviatura: str) -> int:
    nombre = nombre.strip()
    abreviatura = abreviatura.strip()
    if not nombre or not abreviatura:
        raise ValueError("El nombre y la abreviatura del tipo de comprobante son obligatorios.")

    tipo_id = datos.insertar_tipo_comprobante(conexion, nombre, abreviatura)
    conexion.commit()
    return tipo_id


def editar_tipo_comprobante(conexion: sqlite3.Connection, tipo_id: int, **campos) -> None:
    if datos.obtener_tipo_comprobante(conexion, tipo_id) is None:
        raise ValueError(f"No existe el tipo de comprobante {tipo_id}.")

    datos.actualizar_tipo_comprobante(conexion, tipo_id, campos)
    conexion.commit()


def baja_logica_tipo_comprobante(conexion: sqlite3.Connection, tipo_id: int) -> None:
    editar_tipo_comprobante(conexion, tipo_id, activo=0)
