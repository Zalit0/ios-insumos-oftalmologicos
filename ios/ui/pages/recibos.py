"""Pantalla Recibos: listado de todos los recibos emitidos, con filtros
por cliente, fecha y estado (docs/AJUSTES_V1.1.md, módulo de recibos).

Solo lectura: para asentar una cobranza nueva o anular un recibo se sigue
usando la pantalla Cobranzas."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
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

from ios.data import clientes as datos_clientes
from ios.reports.formato import formato_fecha, formato_moneda
from ios.reports.recibo import generar_pdf_recibo
from ios.services.listado_recibos import listado_recibos
from ios.ui.widgets import ajustar_columnas

ETIQUETAS_ORIGEN = {"manual": "Manual", "importado": "Importado"}
ETIQUETAS_ESTADO = {"vigente": "Vigente", "anulado": "Anulado"}

COLUMNA_NUMERO = 0
COLUMNA_FECHA = 1
COLUMNA_CLIENTE = 2
COLUMNA_MONTO = 3
COLUMNA_APLICADO = 4
COLUMNA_PENDIENTE = 5
COLUMNA_ORIGEN = 6
COLUMNA_ESTADO = 7


def _item_moneda(valor: Decimal) -> QTableWidgetItem:
    item = QTableWidgetItem(formato_moneda(valor))
    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    return item


class PaginaRecibos(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion

        layout_general = QVBoxLayout(self)

        filtros = QHBoxLayout()
        filtros.addWidget(QLabel("Cliente"))
        self._campo_cliente = QComboBox()
        self._campo_cliente.currentIndexChanged.connect(self._cargar)
        filtros.addWidget(self._campo_cliente, stretch=1)

        filtros.addWidget(QLabel("Desde"))
        hoy = date.today()
        self._campo_desde = QDateEdit(QDate(hoy.year, hoy.month, 1))
        self._campo_desde.setCalendarPopup(True)
        self._campo_desde.dateChanged.connect(self._cargar)
        filtros.addWidget(self._campo_desde)

        filtros.addWidget(QLabel("Hasta"))
        self._campo_hasta = QDateEdit(QDate.currentDate())
        self._campo_hasta.setCalendarPopup(True)
        self._campo_hasta.dateChanged.connect(self._cargar)
        filtros.addWidget(self._campo_hasta)

        self._casilla_ver_todo = QCheckBox("Ver todo (sin filtro de fecha)")
        self._casilla_ver_todo.toggled.connect(self._cambio_ver_todo)
        filtros.addWidget(self._casilla_ver_todo)

        filtros.addWidget(QLabel("Estado"))
        self._campo_estado = QComboBox()
        self._campo_estado.addItem("Todos", None)
        self._campo_estado.addItem("Vigente", "vigente")
        self._campo_estado.addItem("Anulado", "anulado")
        self._campo_estado.currentIndexChanged.connect(self._cargar)
        filtros.addWidget(self._campo_estado)

        layout_general.addLayout(filtros)

        self._tabla = QTableWidget(0, 8)
        self._tabla.setHorizontalHeaderLabels(
            ["Nº", "Fecha", "Cliente", "Monto", "Aplicado", "Pendiente", "Origen", "Estado"]
        )
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla.setSelectionBehavior(QTableWidget.SelectRows)
        layout_general.addWidget(self._tabla, stretch=1)

        pie = QHBoxLayout()
        self._etiqueta_total = QLabel("Total (vigentes): $ 0,00")
        self._etiqueta_total.setStyleSheet("font-weight: bold;")
        pie.addWidget(self._etiqueta_total)
        pie.addStretch(1)
        boton_pdf = QPushButton("Ver PDF del recibo seleccionado")
        boton_pdf.clicked.connect(self._exportar_pdf_seleccionado)
        pie.addWidget(boton_pdf)
        layout_general.addLayout(pie)

        self.actualizar()

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar (docs/AJUSTES_V1.1.md, etapa 1)

    def actualizar(self) -> None:
        self._campo_cliente.blockSignals(True)
        self._campo_cliente.clear()
        self._campo_cliente.addItem("Todos los clientes", None)
        for cliente in datos_clientes.listar_clientes(self.conexion):
            self._campo_cliente.addItem(cliente["nombre"], cliente["id"])
        self._campo_cliente.blockSignals(False)
        self._cargar()

    def _cambio_ver_todo(self, marcado: bool) -> None:
        self._campo_desde.setEnabled(not marcado)
        self._campo_hasta.setEnabled(not marcado)
        self._cargar()

    def _cargar(self) -> None:
        cliente_id = self._campo_cliente.currentData()
        estado = self._campo_estado.currentData()
        sin_fecha = self._casilla_ver_todo.isChecked()
        fecha_desde = None if sin_fecha else self._campo_desde.date().toString("yyyy-MM-dd")
        fecha_hasta = None if sin_fecha else self._campo_hasta.date().toString("yyyy-MM-dd")

        recibos = listado_recibos(
            self.conexion, cliente_id=cliente_id, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
            estado=estado,
        )

        self._tabla.setRowCount(len(recibos))
        total_vigentes = Decimal(0)
        for fila, recibo in enumerate(recibos):
            item_numero = QTableWidgetItem(str(recibo.numero))
            item_numero.setData(Qt.UserRole, recibo.recibo_id)
            self._tabla.setItem(fila, COLUMNA_NUMERO, item_numero)
            self._tabla.setItem(fila, COLUMNA_FECHA, QTableWidgetItem(formato_fecha(recibo.fecha)))
            self._tabla.setItem(fila, COLUMNA_CLIENTE, QTableWidgetItem(recibo.cliente_nombre))
            self._tabla.setItem(fila, COLUMNA_MONTO, _item_moneda(recibo.monto_total))
            self._tabla.setItem(fila, COLUMNA_APLICADO, _item_moneda(recibo.aplicado))
            self._tabla.setItem(fila, COLUMNA_PENDIENTE, _item_moneda(recibo.pendiente))
            self._tabla.setItem(
                fila, COLUMNA_ORIGEN, QTableWidgetItem(ETIQUETAS_ORIGEN.get(recibo.origen, recibo.origen))
            )
            self._tabla.setItem(
                fila, COLUMNA_ESTADO, QTableWidgetItem(ETIQUETAS_ESTADO.get(recibo.estado, recibo.estado))
            )
            if recibo.estado == "vigente":
                total_vigentes += recibo.monto_total
        ajustar_columnas(self._tabla)
        self._etiqueta_total.setText(f"Total (vigentes): {formato_moneda(total_vigentes)}")

    def _exportar_pdf_seleccionado(self) -> None:
        fila = self._tabla.currentRow()
        if fila < 0:
            QMessageBox.warning(self, "Nada seleccionado", "Elegí un recibo de la lista.")
            return
        item_numero = self._tabla.item(fila, COLUMNA_NUMERO)
        recibo_id = item_numero.data(Qt.UserRole)
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Guardar recibo", f"Recibo {item_numero.text()}.pdf", "PDF (*.pdf)"
        )
        if not ruta:
            return
        generar_pdf_recibo(self.conexion, recibo_id, ruta)
        QMessageBox.information(self, "Listo", "Se exportó el recibo.")
