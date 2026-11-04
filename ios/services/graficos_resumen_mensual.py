"""Datos para los gráficos de la pestaña "Gráficos" del Resumen mensual
(docs/AJUSTES_V1.1.md, etapa 6.3, D5). Los gráficos solo dibujan: todo el
cálculo vive acá, con pruebas."""

from __future__ import annotations

import sqlite3
from calendar import monthrange
from dataclasses import dataclass
from decimal import Decimal

from ios.data import resumen_mensual as datos_resumen
from ios.domain.calculos import calcular_deuda_total
from ios.services.compras_por_cliente import ranking_todos_los_clientes
from ios.services.gastos_caja_chica import SubtotalCategoria, gastos_de_caja_chica
from ios.services.resumen_mensual import resumen_del_mes


def ultimos_n_meses(mes_referencia: str, n: int = 12) -> list[str]:
    """``mes_referencia`` en 'YYYY-MM'; devuelve los ``n`` meses hasta
    ese incluido, en orden cronológico."""
    anio, mes = (int(parte) for parte in mes_referencia.split("-"))
    indice_mes_0 = anio * 12 + (mes - 1)
    return [
        f"{divmod(indice_mes_0 - i, 12)[0]}-{divmod(indice_mes_0 - i, 12)[1] + 1:02d}"
        for i in range(n - 1, -1, -1)
    ]


def primer_dia_del_mes(mes: str) -> str:
    return f"{mes}-01"


def ultimo_dia_del_mes(mes: str) -> str:
    anio, mes_num = (int(parte) for parte in mes.split("-"))
    ultimo = monthrange(anio, mes_num)[1]
    return f"{mes}-{ultimo:02d}"


@dataclass
class PuntoVentaCobranza:
    mes: str
    venta: Decimal
    cobranza: Decimal


def venta_vs_cobranza_12_meses(
    conexion: sqlite3.Connection, mes_referencia: str
) -> list[PuntoVentaCobranza]:
    return [
        PuntoVentaCobranza(mes=mes, venta=resumen.total_venta, cobranza=resumen.total_pagos)
        for mes, resumen in (
            (mes, resumen_del_mes(conexion, mes)) for mes in ultimos_n_meses(mes_referencia)
        )
    ]


@dataclass
class PuntoDeuda:
    mes: str
    deuda: Decimal


def deuda_total_12_meses(conexion: sqlite3.Connection, mes_referencia: str) -> list[PuntoDeuda]:
    puntos = []
    for mes in ultimos_n_meses(mes_referencia):
        fecha_corte = ultimo_dia_del_mes(mes)
        total_monto_final = sum(
            datos_resumen.montos_finales_vigentes_hasta(conexion, fecha_corte), Decimal(0)
        )
        total_recibos = sum(
            datos_resumen.montos_recibos_vigentes_hasta(conexion, fecha_corte), Decimal(0)
        )
        puntos.append(PuntoDeuda(mes=mes, deuda=calcular_deuda_total(total_monto_final, total_recibos)))
    return puntos


@dataclass
class PuntoCliente:
    nombre: str
    total_final: Decimal


def top_clientes_del_mes(conexion: sqlite3.Connection, mes: str, top: int = 10) -> list[PuntoCliente]:
    ranking = ranking_todos_los_clientes(conexion, primer_dia_del_mes(mes), ultimo_dia_del_mes(mes))
    return [PuntoCliente(nombre=f.nombre, total_final=f.total_final) for f in ranking[:top]]


@dataclass
class PuntoIva:
    mes: str
    iva_venta: Decimal
    iva_compra: Decimal


def iva_venta_vs_compra_12_meses(conexion: sqlite3.Connection, mes_referencia: str) -> list[PuntoIva]:
    return [
        PuntoIva(mes=mes, iva_venta=resumen.iva_venta, iva_compra=resumen.iva_compra)
        for mes, resumen in (
            (mes, resumen_del_mes(conexion, mes)) for mes in ultimos_n_meses(mes_referencia)
        )
    ]


def egresos_del_mes_por_categoria(conexion: sqlite3.Connection, mes: str) -> list[SubtotalCategoria]:
    resultado = gastos_de_caja_chica(conexion, primer_dia_del_mes(mes), ultimo_dia_del_mes(mes))
    return sorted(resultado.subtotales_por_categoria, key=lambda s: s.monto, reverse=True)
