"""Pantalla IVA del mes: IVA venta, IVA compra e IVA deuda, con el detalle
de comprobantes y compras (docs/PLAN.md, "Reportes y dashboard"; agregada
al menú en docs/AJUSTES_V1.1.md, etapa 1)."""

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
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ios.reports.formato import formato_fecha, formato_moneda
from ios.reports.iva_mes import generar_excel_iva_mes
from ios.services.iva_mes import detalle_iva_del_mes
from ios.ui.widgets import CampoEntero, ajustar_columnas

NOMBRES_MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]


class PaginaIvaMes(QWidget):
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
        self._campo_mes.currentIndexChanged.connect(self._cargar)
        encabezado.addWidget(self._campo_mes)
        self._campo_anio = CampoEntero()
        self._campo_anio.setRange(2000, 2100)
        self._campo_anio.setValue(hoy.year)
        self._campo_anio.valueChanged.connect(self._cargar)
        encabezado.addWidget(self._campo_anio)
        encabezado.addStretch(1)
        boton_excel = QPushButton("Exportar Excel")
        boton_excel.clicked.connect(self._exportar_excel)
        encabezado.addWidget(boton_excel)
        layout_general.addLayout(encabezado)

        resumen = QFormLayout()
        self._etiqueta_iva_venta = QLabel("$ 0,00")
        self._etiqueta_iva_compra = QLabel("$ 0,00")
        self._etiqueta_iva_deuda = QLabel("$ 0,00")
        resumen.addRow("IVA venta", self._etiqueta_iva_venta)
        resumen.addRow("IVA compra", self._etiqueta_iva_compra)
        resumen.addRow("IVA deuda", self._etiqueta_iva_deuda)
        layout_general.addLayout(resumen)

        layout_general.addWidget(QLabel("Ventas del mes"))
        self._tabla_ventas = QTableWidget(0, 4)
        self._tabla_ventas.setHorizontalHeaderLabels(["Remito", "Fecha", "Monto final", "IVA"])
        self._tabla_ventas.verticalHeader().setVisible(False)
        self._tabla_ventas.setEditTriggers(QTableWidget.NoEditTriggers)
        layout_general.addWidget(self._tabla_ventas, stretch=1)

        layout_general.addWidget(QLabel("Compras del mes"))
        self._tabla_compras = QTableWidget(0, 4)
        self._tabla_compras.setHorizontalHeaderLabels(["Nº factura", "Fecha", "Monto", "IVA"])
        self._tabla_compras.verticalHeader().setVisible(False)
        self._tabla_compras.setEditTriggers(QTableWidget.NoEditTriggers)
        layout_general.addWidget(self._tabla_compras, stretch=1)

        self.actualizar()

    def _mes(self) -> str:
        return f"{self._campo_anio.value()}-{self._campo_mes.currentData():02d}"

    def actualizar(self) -> None:
        self._cargar()

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar

    def _cargar(self) -> None:
        detalle = detalle_iva_del_mes(self.conexion, self._mes())
        self._etiqueta_iva_venta.setText(formato_moneda(detalle.iva_venta))
        self._etiqueta_iva_compra.setText(formato_moneda(detalle.iva_compra))
        self._etiqueta_iva_deuda.setText(formato_moneda(detalle.iva_deuda))

        self._tabla_ventas.setRowCount(len(detalle.comprobantes))
        for fila, c in enumerate(detalle.comprobantes):
            self._tabla_ventas.setItem(fila, 0, QTableWidgetItem(c["numero"]))
            self._tabla_ventas.setItem(fila, 1, QTableWidgetItem(formato_fecha(c["fecha"])))
            self._tabla_ventas.setItem(fila, 2, QTableWidgetItem(formato_moneda(c["monto_final"])))
            self._tabla_ventas.setItem(fila, 3, QTableWidgetItem(formato_moneda(c["iva_discriminado"])))
        ajustar_columnas(self._tabla_ventas)

        self._tabla_compras.setRowCount(len(detalle.compras))
        for fila, c in enumerate(detalle.compras):
            self._tabla_compras.setItem(fila, 0, QTableWidgetItem(c["numero_factura"]))
            self._tabla_compras.setItem(fila, 1, QTableWidgetItem(formato_fecha(c["fecha"])))
            self._tabla_compras.setItem(fila, 2, QTableWidgetItem(formato_moneda(c["monto"])))
            self._tabla_compras.setItem(fila, 3, QTableWidgetItem(formato_moneda(c["iva"])))
        ajustar_columnas(self._tabla_compras)

    def _exportar_excel(self) -> None:
        mes = self._mes()
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Exportar IVA del mes", f"IVA {mes}.xlsx", "Excel (*.xlsx)"
        )
        if not ruta:
            return
        generar_excel_iva_mes(self.conexion, mes, ruta)
        QMessageBox.information(self, "Listo", "Se exportó el IVA del mes.")
