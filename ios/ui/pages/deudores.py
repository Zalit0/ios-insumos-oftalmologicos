"""Pantalla Deudores: clientes con saldo, de mayor a menor, con la
antigüedad del remito más viejo impago (docs/PLAN.md, "Reportes y
dashboard"; agregada al menú en docs/AJUSTES_V1.1.md, etapa 1)."""

from __future__ import annotations

import sqlite3

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

from ios.reports.deudores import generar_excel_deudores, generar_pdf_deudores
from ios.reports.formato import formato_fecha, formato_moneda
from ios.reports.pdf_comun import abrir_pdf, ruta_pdf_automatica
from ios.services.listado_deudores import listado_deudores
from ios.ui.widgets import ajustar_columnas


class PaginaDeudores(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion

        layout_general = QVBoxLayout(self)

        encabezado = QHBoxLayout()
        encabezado.addWidget(QLabel("Al"))
        self._campo_fecha = QDateEdit(QDate.currentDate())
        self._campo_fecha.setCalendarPopup(True)
        self._campo_fecha.dateChanged.connect(self._cargar)
        encabezado.addWidget(self._campo_fecha)
        encabezado.addStretch(1)
        boton_pdf = QPushButton("Exportar PDF")
        boton_pdf.clicked.connect(self._exportar_pdf)
        encabezado.addWidget(boton_pdf)
        boton_excel = QPushButton("Exportar Excel")
        boton_excel.clicked.connect(self._exportar_excel)
        encabezado.addWidget(boton_excel)
        layout_general.addLayout(encabezado)

        self._tabla = QTableWidget(0, 4)
        self._tabla.setHorizontalHeaderLabels(
            ["Cliente", "Saldo", "Remito más viejo impago", "Antigüedad"]
        )
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        layout_general.addWidget(self._tabla, stretch=1)

        self.actualizar()

    def _fecha(self) -> str:
        return self._campo_fecha.date().toString("yyyy-MM-dd")

    def actualizar(self) -> None:
        self._cargar()

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar

    def _cargar(self) -> None:
        deudores = listado_deudores(self.conexion, self._fecha())
        self._tabla.setRowCount(len(deudores))
        for fila, deudor in enumerate(deudores):
            self._tabla.setItem(fila, 0, QTableWidgetItem(deudor.nombre))
            self._tabla.setItem(fila, 1, QTableWidgetItem(formato_moneda(deudor.saldo)))
            self._tabla.setItem(
                fila, 2,
                QTableWidgetItem(
                    formato_fecha(deudor.fecha_remito_mas_viejo)
                    if deudor.fecha_remito_mas_viejo else "-"
                ),
            )
            self._tabla.setItem(
                fila, 3,
                QTableWidgetItem(
                    f"{deudor.antiguedad_dias} días" if deudor.antiguedad_dias is not None else "-"
                ),
            )
        ajustar_columnas(self._tabla)

    def _exportar_pdf(self) -> None:
        ruta = ruta_pdf_automatica(f"Deudores - {self._fecha()}.pdf", subcarpeta="Deudores")
        generar_pdf_deudores(self.conexion, self._fecha(), ruta)
        abrir_pdf(ruta)

    def _exportar_excel(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Exportar deudores", "Deudores.xlsx", "Excel (*.xlsx)"
        )
        if not ruta:
            return
        generar_excel_deudores(self.conexion, self._fecha(), ruta)
        QMessageBox.information(self, "Listo", "Se exportó el listado de deudores.")
