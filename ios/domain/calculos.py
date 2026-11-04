"""Cálculos puros de IOS (docs/PLAN.md, "Reglas de negocio y fórmulas").

Sin acceso a base de datos ni a la interfaz: todo son funciones que reciben
``Decimal`` (u otros valores simples) y devuelven ``Decimal``. La pantalla
muestra resultados, no calcula.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, NamedTuple


def cuantizar(valor: Decimal, decimales: int) -> Decimal:
    """Redondea ``valor`` a ``decimales`` posiciones (redondeo comercial)."""
    exponente = Decimal(1).scaleb(-decimales)
    return valor.quantize(exponente, rounding=ROUND_HALF_UP)


def calcular_monto_final(
    monto_lista: Decimal, descuento_pct: Decimal, decimales: int
) -> Decimal:
    """monto_lista × (1 − descuento / 100), redondeado."""
    factor = (Decimal(100) - descuento_pct) / Decimal(100)
    return cuantizar(monto_lista * factor, decimales)


def calcular_iva_discriminado(
    monto_final: Decimal, con_iva: bool, tasa_iva_pct: Decimal, decimales: int
) -> Decimal:
    """monto_final × tasa / (100 + tasa) si con_iva, si no 0. Redondeado."""
    if not con_iva:
        return cuantizar(Decimal(0), decimales)
    iva = monto_final * tasa_iva_pct / (Decimal(100) + tasa_iva_pct)
    return cuantizar(iva, decimales)


def calcular_saldo_comprobante(monto_final: Decimal, total_aplicado: Decimal) -> Decimal:
    """monto_final − suma de montos aplicados desde recibos."""
    return monto_final - total_aplicado


def calcular_saldo_a_favor(total_recibos_vigentes: Decimal, total_aplicado: Decimal) -> Decimal:
    """Monto de recibos vigentes del cliente − montos que ya aplicó a remitos."""
    return total_recibos_vigentes - total_aplicado


def calcular_saldo_cliente(
    saldos_comprobantes: Iterable[Decimal], saldo_a_favor: Decimal
) -> Decimal:
    """Suma de saldos de comprobantes vigentes (todas las sucursales) − saldo a favor.

    Si el resultado es negativo, el cliente tiene saldo a favor.
    """
    return sum(saldos_comprobantes, Decimal(0)) - saldo_a_favor


def calcular_deuda_total(
    total_monto_final_vigente: Decimal, total_recibos_vigentes: Decimal
) -> Decimal:
    """Deuda total de todos los clientes a una fecha: total facturado
    vigente menos total cobrado (recibos vigentes), sin importar a qué
    comprobante se aplicó cada recibo (docs/AJUSTES_V1.1.md, etapa 6.3).

    Equivale a sumar el saldo consolidado de todos los clientes: el monto
    aplicado se cancela entre el saldo de cada comprobante y el saldo a
    favor, así que solo quedan estos dos totales.
    """
    return total_monto_final_vigente - total_recibos_vigentes


class TotalesMes(NamedTuple):
    total_venta: Decimal
    total_pagos: Decimal
    total_saldos: Decimal
    iva_venta: Decimal
    iva_compra: Decimal
    iva_deuda: Decimal
    comision: Decimal
    total_compras: Decimal
    depositos: Decimal
    ganancia_teorica: Decimal


def calcular_totales_mes(
    montos_finales_vigentes: Iterable[Decimal],
    montos_aplicados_a_remitos_del_mes: Iterable[Decimal],
    ivas_venta_vigentes: Iterable[Decimal],
    ivas_compra: Iterable[Decimal],
    montos_compras: Iterable[Decimal],
    montos_pagos_proveedor: Iterable[Decimal],
    comision_pct: Decimal,
) -> TotalesMes:
    """Resumen mensual (docs/PLAN.md, equivalente a la hoja TOTALES).

    ``montos_aplicados_a_remitos_del_mes`` son los montos aplicados a
    comprobantes con fecha en el mes, sin importar la fecha del recibo.
    ``montos_pagos_proveedor`` son los "depósitos" (pagos a proveedores).
    """
    total_venta = sum(montos_finales_vigentes, Decimal(0))
    total_pagos = sum(montos_aplicados_a_remitos_del_mes, Decimal(0))
    total_saldos = total_venta - total_pagos

    iva_venta = sum(ivas_venta_vigentes, Decimal(0))
    iva_compra = sum(ivas_compra, Decimal(0))
    iva_deuda = iva_venta - iva_compra

    comision = total_venta * comision_pct / Decimal(100)
    total_compras = sum(montos_compras, Decimal(0))
    depositos = sum(montos_pagos_proveedor, Decimal(0))

    ganancia_teorica = total_venta - comision - total_compras - iva_deuda

    return TotalesMes(
        total_venta=total_venta,
        total_pagos=total_pagos,
        total_saldos=total_saldos,
        iva_venta=iva_venta,
        iva_compra=iva_compra,
        iva_deuda=iva_deuda,
        comision=comision,
        total_compras=total_compras,
        depositos=depositos,
        ganancia_teorica=ganancia_teorica,
    )
