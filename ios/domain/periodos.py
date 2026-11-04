"""Períodos y comparaciones temporales para el Dashboard directivo
(docs/AJUSTES_V1.1.md, rediseño del Dashboard). Solo fechas y porcentajes,
sin acceso a base de datos: la pantalla solo pide un período y compara.

Las comparaciones usan el mismo rango de días calendario en el período
anterior (nunca el mes anterior completo contra lo transcurrido del mes
actual, que da una comparación inválida)."""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import NamedTuple


class Periodo(NamedTuple):
    desde: str
    hasta: str


class MesRango(NamedTuple):
    mes: str
    desde: str
    hasta: str


class Variacion(NamedTuple):
    monto: Decimal
    porcentaje: Decimal | None  # None si no es matemáticamente válido (valor anterior cero)


def _sumar_meses(anio: int, mes: int, delta: int) -> tuple[int, int]:
    indice = anio * 12 + (mes - 1) + delta
    anio_resultado, mes_cero = divmod(indice, 12)
    return anio_resultado, mes_cero + 1


def _dia_valido_del_mes(anio: int, mes: int, dia: int) -> date:
    """``dia`` recortado al último día de ``anio``-``mes`` si ese mes es más
    corto (31 de octubre → 28 o 29 de febrero; respeta años bisiestos)."""
    ultimo_dia = monthrange(anio, mes)[1]
    return date(anio, mes, min(dia, ultimo_dia))


def _mismo_dia_otro_mes(fecha: date, anio: int, mes: int) -> date:
    return _dia_valido_del_mes(anio, mes, fecha.day)


def periodo_mes_actual(fecha_hasta: date) -> Periodo:
    """Del 1° del mes de ``fecha_hasta`` hasta ``fecha_hasta`` inclusive."""
    return Periodo(date(fecha_hasta.year, fecha_hasta.month, 1).isoformat(), fecha_hasta.isoformat())


def periodo_mismo_rango_mes_anterior(fecha_hasta: date) -> Periodo:
    """Mismo rango de días calendario (del 1° al mismo día) pero del mes
    anterior: si hoy es 20/10, compara contra 01/09 al 20/09, nunca contra
    septiembre completo."""
    anio, mes = _sumar_meses(fecha_hasta.year, fecha_hasta.month, -1)
    hasta = _mismo_dia_otro_mes(fecha_hasta, anio, mes)
    return Periodo(date(anio, mes, 1).isoformat(), hasta.isoformat())


def periodo_mismo_rango_anio_anterior(fecha_hasta: date) -> Periodo:
    """Mismo rango de días calendario pero del año anterior (respeta el 29
    de febrero de un año bisiesto comparado contra uno que no lo es)."""
    anio_anterior = fecha_hasta.year - 1
    hasta = _mismo_dia_otro_mes(fecha_hasta, anio_anterior, fecha_hasta.month)
    return Periodo(date(anio_anterior, fecha_hasta.month, 1).isoformat(), hasta.isoformat())


def periodo_ultimo_mes_cerrado(fecha_hoy: date) -> Periodo:
    """El mes calendario anterior completo (si hoy es cualquier día de
    octubre, es septiembre completo)."""
    anio, mes = _sumar_meses(fecha_hoy.year, fecha_hoy.month, -1)
    ultimo_dia = monthrange(anio, mes)[1]
    return Periodo(date(anio, mes, 1).isoformat(), date(anio, mes, ultimo_dia).isoformat())


def periodo_mismo_rango_anio_anterior_de(periodo: Periodo) -> Periodo:
    """El mismo rango de ``periodo``, un año antes (para comparar, por
    ejemplo, el último mes cerrado contra el mismo mes del año anterior)."""
    desde = date.fromisoformat(periodo.desde)
    hasta = date.fromisoformat(periodo.hasta)
    desde_anterior = _mismo_dia_otro_mes(desde, desde.year - 1, desde.month)
    hasta_anterior = _mismo_dia_otro_mes(hasta, hasta.year - 1, hasta.month)
    return Periodo(desde_anterior.isoformat(), hasta_anterior.isoformat())


def ultimos_n_meses(fecha_hasta: date, n: int = 12) -> list[MesRango]:
    """Los ``n`` meses calendario completos hasta el de ``fecha_hasta``
    inclusive, en orden cronológico, cada uno con su rango de fechas
    (para acotar las consultas, en vez de traer todo el historial)."""
    indice_0 = fecha_hasta.year * 12 + (fecha_hasta.month - 1)
    resultado = []
    for i in range(n - 1, -1, -1):
        anio, mes_cero = divmod(indice_0 - i, 12)
        mes = mes_cero + 1
        ultimo_dia = monthrange(anio, mes)[1]
        resultado.append(MesRango(
            mes=f"{anio}-{mes:02d}",
            desde=date(anio, mes, 1).isoformat(),
            hasta=date(anio, mes, ultimo_dia).isoformat(),
        ))
    return resultado


def calcular_variacion(actual: Decimal, anterior: Decimal) -> Variacion:
    """monto = actual − anterior; porcentaje = monto / anterior × 100, o
    ``None`` si ``anterior`` es cero (no hay base válida para un
    porcentaje: mostrar un estado descriptivo, nunca uno engañoso)."""
    monto = actual - anterior
    if anterior == 0:
        return Variacion(monto=monto, porcentaje=None)
    return Variacion(monto=monto, porcentaje=(monto / anterior) * Decimal(100))
