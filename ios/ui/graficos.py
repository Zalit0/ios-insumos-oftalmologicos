"""Armado común de los gráficos de IOS con QtCharts (docs/AJUSTES_V1.1.md,
etapa 6.3, D5): solo dibujan los valores que reciben, sin calcular nada.
Barras agrupadas, barras horizontales y líneas; nunca torta."""

from __future__ import annotations

from decimal import Decimal
from typing import Callable

from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QHorizontalBarSeries,
    QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QPainter
from PySide6.QtWidgets import QToolTip


def _chart_view(chart: QChart) -> QChartView:
    chart.legend().setVisible(True)
    vista = QChartView(chart)
    vista.setRenderHint(QPainter.Antialiasing)
    vista.setMinimumHeight(260)
    return vista


def grafico_barras_agrupadas(
    titulo: str,
    categorias: list[str],
    series_nombre_valores: list[tuple[str, list[Decimal]]],
    titulo_eje_x: str,
    titulo_eje_y: str,
) -> QChartView:
    """Una barra por serie en cada categoría, lado a lado (docs: "barras
    agrupadas"). ``series_nombre_valores`` es [(nombre, valores), ...]."""
    chart = QChart()
    chart.setTitle(titulo)

    # QBarSeries agrupa lado a lado por defecto (distinto de QStackedBarSeries).
    serie = QBarSeries()
    for nombre, valores in series_nombre_valores:
        conjunto = QBarSet(nombre)
        for valor in valores:
            conjunto.append(float(valor))
        serie.append(conjunto)
    chart.addSeries(serie)

    eje_x = QBarCategoryAxis()
    eje_x.append(categorias)
    eje_x.setTitleText(titulo_eje_x)
    chart.addAxis(eje_x, Qt.AlignBottom)
    serie.attachAxis(eje_x)

    eje_y = QValueAxis()
    eje_y.setTitleText(titulo_eje_y)
    eje_y.setLabelFormat("%.0f")
    chart.addAxis(eje_y, Qt.AlignLeft)
    serie.attachAxis(eje_y)

    return _chart_view(chart)


def grafico_linea(
    titulo: str,
    categorias: list[str],
    nombre_serie: str,
    valores: list[Decimal],
    titulo_eje_x: str,
    titulo_eje_y: str,
) -> QChartView:
    chart = QChart()
    chart.setTitle(titulo)

    serie = QLineSeries()
    serie.setName(nombre_serie)
    for indice, valor in enumerate(valores):
        serie.append(indice, float(valor))
    chart.addSeries(serie)

    eje_x = QBarCategoryAxis()
    eje_x.append(categorias)
    eje_x.setTitleText(titulo_eje_x)
    chart.addAxis(eje_x, Qt.AlignBottom)
    serie.attachAxis(eje_x)

    eje_y = QValueAxis()
    eje_y.setTitleText(titulo_eje_y)
    eje_y.setLabelFormat("%.0f")
    chart.addAxis(eje_y, Qt.AlignLeft)
    serie.attachAxis(eje_y)

    return _chart_view(chart)


def grafico_lineas_multiples(
    titulo: str,
    categorias: list[str],
    series_nombre_valores: list[tuple[str, list[Decimal]]],
    titulo_eje_x: str,
    titulo_eje_y: str,
    formateador_valor: Callable[[Decimal], str] | None = None,
) -> QChartView:
    """Varias series de línea en el mismo gráfico (p. ej. venta y
    cobranza), con tooltip al pasar el mouse mostrando el valor exacto."""
    chart = QChart()
    chart.setTitle(titulo)

    eje_x = QBarCategoryAxis()
    eje_x.append(categorias)
    eje_x.setTitleText(titulo_eje_x)
    eje_y = QValueAxis()
    eje_y.setTitleText(titulo_eje_y)
    eje_y.setLabelFormat("%.0f")
    chart.addAxis(eje_x, Qt.AlignBottom)
    chart.addAxis(eje_y, Qt.AlignLeft)

    for nombre, valores in series_nombre_valores:
        serie = QLineSeries()
        serie.setName(nombre)
        serie.setPointsVisible(True)
        for indice, valor in enumerate(valores):
            serie.append(indice, float(valor))
        chart.addSeries(serie)
        serie.attachAxis(eje_x)
        serie.attachAxis(eje_y)

        def _al_pasar_mouse(punto, estado, nombre_serie=nombre, valores_serie=valores):
            if not estado:
                return
            indice = round(punto.x())
            if 0 <= indice < len(valores_serie):
                valor = valores_serie[indice]
                texto = formateador_valor(valor) if formateador_valor else f"{valor:.2f}"
                QToolTip.showText(QCursor.pos(), f"{nombre_serie}: {texto}")

        serie.hovered.connect(_al_pasar_mouse)

    return _chart_view(chart)


def grafico_barras_horizontales(
    titulo: str,
    categorias: list[str],
    nombre_serie: str,
    valores: list[Decimal],
    titulo_eje_x: str,
    titulo_eje_y: str,
) -> QChartView:
    chart = QChart()
    chart.setTitle(titulo)

    conjunto = QBarSet(nombre_serie)
    for valor in valores:
        conjunto.append(float(valor))
    serie = QHorizontalBarSeries()
    serie.append(conjunto)
    chart.addSeries(serie)

    eje_y = QBarCategoryAxis()
    eje_y.append(categorias)
    eje_y.setTitleText(titulo_eje_y)
    chart.addAxis(eje_y, Qt.AlignLeft)
    serie.attachAxis(eje_y)

    eje_x = QValueAxis()
    eje_x.setTitleText(titulo_eje_x)
    eje_x.setLabelFormat("%.0f")
    chart.addAxis(eje_x, Qt.AlignBottom)
    serie.attachAxis(eje_x)

    return _chart_view(chart)
