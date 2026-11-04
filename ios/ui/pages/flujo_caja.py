"""Pantalla Flujo de caja: ingresos y egresos por día y por categoría en
un período, con el saldo acumulado (docs/PLAN.md, "Reportes y dashboard";
agregada al menú en docs/AJUSTES_V1.1.md, etapa 1)."""

from __future__ import annotations

import sqlite3
from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ios.reports.flujo_caja import generar_excel_flujo_caja
from ios.reports.formato import formato_moneda
from ios.services.flujo_caja import flujo_de_caja_diario
from ios.ui.widgets import ajustar_columnas


class PaginaFlujoCaja(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        hoy = date.today()

        layout_general = QVBoxLayout(self)

        encabezado = QHBoxLayout()
        encabezado.addWidget(QLabel("Desde"))
        self._campo_desde = QDateEdit(QDate(hoy.year, hoy.month, 1))
        self._campo_desde.setCalendarPopup(True)
        self._campo_desde.dateChanged.connect(self._cargar)
        encabezado.addWidget(self._campo_desde)
        encabezado.addWidget(QLabel("Hasta"))
        self._campo_hasta = QDateEdit(QDate.currentDate())
        self._campo_hasta.setCalendarPopup(True)
        self._campo_hasta.dateChanged.connect(self._cargar)
        encabezado.addWidget(self._campo_hasta)
        encabezado.addStretch(1)
        boton_excel = QPushButton("Exportar Excel")
        boton_excel.clicked.connect(self._exportar_excel)
        encabezado.addWidget(boton_excel)
        layout_general.addLayout(encabezado)

        self._tabla = QTableWidget(0, 5)
        self._tabla.setHorizontalHeaderLabels(
            ["Fecha", "Ingresos", "Egresos", "Saldo del día", "Saldo acumulado"]
        )
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        layout_general.addWidget(self._tabla, stretch=1)

        self.actualizar()

    def _desde(self) -> str:
        return self._campo_desde.date().toString("yyyy-MM-dd")

    def _hasta(self) -> str:
        return self._campo_hasta.date().toString("yyyy-MM-dd")

    def actualizar(self) -> None:
        self._cargar()

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar

    def _cargar(self) -> None:
        filas = flujo_de_caja_diario(self.conexion, self._desde(), self._hasta())
        self._tabla.setRowCount(len(filas))
        for fila, dato in enumerate(filas):
            self._tabla.setItem(fila, 0, QTableWidgetItem(dato.fecha))
            self._tabla.setItem(fila, 1, QTableWidgetItem(formato_moneda(dato.ingresos)))
            self._tabla.setItem(fila, 2, QTableWidgetItem(formato_moneda(dato.egresos)))
            self._tabla.setItem(fila, 3, QTableWidgetItem(formato_moneda(dato.saldo_del_dia)))
            self._tabla.setItem(fila, 4, QTableWidgetItem(formato_moneda(dato.saldo_acumulado)))
        ajustar_columnas(self._tabla)

    def _exportar_excel(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Exportar flujo de caja", "Flujo de caja.xlsx", "Excel (*.xlsx)"
        )
        if not ruta:
            return
        generar_excel_flujo_caja(self.conexion, self._desde(), self._hasta(), ruta)
        QMessageBox.information(self, "Listo", "Se exportó el flujo de caja.")
