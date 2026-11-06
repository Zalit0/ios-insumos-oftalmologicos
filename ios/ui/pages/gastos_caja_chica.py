"""Pantalla Gastos de caja chica: egresos manuales de caja (gastos y
retiros) entre dos fechas, filtrables por categoría y forma de pago, con
subtotal por categoría (docs/AJUSTES_V1.1.md, etapa 6.2, D4)."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
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

from ios.data import categorias_caja as datos_categorias
from ios.data import formas_pago as datos_formas_pago
from ios.reports.formato import formato_fecha, formato_moneda
from ios.reports.gastos_caja_chica import generar_excel_gastos_caja_chica, generar_pdf_gastos_caja_chica
from ios.reports.pdf_comun import abrir_pdf, ruta_pdf_automatica
from ios.services.gastos_caja_chica import gastos_de_caja_chica
from ios.ui.widgets import ajustar_columnas


class PaginaGastosCajaChica(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion

        layout_general = QVBoxLayout(self)
        layout_general.addWidget(QLabel("Gastos de caja chica"))

        fila_filtros = QHBoxLayout()
        fila_filtros.addWidget(QLabel("Desde"))
        self._campo_desde = QDateEdit(QDate.currentDate().addMonths(-1))
        self._campo_desde.setCalendarPopup(True)
        self._campo_desde.dateChanged.connect(self._cargar)
        fila_filtros.addWidget(self._campo_desde)
        fila_filtros.addWidget(QLabel("Hasta"))
        self._campo_hasta = QDateEdit(QDate.currentDate())
        self._campo_hasta.setCalendarPopup(True)
        self._campo_hasta.dateChanged.connect(self._cargar)
        fila_filtros.addWidget(self._campo_hasta)

        fila_filtros.addWidget(QLabel("Categoría"))
        self._campo_categoria = QComboBox()
        self._campo_categoria.currentIndexChanged.connect(self._cargar)
        fila_filtros.addWidget(self._campo_categoria)

        fila_filtros.addWidget(QLabel("Forma de pago"))
        self._campo_forma_pago = QComboBox()
        self._campo_forma_pago.currentIndexChanged.connect(self._cargar)
        fila_filtros.addWidget(self._campo_forma_pago)

        fila_filtros.addStretch(1)
        boton_pdf = QPushButton("Exportar PDF")
        boton_pdf.clicked.connect(self._exportar_pdf)
        fila_filtros.addWidget(boton_pdf)
        boton_excel = QPushButton("Exportar Excel")
        boton_excel.clicked.connect(self._exportar_excel)
        fila_filtros.addWidget(boton_excel)
        layout_general.addLayout(fila_filtros)

        self._tabla = QTableWidget(0, 5)
        self._tabla.setHorizontalHeaderLabels(["Fecha", "Categoría", "Concepto", "Forma de pago", "Monto"])
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        layout_general.addWidget(self._tabla, stretch=1)

        self._etiqueta_totales = QLabel("")
        layout_general.addWidget(self._etiqueta_totales)

        self.actualizar()

    # --- interfaz de navegación (docs/AJUSTES_V1.1.md, etapa 1) ---

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar

    def actualizar(self) -> None:
        self._cargar_combos()
        self._cargar()

    def _cargar_combos(self) -> None:
        for combo, cargar in (
            (self._campo_categoria, self._opciones_categoria),
            (self._campo_forma_pago, self._opciones_forma_pago),
        ):
            seleccionado = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for etiqueta, valor in cargar():
                combo.addItem(etiqueta, valor)
            indice = combo.findData(seleccionado)
            combo.setCurrentIndex(indice if indice >= 0 else 0)
            combo.blockSignals(False)

    def _opciones_categoria(self) -> list[tuple[str, int | None]]:
        opciones: list[tuple[str, int | None]] = [("Todas las categorías", None)]
        for categoria in datos_categorias.listar_categorias(self.conexion, incluir_inactivas=True):
            if categoria["tipo"] == "egreso":
                opciones.append((categoria["nombre"], categoria["id"]))
        return opciones

    def _opciones_forma_pago(self) -> list[tuple[str, int | None]]:
        opciones: list[tuple[str, int | None]] = [("Todas las formas de pago", None)]
        for forma in datos_formas_pago.listar_formas_pago(self.conexion, incluir_inactivas=True):
            opciones.append((forma["nombre"], forma["id"]))
        return opciones

    # --- fechas ---

    def _fecha_desde(self) -> str:
        return self._campo_desde.date().toString("yyyy-MM-dd")

    def _fecha_hasta(self) -> str:
        return self._campo_hasta.date().toString("yyyy-MM-dd")

    # --- tabla ---

    def _cargar(self) -> None:
        resultado = gastos_de_caja_chica(
            self.conexion,
            self._fecha_desde(),
            self._fecha_hasta(),
            categoria_id=self._campo_categoria.currentData(),
            forma_pago_id=self._campo_forma_pago.currentData(),
        )
        self._tabla.setRowCount(len(resultado.filas))
        for fila, item in enumerate(resultado.filas):
            self._tabla.setItem(fila, 0, QTableWidgetItem(formato_fecha(item.fecha)))
            self._tabla.setItem(fila, 1, QTableWidgetItem(item.categoria_nombre))
            self._tabla.setItem(fila, 2, QTableWidgetItem(item.concepto))
            self._tabla.setItem(fila, 3, QTableWidgetItem(item.forma_pago_nombre))
            self._tabla.setItem(fila, 4, QTableWidgetItem(formato_moneda(item.monto)))
        ajustar_columnas(self._tabla)

        texto = f"Total: {formato_moneda(resultado.total)}"
        if len(resultado.subtotales_por_categoria) > 1:
            subtotales = " · ".join(
                f"{s.nombre}: {formato_moneda(s.monto)}" for s in resultado.subtotales_por_categoria
            )
            texto += f"\nPor categoría — {subtotales}"
        self._etiqueta_totales.setText(texto)

    # --- exportar ---

    def _exportar_pdf(self) -> None:
        ruta = ruta_pdf_automatica(
            f"Gastos de caja chica - {self._fecha_desde()} a {self._fecha_hasta()}.pdf",
            subcarpeta="Gastos de caja chica",
        )
        generar_pdf_gastos_caja_chica(
            self.conexion, self._fecha_desde(), self._fecha_hasta(), ruta,
            categoria_id=self._campo_categoria.currentData(),
            forma_pago_id=self._campo_forma_pago.currentData(),
        )
        abrir_pdf(ruta)

    def _exportar_excel(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Exportar gastos de caja chica", "Gastos de caja chica.xlsx", "Excel (*.xlsx)"
        )
        if not ruta:
            return
        generar_excel_gastos_caja_chica(
            self.conexion, self._fecha_desde(), self._fecha_hasta(), ruta,
            categoria_id=self._campo_categoria.currentData(),
            forma_pago_id=self._campo_forma_pago.currentData(),
        )
        QMessageBox.information(self, "Listo", "Se exportaron los gastos de caja chica.")
