"""Formato de moneda y fecha en los reportes (es-AR: punto de miles,
coma decimal; fecha dd/mm/aaaa)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal


def formato_moneda(valor: Decimal, decimales: int = 2) -> str:
    entero_y_decimal = f"{valor:,.{decimales}f}"
    parte_entera, _, parte_decimal = entero_y_decimal.partition(".")
    parte_entera = parte_entera.replace(",", ".")
    if not parte_decimal:
        return f"$ {parte_entera}"
    return f"$ {parte_entera},{parte_decimal}"


def formato_fecha(valor: str | date | datetime) -> str:
    if isinstance(valor, str):
        valor = date.fromisoformat(valor[:10])
    elif isinstance(valor, datetime):
        valor = valor.date()
    return valor.strftime("%d/%m/%Y")


def formato_porcentaje(valor: Decimal) -> str:
    texto = f"{valor:f}".rstrip("0").rstrip(".")
    return f"{texto or '0'}%"
