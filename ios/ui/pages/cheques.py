"""Pantalla Cheques: cheques en cartera ordenados por fecha de cobro, con
cambio de estado (cobrado, entregado a proveedor o rechazado). "Entregado
a proveedor" se hace desde Compras y proveedores; acá se cobra o se
rechaza (docs/PLAN.md, "Pantallas")."""

from __future__ import annotations

import sqlite3
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ios.data import cheques as datos_cheques
from ios.data import clientes as datos_clientes
from ios.data import formas_pago as datos_formas_pago
from ios.reports.formato import formato_fecha, formato_moneda
from ios.services.cheques import cobrar_cheque, rechazar_cheque
from ios.ui.widgets import ajustar_columnas


class PaginaCheques(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion

        layout_general = QVBoxLayout(self)
        layout_general.addWidget(QLabel("Cheques en cartera"))

        self._tabla = QTableWidget(0, 5)
        self._tabla.setHorizontalHeaderLabels(["Nº", "Cliente", "Banco", "Monto", "Fecha de cobro"])
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.setSelectionBehavior(QTableWidget.SelectRows)
        self._tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        layout_general.addWidget(self._tabla, stretch=1)

        pie = QHBoxLayout()
        pie.addWidget(QLabel("Depositar en"))
        self._campo_forma_banco = QComboBox()
        pie.addWidget(self._campo_forma_banco)
        boton_cobrar = QPushButton("Cobrar seleccionado")
        boton_cobrar.clicked.connect(self._cobrar)
        pie.addWidget(boton_cobrar)
        boton_rechazar = QPushButton("Rechazar seleccionado")
        boton_rechazar.clicked.connect(self._rechazar)
        pie.addWidget(boton_rechazar)
        pie.addStretch(1)
        layout_general.addLayout(pie)

        self.actualizar()

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar (docs/AJUSTES_V1.1.md, etapa 1)

    def actualizar(self) -> None:
        self._campo_forma_banco.clear()
        for forma in datos_formas_pago.listar_formas_pago(self.conexion):
            if forma["tipo"] == "banco":
                self._campo_forma_banco.addItem(forma["nombre"], forma["id"])
        self._cargar_tabla()

    def _cargar_tabla(self) -> None:
        cheques = datos_cheques.listar_cheques_en_cartera(self.conexion)
        self._tabla.setRowCount(len(cheques))
        for fila, cheque in enumerate(cheques):
            cliente = datos_clientes.obtener_cliente(self.conexion, cheque["cliente_id"])
            self._tabla.setItem(fila, 0, QTableWidgetItem(cheque["numero"]))
            self._tabla.setItem(fila, 1, QTableWidgetItem(cliente["nombre"]))
            self._tabla.setItem(fila, 2, QTableWidgetItem(cheque["banco"] or "-"))
            self._tabla.setItem(fila, 3, QTableWidgetItem(formato_moneda(cheque["monto"])))
            self._tabla.setItem(fila, 4, QTableWidgetItem(formato_fecha(cheque["fecha_cobro"])))
            self._tabla.item(fila, 0).setData(Qt.UserRole, cheque["id"])
        ajustar_columnas(self._tabla)

    def _cheque_seleccionado(self) -> int | None:
        filas = self._tabla.selectionModel().selectedRows()
        if not filas:
            return None
        return self._tabla.item(filas[0].row(), 0).data(Qt.UserRole)

    def _forma_pago_cheque_id(self) -> int | None:
        for forma in datos_formas_pago.listar_formas_pago(self.conexion):
            if forma["tipo"] == "cheque":
                return forma["id"]
        return None

    def _cobrar(self) -> None:
        cheque_id = self._cheque_seleccionado()
        if cheque_id is None:
            return
        forma_banco_id = self._campo_forma_banco.currentData()
        if forma_banco_id is None:
            QMessageBox.warning(self, "Falta la forma de pago", "No hay ninguna forma de pago de tipo banco configurada.")
            return

        try:
            cobrar_cheque(
                self.conexion, cheque_id, date.today().isoformat(),
                self._forma_pago_cheque_id(), forma_banco_id,
            )
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo cobrar", str(error))
            return
        self._cargar_tabla()

    def _rechazar(self) -> None:
        cheque_id = self._cheque_seleccionado()
        if cheque_id is None:
            return
        respuesta = QMessageBox.question(self, "Rechazar cheque", "¿Marcar este cheque como rechazado?")
        if respuesta != QMessageBox.Yes:
            return
        try:
            rechazar_cheque(self.conexion, cheque_id)
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo rechazar", str(error))
            return
        self._cargar_tabla()
