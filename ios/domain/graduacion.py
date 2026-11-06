"""Graduación oftálmica (esférico/cilíndrico) como texto, para guardar en
una columna ``graduacion`` (TEXT) sin agregar columnas nuevas (plan de
detalle de comprobantes). Usado tanto por el detalle de un comprobante
como por una línea especial de pedido a proveedor, para que se vea y se
cargue siempre igual."""

from __future__ import annotations

import re
from decimal import Decimal

_PATRON_GRADUACION = re.compile(
    r"ESF\s*([+-]?\d+(?:\.\d+)?)\s*CIL\s*([+-]?\d+(?:\.\d+)?)", re.IGNORECASE
)


def formatear_graduacion(esferico: Decimal, cilindrico: Decimal) -> str:
    """"Neutro" si ambos son 0 (valor explícito, nunca vacío); si no,
    "ESF +1.25 CIL -0.50", siempre con el signo."""
    if esferico == 0 and cilindrico == 0:
        return "Neutro"
    return f"ESF {esferico:+.2f} CIL {cilindrico:+.2f}"


def parsear_graduacion(texto: str) -> tuple[Decimal, Decimal]:
    """Inverso de ``formatear_graduacion``, para recargar una graduación ya
    guardada en los campos de esférico/cilíndrico. Si no matchea el
    formato (texto libre viejo, o "Neutro"), devuelve (0, 0)."""
    coincidencia = _PATRON_GRADUACION.search(texto or "")
    if not coincidencia:
        return Decimal("0"), Decimal("0")
    return Decimal(coincidencia.group(1)), Decimal(coincidencia.group(2))
