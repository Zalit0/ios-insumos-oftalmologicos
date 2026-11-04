"""Pantalla Exportación para el contador: comprobantes, recibos, compras y
movimientos de caja de un período, en un solo Excel (docs/PLAN.md,
"Reportes y dashboard"; agregada al menú en docs/AJUSTES_V1.1.md,
etapa 1)."""

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
    QVBoxLayout,
    QWidget,
)

from ios.reports.exportacion_contador import generar_excel_exportacion_contador


class PaginaExportacionContador(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        hoy = date.today()

        layout_general = QVBoxLayout(self)
        layout_general.addWidget(QLabel(
            "Exporta a un Excel, en hojas separadas, los comprobantes, recibos, "
            "compras y movimientos de caja del período elegido."
        ))

        fila = QHBoxLayout()
        fila.addWidget(QLabel("Desde"))
        self._campo_desde = QDateEdit(QDate(hoy.year, hoy.month, 1))
        self._campo_desde.setCalendarPopup(True)
        fila.addWidget(self._campo_desde)
        fila.addWidget(QLabel("Hasta"))
        self._campo_hasta = QDateEdit(QDate.currentDate())
        self._campo_hasta.setCalendarPopup(True)
        fila.addWidget(self._campo_hasta)
        fila.addStretch(1)
        layout_general.addLayout(fila)

        boton_excel = QPushButton("Exportar Excel")
        boton_excel.clicked.connect(self._exportar_excel)
        layout_general.addWidget(boton_excel)
        layout_general.addStretch(1)

    def actualizar(self) -> None:
        pass  # no muestra datos propios, solo filtros

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar

    def _exportar_excel(self) -> None:
        desde = self._campo_desde.date().toString("yyyy-MM-dd")
        hasta = self._campo_hasta.date().toString("yyyy-MM-dd")
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Exportar para el contador", f"IOS {desde} a {hasta}.xlsx", "Excel (*.xlsx)"
        )
        if not ruta:
            return
        generar_excel_exportacion_contador(self.conexion, desde, hasta, ruta)
        QMessageBox.information(self, "Listo", "Se generó la exportación.")
