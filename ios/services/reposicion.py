"""Reporte de reposición: cuánto se vendió de cada tipo de cristal de stock
reponible, por graduación, en un rango de fechas — la base del pedido a
proveedor que arma el módulo de pedidos (plan de detalle de comprobantes,
etapa 3/4/5.2).

Cada renglón de venta que entra en un pedido de reposición hay que
marcarlo (``marcar_reposicion_generada``), para que si más tarde se genera
otra reposición con un rango de fechas que se superpone con este, esa
venta no se cuente dos veces."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from ios.data import detalle_comprobante as datos_detalle


@dataclass
class ItemReposicion:
    tipo_cristal_id: int
    nombre: str
    graduacion: str
    cantidad_vendida: int
    detalle_ids: list[int] = field(default_factory=list)


def reporte_reposicion(
    conexion: sqlite3.Connection, fecha_desde: str, fecha_hasta: str
) -> list[ItemReposicion]:
    filas = datos_detalle.detalle_pendiente_de_reposicion(conexion, fecha_desde, fecha_hasta)
    agrupado: dict[tuple[int, str], ItemReposicion] = {}
    for fila in filas:
        clave = (fila["tipo_cristal_id"], fila["graduacion"])
        if clave not in agrupado:
            agrupado[clave] = ItemReposicion(
                tipo_cristal_id=fila["tipo_cristal_id"], nombre=fila["nombre"],
                graduacion=fila["graduacion"], cantidad_vendida=0,
            )
        item = agrupado[clave]
        item.cantidad_vendida += fila["cantidad"]
        item.detalle_ids.append(fila["id"])
    return list(agrupado.values())


def marcar_reposicion_generada(conexion: sqlite3.Connection, item: ItemReposicion) -> None:
    """Marca los renglones de venta que formaron este ítem como ya
    incluidos en un pedido de reposición — se llama se haya terminado
    pidiendo la cantidad completa o no (p. ej. si una compensación por
    devolución la dejó en cero), porque de cualquier forma ya se tuvieron
    en cuenta."""
    datos_detalle.marcar_incluido_en_reposicion(conexion, item.detalle_ids)
