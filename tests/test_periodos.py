"""Períodos y comparaciones temporales del Dashboard
(docs/AJUSTES_V1.1.md, rediseño del Dashboard)."""

from datetime import date
from decimal import Decimal

from ios.domain.periodos import (
    Periodo,
    calcular_variacion,
    periodo_mes_actual,
    periodo_mismo_rango_anio_anterior,
    periodo_mismo_rango_anio_anterior_de,
    periodo_mismo_rango_mes_anterior,
    periodo_ultimo_mes_cerrado,
    ultimos_n_meses,
)


def test_periodo_mes_actual():
    assert periodo_mes_actual(date(2026, 10, 20)) == Periodo("2026-10-01", "2026-10-20")


def test_mismo_rango_mes_anterior_mismo_dia():
    assert periodo_mismo_rango_mes_anterior(date(2026, 10, 20)) == Periodo("2026-09-01", "2026-09-20")


def test_mismo_rango_mes_anterior_recorta_si_el_mes_anterior_es_mas_corto():
    # 31 de octubre: septiembre solo tiene 30 días.
    assert periodo_mismo_rango_mes_anterior(date(2026, 10, 31)) == Periodo("2026-09-01", "2026-09-30")


def test_mismo_rango_mes_anterior_cambia_de_anio():
    assert periodo_mismo_rango_mes_anterior(date(2026, 1, 15)) == Periodo("2025-12-01", "2025-12-15")


def test_mismo_rango_mes_anterior_recorta_febrero_no_bisiesto():
    # 31 de marzo de 2026 (no bisiesto): febrero 2026 solo tiene 28 días.
    assert periodo_mismo_rango_mes_anterior(date(2026, 3, 31)) == Periodo("2026-02-01", "2026-02-28")


def test_mismo_rango_anio_anterior():
    assert periodo_mismo_rango_anio_anterior(date(2026, 10, 20)) == Periodo("2025-10-01", "2025-10-20")


def test_mismo_rango_anio_anterior_29_de_febrero_bisiesto_contra_no_bisiesto():
    # 2028 es bisiesto; 2027 no lo es: el 29/02 se recorta a 28/02.
    assert periodo_mismo_rango_anio_anterior(date(2028, 2, 29)) == Periodo("2027-02-01", "2027-02-28")


def test_ultimo_mes_cerrado():
    assert periodo_ultimo_mes_cerrado(date(2026, 10, 5)) == Periodo("2026-09-01", "2026-09-30")


def test_ultimo_mes_cerrado_cambia_de_anio():
    assert periodo_ultimo_mes_cerrado(date(2026, 1, 15)) == Periodo("2025-12-01", "2025-12-31")


def test_mismo_rango_anio_anterior_de_un_periodo():
    periodo = Periodo("2026-09-01", "2026-09-30")
    assert periodo_mismo_rango_anio_anterior_de(periodo) == Periodo("2025-09-01", "2025-09-30")


def test_mismo_rango_anio_anterior_de_febrero_bisiesto():
    periodo = Periodo("2028-02-01", "2028-02-29")
    assert periodo_mismo_rango_anio_anterior_de(periodo) == Periodo("2027-02-01", "2027-02-28")


def test_ultimos_n_meses_en_orden_cronologico_y_cambia_de_anio():
    meses = ultimos_n_meses(date(2026, 2, 15), n=3)
    assert [m.mes for m in meses] == ["2025-12", "2026-01", "2026-02"]
    assert meses[0] == ("2025-12", "2025-12-01", "2025-12-31")
    # Febrero de 2026 (no bisiesto): último día 28.
    assert meses[-1] == ("2026-02", "2026-02-01", "2026-02-28")


def test_ultimos_n_meses_respeta_anio_bisiesto():
    meses = ultimos_n_meses(date(2028, 2, 10), n=1)
    assert meses[0] == ("2028-02", "2028-02-01", "2028-02-29")


def test_calcular_variacion_positiva():
    variacion = calcular_variacion(Decimal("1200"), Decimal("1000"))
    assert variacion.monto == Decimal("200")
    assert variacion.porcentaje == Decimal("20")


def test_calcular_variacion_negativa():
    variacion = calcular_variacion(Decimal("800"), Decimal("1000"))
    assert variacion.monto == Decimal("-200")
    assert variacion.porcentaje == Decimal("-20")


def test_calcular_variacion_sin_base_valida_cuando_el_anterior_es_cero():
    variacion = calcular_variacion(Decimal("500"), Decimal("0"))
    assert variacion.monto == Decimal("500")
    assert variacion.porcentaje is None


def test_calcular_variacion_ambos_en_cero():
    variacion = calcular_variacion(Decimal("0"), Decimal("0"))
    assert variacion.monto == Decimal("0")
    assert variacion.porcentaje is None
