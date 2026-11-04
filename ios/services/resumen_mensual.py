"""Resumen de un mes elegido, equivalente a la hoja TOTALES del Excel
(docs/PLAN.md, etapa 8). ``mes`` siempre en formato 'YYYY-MM'."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from ios.data import configuracion as datos_configuracion
from ios.data import resumen_mensual as datos
from ios.domain.calculos import TotalesMes, calcular_totales_mes
from ios.services.caja import total_disponible


def resumen_del_mes(conexion: sqlite3.Connection, mes: str) -> TotalesMes:
    comision_pct = datos_configuracion.obtener_configuracion(conexion)["comision_pct"]

    return calcular_totales_mes(
        montos_finales_vigentes=datos.montos_finales_vigentes_del_mes(conexion, mes),
        montos_aplicados_a_remitos_del_mes=datos.montos_aplicados_a_comprobantes_del_mes(
            conexion, mes
        ),
        ivas_venta_vigentes=datos.ivas_venta_vigentes_del_mes(conexion, mes),
        ivas_compra=datos.ivas_compra_del_mes(conexion, mes),
        montos_compras=datos.montos_compras_del_mes(conexion, mes),
        montos_pagos_proveedor=datos.montos_pagos_proveedor_del_mes(conexion, mes),
        comision_pct=comision_pct,
    )


def total_disponible_actual(conexion: sqlite3.Connection) -> Decimal:
    formas_pago_ids = [
        fila["id"] for fila in conexion.execute("SELECT id FROM formas_pago WHERE activo = 1")
    ]
    return total_disponible(conexion, formas_pago_ids)
