"""Pantalla Resumen mensual: equivale a la hoja TOTALES para cualquier
mes (ventas, pagos, saldos, IVA, comisión, compras, depósitos, ganancia
teórica y total disponible) (docs/PLAN.md, "Pantallas" y etapa 8)."""

from __future__ import annotations

import sqlite3
from datetime import date

from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ios.reports.formato import formato_moneda
from ios.reports.pdf_comun import abrir_pdf, ruta_pdf_automatica
from ios.reports.resumen_mensual import (
    ETIQUETAS,
    generar_excel_resumen_mensual,
    generar_pdf_resumen_mensual,
)
from ios.services.graficos_resumen_mensual import (
    deuda_total_12_meses,
    egresos_del_mes_por_categoria,
    iva_venta_vs_compra_12_meses,
    top_clientes_del_mes,
    venta_vs_cobranza_12_meses,
)
from ios.services.resumen_mensual import resumen_del_mes, total_disponible_actual
from ios.ui.graficos import grafico_barras_agrupadas, grafico_barras_horizontales, grafico_linea
from ios.ui.widgets import CampoEntero

NOMBRES_MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


class PaginaResumenMensual(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        hoy = date.today()

        layout_general = QVBoxLayout(self)

        encabezado = QHBoxLayout()
        encabezado.addWidget(QLabel("Mes"))
        self._campo_mes = QComboBox()
        for numero, nombre in enumerate(NOMBRES_MESES, start=1):
            self._campo_mes.addItem(nombre, numero)
        self._campo_mes.setCurrentIndex(hoy.month - 1)
        self._campo_mes.currentIndexChanged.connect(self._actualizar_resumen)
        encabezado.addWidget(self._campo_mes)

        self._campo_anio = CampoEntero()
        self._campo_anio.setRange(2000, 2100)
        self._campo_anio.setValue(hoy.year)
        self._campo_anio.valueChanged.connect(self._actualizar_resumen)
        encabezado.addWidget(self._campo_anio)
        encabezado.addStretch(1)

        boton_pdf = QPushButton("Exportar PDF")
        boton_pdf.clicked.connect(self._exportar_pdf)
        encabezado.addWidget(boton_pdf)
        boton_excel = QPushButton("Exportar Excel")
        boton_excel.clicked.connect(self._exportar_excel)
        encabezado.addWidget(boton_excel)

        layout_general.addLayout(encabezado)

        self._pestanas = QTabWidget()
        self._pestanas.addTab(self._crear_pestana_resumen(), "Resumen")
        self._pestanas.addTab(self._crear_pestana_graficos(), "Gráficos")
        layout_general.addWidget(self._pestanas, stretch=1)

        self.actualizar()

    def _crear_pestana_resumen(self) -> QWidget:
        pagina = QWidget()
        grupo = QFormLayout(pagina)
        self._etiquetas_valores: dict[str, QLabel] = {}
        for campo, etiqueta in ETIQUETAS:
            valor = QLabel("$ 0,00")
            grupo.addRow(etiqueta, valor)
            self._etiquetas_valores[campo] = valor
        self._etiqueta_total_disponible = QLabel("$ 0,00")
        grupo.addRow("Total disponible", self._etiqueta_total_disponible)
        return pagina

    def _crear_pestana_graficos(self) -> QWidget:
        area = QScrollArea()
        area.setWidgetResizable(True)
        contenido = QWidget()
        self._layout_graficos = QVBoxLayout(contenido)
        area.setWidget(contenido)
        return area

    def _mes_actual(self) -> str:
        return f"{self._campo_anio.value()}-{self._campo_mes.currentData():02d}"

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar (docs/AJUSTES_V1.1.md, etapa 1)

    def actualizar(self) -> None:
        self._actualizar_resumen()

    def _actualizar_resumen(self) -> None:
        resumen = resumen_del_mes(self.conexion, self._mes_actual())
        for campo, etiqueta_widget in self._etiquetas_valores.items():
            etiqueta_widget.setText(formato_moneda(getattr(resumen, campo)))
        self._etiqueta_total_disponible.setText(formato_moneda(total_disponible_actual(self.conexion)))
        self._actualizar_graficos()

    def _actualizar_graficos(self) -> None:
        while self._layout_graficos.count():
            item = self._layout_graficos.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        mes = self._mes_actual()

        puntos_venta = venta_vs_cobranza_12_meses(self.conexion, mes)
        categorias = [p.mes for p in puntos_venta]
        self._layout_graficos.addWidget(grafico_barras_agrupadas(
            "Venta vs. cobranza (últimos 12 meses)", categorias,
            [
                ("Venta", [p.venta for p in puntos_venta]),
                ("Cobranza", [p.cobranza for p in puntos_venta]),
            ],
            "Mes", "Monto",
        ))

        puntos_deuda = deuda_total_12_meses(self.conexion, mes)
        self._layout_graficos.addWidget(grafico_linea(
            "Deuda total de clientes (últimos 12 meses)", [p.mes for p in puntos_deuda],
            "Deuda", [p.deuda for p in puntos_deuda], "Mes", "Monto",
        ))

        top_clientes = top_clientes_del_mes(self.conexion, mes)
        self._layout_graficos.addWidget(grafico_barras_horizontales(
            "Top 10 clientes por venta del mes",
            [p.nombre for p in reversed(top_clientes)],
            "Venta", [p.total_final for p in reversed(top_clientes)],
            "Monto", "Cliente",
        ))

        puntos_iva = iva_venta_vs_compra_12_meses(self.conexion, mes)
        self._layout_graficos.addWidget(grafico_barras_agrupadas(
            "IVA venta vs. IVA compra (últimos 12 meses)", [p.mes for p in puntos_iva],
            [
                ("IVA venta", [p.iva_venta for p in puntos_iva]),
                ("IVA compra", [p.iva_compra for p in puntos_iva]),
            ],
            "Mes", "Monto",
        ))

        egresos = egresos_del_mes_por_categoria(self.conexion, mes)
        self._layout_graficos.addWidget(grafico_barras_horizontales(
            "Egresos de caja del mes por categoría",
            [s.nombre for s in reversed(egresos)],
            "Egresos", [s.monto for s in reversed(egresos)],
            "Monto", "Categoría",
        ))

    def _exportar_pdf(self) -> None:
        mes = self._mes_actual()
        ruta = ruta_pdf_automatica(f"Resumen {mes}.pdf", subcarpeta="Resumen mensual")
        generar_pdf_resumen_mensual(self.conexion, mes, ruta)
        abrir_pdf(ruta)

    def _exportar_excel(self) -> None:
        mes = self._mes_actual()
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Exportar resumen mensual", f"Resumen {mes}.xlsx", "Excel (*.xlsx)"
        )
        if not ruta:
            return
        generar_excel_resumen_mensual(self.conexion, mes, ruta)
        QMessageBox.information(self, "Listo", "Se exportó el resumen mensual.")
