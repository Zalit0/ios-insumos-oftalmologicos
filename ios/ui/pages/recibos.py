"""Pantalla Recibos: listado de todos los recibos emitidos, con filtros
por cliente, fecha y estado (docs/AJUSTES_V1.1.md, módulo de recibos).

Para asentar una cobranza nueva o anular un recibo se sigue usando la
pantalla Cobranzas; esta pantalla también permite corregir la forma de
pago (o el monto) de una línea de un recibo ya cargado, para cuando se
tildó Efectivo en vez de Transferencia (o viceversa) y la caja no
cierra."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
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

from ios.data import clientes as datos_clientes
from ios.data import formas_pago as datos_formas_pago
from ios.data import recibos as datos_recibos
from ios.reports.formato import formato_fecha, formato_moneda
from ios.reports.pdf_comun import abrir_pdf, ruta_pdf_automatica
from ios.reports.recibo import generar_pdf_recibo
from ios.services import cobranzas as servicio_cobranzas
from ios.services.listado_recibos import listado_recibos
from ios.ui.widgets import CampoDecimal, ajustar_columnas

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


class _FilaCorreccionPago(QWidget):
    """Una línea de forma de pago de un recibo, con su forma y monto
    editables -- salvo que la línea sea un cheque, que no se puede
    cambiar desde acá (tiene datos propios: número, banco, fecha de
    cobro) y queda solo para mostrar."""

    def __init__(self, conexion: sqlite3.Connection, recibo_pago: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self.recibo_pago_id = recibo_pago["id"]
        self._forma_original_id = recibo_pago["forma_pago_id"]
        self._monto_original = recibo_pago["monto"]
        forma_original = datos_formas_pago.obtener_forma_pago(conexion, recibo_pago["forma_pago_id"])
        self._es_cheque = forma_original["tipo"] == "cheque"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.combo_forma = QComboBox()
        for forma in datos_formas_pago.listar_formas_pago(conexion):
            if forma["tipo"] == "cheque":
                continue
            self.combo_forma.addItem(forma["nombre"], forma["id"])
        if self._es_cheque:
            self.combo_forma.addItem(forma_original["nombre"], forma_original["id"])
        self.combo_forma.setCurrentIndex(self.combo_forma.findData(recibo_pago["forma_pago_id"]))

        self.campo_monto = CampoDecimal()
        self.campo_monto.setRange(0, 99_999_999)
        self.campo_monto.setDecimals(2)
        self.campo_monto.setValue(float(recibo_pago["monto"]))

        if self._es_cheque:
            self.combo_forma.setEnabled(False)
            self.campo_monto.setEnabled(False)
            layout.addWidget(QLabel("Cheque (no se puede cambiar desde acá):"))

        layout.addWidget(self.combo_forma)
        layout.addWidget(self.campo_monto)

    def guardar_si_cambio(self, conexion: sqlite3.Connection, fecha_hoy: str) -> None:
        if self._es_cheque:
            return
        forma_nueva = self.combo_forma.currentData()
        monto_nuevo = Decimal(str(self.campo_monto.value()))
        if forma_nueva == self._forma_original_id and monto_nuevo == self._monto_original:
            return
        servicio_cobranzas.editar_forma_pago_recibo_pago(
            conexion, self.recibo_pago_id, fecha_hoy=fecha_hoy,
            forma_pago_id=forma_nueva, monto=monto_nuevo,
        )


class _DialogoEditarFormaPago(QDialog):
    """Corrige la forma de pago (o el monto) de una o más líneas de un
    recibo ya cargado — pensado para arreglar un "Efectivo" que en
    realidad era "Transferencia" (o viceversa) sin tener que anular el
    recibo entero."""

    def __init__(self, conexion: sqlite3.Connection, recibo: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self.conexion = conexion
        self.setWindowTitle(f"Editar forma de pago — Recibo {recibo['numero']}")

        formulario = QFormLayout(self)
        self._filas: list[_FilaCorreccionPago] = []
        for recibo_pago in datos_recibos.listar_recibo_pagos(conexion, recibo["id"]):
            fila = _FilaCorreccionPago(conexion, recibo_pago)
            self._filas.append(fila)
            formulario.addRow(fila)

        pie = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(self.reject)
        pie.addWidget(boton_cancelar)
        boton_guardar = QPushButton("Guardar corrección")
        boton_guardar.clicked.connect(self._guardar)
        pie.addWidget(boton_guardar)
        formulario.addRow(pie)

    def _guardar(self) -> None:
        fecha_hoy = date.today().isoformat()
        try:
            for fila in self._filas:
                fila.guardar_si_cambio(self.conexion, fecha_hoy)
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return
        self.accept()


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
        boton_pdf = QPushButton("Reimprimir recibo seleccionado")
        boton_pdf.clicked.connect(self._exportar_pdf_seleccionado)
        pie.addWidget(boton_pdf)
        boton_editar_forma_pago = QPushButton("Editar forma de pago")
        boton_editar_forma_pago.clicked.connect(self._editar_forma_pago_seleccionado)
        pie.addWidget(boton_editar_forma_pago)
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
        fecha = self._tabla.item(fila, COLUMNA_FECHA).text().replace("/", "-")
        ruta = ruta_pdf_automatica(f"Recibo {item_numero.text()} - {fecha}.pdf", subcarpeta="Recibos")
        generar_pdf_recibo(self.conexion, recibo_id, ruta)
        abrir_pdf(ruta)

    def _editar_forma_pago_seleccionado(self) -> None:
        fila = self._tabla.currentRow()
        if fila < 0:
            QMessageBox.warning(self, "Nada seleccionado", "Elegí un recibo de la lista.")
            return
        recibo_id = self._tabla.item(fila, COLUMNA_NUMERO).data(Qt.UserRole)
        recibo = datos_recibos.obtener_recibo(self.conexion, recibo_id)
        if recibo["estado"] != "vigente":
            QMessageBox.warning(self, "Recibo anulado", "Un recibo anulado no se puede corregir.")
            return
        dialogo = _DialogoEditarFormaPago(self.conexion, recibo, self)
        if dialogo.exec() == QDialog.Accepted:
            self._cargar()
