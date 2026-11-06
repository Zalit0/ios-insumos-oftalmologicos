"""Pantalla Entrega de pedidos especiales (plan de detalle de comprobantes,
etapa 5): por cliente, tildar las líneas especiales ya recibidas para
generar de una un solo comprobante con un renglón por cristal."""

from __future__ import annotations

import sqlite3
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ios.data import clientes as datos_clientes
from ios.data import tipos_comprobante as datos_tipos_comprobante
from ios.data.tipos_cristal import obtener_tipo_cristal
from ios.services.comprobantes import NumeroDuplicadoError, siguiente_numero_comprobante
from ios.services.pedidos_proveedor import ItemEntrega, generar_entrega, lineas_listas_para_entregar
from ios.services.tipos_cristal import precio_unitario
from ios.ui.widgets import ajustar_columnas

COLUMNA_LISTA_TILDE = 0
COLUMNA_LISTA_CRISTAL = 1
COLUMNA_LISTA_CANTIDAD = 2
COLUMNA_LISTA_GRADUACION = 3
COLUMNA_LISTA_PRECIO = 4


class PaginaEntregaPedidos(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self._cliente_id: int | None = None
        self._ids_listas: list[int] = []

        layout_general = QVBoxLayout(self)

        fila_cliente = QHBoxLayout()
        fila_cliente.addWidget(QLabel("Cliente"))
        self._campo_cliente = QComboBox()
        self._campo_cliente.currentIndexChanged.connect(self._al_elegir_cliente)
        fila_cliente.addWidget(self._campo_cliente, stretch=1)
        layout_general.addLayout(fila_cliente)

        layout_general.addWidget(QLabel("Listas para entregar"))
        self._tabla_listas = QTableWidget(0, 5)
        self._tabla_listas.setHorizontalHeaderLabels(
            ["", "Cristal/Descripción", "Cantidad", "Graduación", "Precio unitario"]
        )
        self._tabla_listas.verticalHeader().setVisible(False)
        self._tabla_listas.setEditTriggers(
            QTableWidget.CurrentChanged | QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed
        )
        layout_general.addWidget(self._tabla_listas, stretch=1)

        fila_comprobante = QHBoxLayout()
        fila_comprobante.addWidget(QLabel("Tipo"))
        self._campo_tipo = QComboBox()
        for tipo in datos_tipos_comprobante.listar_tipos_comprobante(conexion):
            self._campo_tipo.addItem(tipo["abreviatura"], tipo["id"])
        self._campo_tipo.currentIndexChanged.connect(self._autosugerir_numero)
        fila_comprobante.addWidget(self._campo_tipo)
        fila_comprobante.addWidget(QLabel("Número"))
        self._campo_numero = QLineEdit()
        fila_comprobante.addWidget(self._campo_numero)
        fila_comprobante.addWidget(QLabel("Fecha"))
        self._campo_fecha = QDateEdit(QDate.currentDate())
        self._campo_fecha.setCalendarPopup(True)
        fila_comprobante.addWidget(self._campo_fecha)
        fila_comprobante.addWidget(QLabel("Sucursal"))
        self._campo_sucursal = QComboBox()
        fila_comprobante.addWidget(self._campo_sucursal)
        layout_general.addLayout(fila_comprobante)

        pie = QHBoxLayout()
        pie.addStretch(1)
        self._boton_generar = QPushButton("Generar comprobante de entrega")
        self._boton_generar.clicked.connect(self._generar_comprobante)
        pie.addWidget(self._boton_generar)
        layout_general.addLayout(pie)

        self.actualizar()

    # --- navegación ---

    def actualizar(self) -> None:
        self._cargar_combo_clientes()

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar

    def _cargar_combo_clientes(self) -> None:
        cliente_actual = self._campo_cliente.currentData()
        ids_clientes = sorted({l["cliente_id"] for l in lineas_listas_para_entregar(self.conexion)})

        self._campo_cliente.blockSignals(True)
        self._campo_cliente.clear()
        for cliente_id in ids_clientes:
            cliente = datos_clientes.obtener_cliente(self.conexion, cliente_id)
            if cliente is not None:
                self._campo_cliente.addItem(cliente["nombre"], cliente_id)
        indice = self._campo_cliente.findData(cliente_actual)
        self._campo_cliente.setCurrentIndex(max(indice, 0))
        self._campo_cliente.blockSignals(False)
        self._al_elegir_cliente()

    def _al_elegir_cliente(self) -> None:
        self._cliente_id = self._campo_cliente.currentData()
        self._cargar_sucursales()
        self._cargar_tabla_listas()
        self._autosugerir_numero()

    def _cargar_sucursales(self) -> None:
        self._campo_sucursal.clear()
        if self._cliente_id is None:
            return
        for sucursal in datos_clientes.listar_sucursales(self.conexion, self._cliente_id):
            self._campo_sucursal.addItem(sucursal["nombre"], sucursal["id"])

    def _autosugerir_numero(self) -> None:
        tipo_id = self._campo_tipo.currentData()
        if tipo_id is None:
            return
        self._campo_numero.setText(siguiente_numero_comprobante(self.conexion, tipo_id))

    # --- listas para entregar ---

    def _cargar_tabla_listas(self) -> None:
        lineas = (
            lineas_listas_para_entregar(self.conexion, self._cliente_id)
            if self._cliente_id is not None else []
        )
        self._ids_listas = [l["id"] for l in lineas]
        self._tabla_listas.setRowCount(len(lineas))
        for fila, linea in enumerate(lineas):
            tilde = QTableWidgetItem()
            tilde.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            tilde.setCheckState(Qt.Unchecked)
            self._tabla_listas.setItem(fila, COLUMNA_LISTA_TILDE, tilde)
            self._tabla_listas.setItem(
                fila, COLUMNA_LISTA_CRISTAL,
                QTableWidgetItem(linea["tipo_cristal_nombre"] or linea["descripcion"] or ""),
            )
            self._tabla_listas.setItem(fila, COLUMNA_LISTA_CANTIDAD, QTableWidgetItem(str(linea["cantidad"])))
            graduacion = linea["graduacion_recibida"] or linea["graduacion_solicitada"] or ""
            self._tabla_listas.setItem(fila, COLUMNA_LISTA_GRADUACION, QTableWidgetItem(graduacion))

            precio_sugerido = ""
            if linea["tipo_cristal_id"] is not None:
                tipo_cristal = obtener_tipo_cristal(self.conexion, linea["tipo_cristal_id"])
                if tipo_cristal is not None:
                    precio_sugerido = str(precio_unitario(tipo_cristal))
            item_precio = QTableWidgetItem(precio_sugerido)
            item_precio.setFlags(item_precio.flags() | Qt.ItemIsEditable)
            self._tabla_listas.setItem(fila, COLUMNA_LISTA_PRECIO, item_precio)
        ajustar_columnas(self._tabla_listas)

    def _items_tildados(self) -> list[ItemEntrega]:
        items = []
        for fila, linea_id in enumerate(self._ids_listas):
            if self._tabla_listas.item(fila, COLUMNA_LISTA_TILDE).checkState() != Qt.Checked:
                continue
            texto_precio = self._tabla_listas.item(fila, COLUMNA_LISTA_PRECIO).text().strip()
            precio_unitario_linea = None
            if texto_precio:
                try:
                    precio_unitario_linea = Decimal(texto_precio.replace(",", "."))
                except InvalidOperation:
                    raise ValueError(f"El precio \"{texto_precio}\" no es un número válido.")
            items.append(ItemEntrega(linea_id, precio_unitario=precio_unitario_linea))
        return items

    def _generar_comprobante(self) -> None:
        if self._cliente_id is None:
            QMessageBox.warning(self, "Nada seleccionado", "Elegí un cliente.")
            return
        try:
            items = self._items_tildados()
        except ValueError as error:
            QMessageBox.warning(self, "Precio inválido", str(error))
            return
        if not items:
            QMessageBox.warning(self, "Nada tildado", "Tildá al menos una línea para entregar.")
            return
        sucursal_id = self._campo_sucursal.currentData()
        if sucursal_id is None:
            QMessageBox.warning(self, "Falta la sucursal", "Este cliente no tiene ninguna sucursal activa.")
            return

        try:
            comprobante_id = generar_entrega(
                self.conexion, self._cliente_id, items,
                tipo_comprobante_id=self._campo_tipo.currentData(),
                numero=self._campo_numero.text(),
                fecha=self._campo_fecha.date().toString("yyyy-MM-dd"),
                sucursal_id=sucursal_id,
            )
        except NumeroDuplicadoError as error:
            respuesta = QMessageBox.question(self, "Número repetido", f"{error} ¿Continuar igual?")
            if respuesta != QMessageBox.Yes:
                return
            comprobante_id = generar_entrega(
                self.conexion, self._cliente_id, items,
                tipo_comprobante_id=self._campo_tipo.currentData(),
                numero=self._campo_numero.text(),
                fecha=self._campo_fecha.date().toString("yyyy-MM-dd"),
                sucursal_id=sucursal_id,
                forzar_numero_repetido=True,
            )
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo generar", str(error))
            return

        QMessageBox.information(
            self, "Entrega generada", f"Se generó el comprobante Nº {self._campo_numero.text()}."
        )
        self._cargar_combo_clientes()
