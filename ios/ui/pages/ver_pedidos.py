"""Pantalla Ver pedidos (plan de detalle de comprobantes, etapa 4): consulta
de todos los pedidos a proveedor, con filtro por proveedor, fecha y número
de pedido, listado a la izquierda y detalle de líneas a la derecha."""

from __future__ import annotations

import sqlite3
from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
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

from ios.data import proveedores as datos_proveedores
from ios.reports.formato import formato_fecha
from ios.reports.pdf_comun import abrir_pdf, ruta_pdf_automatica
from ios.reports.pedido_proveedor import generar_pdf_pedido_proveedor
from ios.services.pedidos_proveedor import listar_lineas_pedido, listar_pedidos
from ios.ui.widgets import ajustar_columnas

ETIQUETAS_ESTADO_PEDIDO = {"en_carga": "En carga", "realizado": "Realizado", "recibido": "Recibido"}
ETIQUETAS_ESTADO_LINEA = {
    "pedido": "Sin resolver",
    "recibido": "Recibida",
    "recibido_con_diferencia": "Recibida con diferencia",
    "pendiente": "Pendiente (se pide de nuevo)",
    "cancelado": "Cancelada",
    "entregado": "Entregada",
}

COLUMNA_NUMERO = 0
COLUMNA_PROVEEDOR = 1
COLUMNA_FECHA = 2
COLUMNA_ESTADO = 3

COLUMNA_REPO_CRISTAL = 0
COLUMNA_REPO_CANTIDAD = 1
COLUMNA_REPO_GRAD_SOLICITADA = 2
COLUMNA_REPO_ESTADO = 3

COLUMNA_ESP_CRISTAL = 0
COLUMNA_ESP_CLIENTE = 1
COLUMNA_ESP_CANTIDAD = 2
COLUMNA_ESP_GRAD_SOLICITADA = 3
COLUMNA_ESP_ESTADO = 4


class PaginaVerPedidos(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self._ids_listado: list[int] = []
        self._pedido_seleccionado_id: int | None = None

        layout_general = QVBoxLayout(self)

        filtros = QHBoxLayout()
        filtros.addWidget(QLabel("Proveedor"))
        self._campo_proveedor = QComboBox()
        self._campo_proveedor.currentIndexChanged.connect(self._cargar_listado)
        filtros.addWidget(self._campo_proveedor, stretch=1)

        filtros.addWidget(QLabel("Desde"))
        hoy = date.today()
        self._campo_desde = QDateEdit(QDate(hoy.year, hoy.month, 1))
        self._campo_desde.setCalendarPopup(True)
        self._campo_desde.dateChanged.connect(self._cargar_listado)
        filtros.addWidget(self._campo_desde)

        filtros.addWidget(QLabel("Hasta"))
        self._campo_hasta = QDateEdit(QDate.currentDate())
        self._campo_hasta.setCalendarPopup(True)
        self._campo_hasta.dateChanged.connect(self._cargar_listado)
        filtros.addWidget(self._campo_hasta)

        self._casilla_ver_todo = QCheckBox("Ver todo (sin filtro de fecha)")
        self._casilla_ver_todo.toggled.connect(self._cambio_ver_todo)
        filtros.addWidget(self._casilla_ver_todo)

        filtros.addWidget(QLabel("Número"))
        self._campo_numero = QLineEdit()
        self._campo_numero.setPlaceholderText("Nº de pedido")
        self._campo_numero.setMaximumWidth(80)
        self._campo_numero.textChanged.connect(self._cargar_listado)
        filtros.addWidget(self._campo_numero)

        layout_general.addLayout(filtros)

        columnas = QHBoxLayout()

        self._tabla_listado = QTableWidget(0, 4)
        self._tabla_listado.setHorizontalHeaderLabels(["Nº", "Proveedor", "Fecha", "Estado"])
        self._tabla_listado.verticalHeader().setVisible(False)
        self._tabla_listado.setSelectionBehavior(QTableWidget.SelectRows)
        self._tabla_listado.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla_listado.itemSelectionChanged.connect(self._al_elegir_pedido)
        columnas.addWidget(self._tabla_listado, stretch=1)

        columna_detalle = QVBoxLayout()
        columna_detalle.addWidget(QLabel("Reposición"))
        self._tabla_detalle_reposicion = QTableWidget(0, 4)
        self._tabla_detalle_reposicion.setHorizontalHeaderLabels(
            ["Cristal", "Cantidad", "Graduación solicitada", "Estado"]
        )
        self._tabla_detalle_reposicion.verticalHeader().setVisible(False)
        self._tabla_detalle_reposicion.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla_detalle_reposicion.setSortingEnabled(True)
        columna_detalle.addWidget(self._tabla_detalle_reposicion)

        columna_detalle.addWidget(QLabel("Especiales"))
        self._tabla_detalle_especiales = QTableWidget(0, 5)
        self._tabla_detalle_especiales.setHorizontalHeaderLabels(
            ["Cristal/Descripción", "Cliente", "Cantidad", "Graduación solicitada", "Estado"]
        )
        self._tabla_detalle_especiales.verticalHeader().setVisible(False)
        self._tabla_detalle_especiales.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla_detalle_especiales.setSortingEnabled(True)
        columna_detalle.addWidget(self._tabla_detalle_especiales)
        columnas.addLayout(columna_detalle, stretch=2)

        layout_general.addLayout(columnas, stretch=1)

        pie = QHBoxLayout()
        pie.addStretch(1)
        self._boton_generar_pdf = QPushButton("Generar PDF")
        self._boton_generar_pdf.setEnabled(False)
        self._boton_generar_pdf.clicked.connect(self._generar_pdf)
        pie.addWidget(self._boton_generar_pdf)
        layout_general.addLayout(pie)

        self.actualizar()

    # --- carga de datos ---

    def actualizar(self) -> None:
        self._cargar_combo_proveedores()

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar

    def _cargar_combo_proveedores(self) -> None:
        proveedor_actual = self._campo_proveedor.currentData()
        self._campo_proveedor.blockSignals(True)
        self._campo_proveedor.clear()
        self._campo_proveedor.addItem("Todos", None)
        for proveedor in datos_proveedores.listar_proveedores(self.conexion):
            self._campo_proveedor.addItem(proveedor["nombre"], proveedor["id"])
        indice = self._campo_proveedor.findData(proveedor_actual)
        self._campo_proveedor.setCurrentIndex(max(indice, 0))
        self._campo_proveedor.blockSignals(False)
        self._cargar_listado()

    def _cambio_ver_todo(self, marcado: bool) -> None:
        self._campo_desde.setEnabled(not marcado)
        self._campo_hasta.setEnabled(not marcado)
        self._cargar_listado()

    # --- listado (izquierda) ---

    def _cargar_listado(self) -> None:
        proveedor_id = self._campo_proveedor.currentData()
        sin_fecha = self._casilla_ver_todo.isChecked()
        fecha_desde = None if sin_fecha else self._campo_desde.date().toString("yyyy-MM-dd")
        fecha_hasta = None if sin_fecha else self._campo_hasta.date().toString("yyyy-MM-dd")
        texto_numero = self._campo_numero.text().strip()
        numero = int(texto_numero) if texto_numero.isdigit() else None

        pedidos = listar_pedidos(
            self.conexion, proveedor_id=proveedor_id,
            fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, numero=numero,
        )

        self._ids_listado = [p["id"] for p in pedidos]
        self._tabla_listado.setRowCount(len(pedidos))
        for fila, pedido in enumerate(pedidos):
            self._tabla_listado.setItem(fila, COLUMNA_NUMERO, QTableWidgetItem(str(pedido["id"])))
            self._tabla_listado.setItem(fila, COLUMNA_PROVEEDOR, QTableWidgetItem(pedido["proveedor_nombre"]))
            self._tabla_listado.setItem(fila, COLUMNA_FECHA, QTableWidgetItem(formato_fecha(pedido["fecha"])))
            self._tabla_listado.setItem(
                fila, COLUMNA_ESTADO,
                QTableWidgetItem(ETIQUETAS_ESTADO_PEDIDO.get(pedido["estado"], pedido["estado"])),
            )
        ajustar_columnas(self._tabla_listado)
        self._tabla_detalle_reposicion.setRowCount(0)
        self._tabla_detalle_especiales.setRowCount(0)
        self._pedido_seleccionado_id = None
        self._boton_generar_pdf.setEnabled(False)

    # --- detalle (derecha) ---

    def _al_elegir_pedido(self) -> None:
        fila = self._tabla_listado.currentRow()
        if fila < 0 or fila >= len(self._ids_listado):
            self._pedido_seleccionado_id = None
            self._boton_generar_pdf.setEnabled(False)
            self._tabla_detalle_reposicion.setRowCount(0)
            self._tabla_detalle_especiales.setRowCount(0)
            return
        pedido_id = self._ids_listado[fila]
        self._pedido_seleccionado_id = pedido_id
        self._boton_generar_pdf.setEnabled(True)
        lineas = listar_lineas_pedido(self.conexion, pedido_id)
        reposicion = [l for l in lineas if l["origen"] == "reposicion"]
        especiales = [l for l in lineas if l["origen"] == "especial"]

        self._tabla_detalle_reposicion.setSortingEnabled(False)
        self._tabla_detalle_reposicion.setRowCount(len(reposicion))
        for fila_linea, linea in enumerate(reposicion):
            self._tabla_detalle_reposicion.setItem(
                fila_linea, COLUMNA_REPO_CRISTAL,
                QTableWidgetItem(linea["tipo_cristal_nombre"] or linea["descripcion"] or ""),
            )
            self._tabla_detalle_reposicion.setItem(
                fila_linea, COLUMNA_REPO_CANTIDAD, QTableWidgetItem(str(linea["cantidad"]))
            )
            self._tabla_detalle_reposicion.setItem(
                fila_linea, COLUMNA_REPO_GRAD_SOLICITADA,
                QTableWidgetItem(linea["graduacion_solicitada"] or ""),
            )
            self._tabla_detalle_reposicion.setItem(
                fila_linea, COLUMNA_REPO_ESTADO,
                QTableWidgetItem(ETIQUETAS_ESTADO_LINEA.get(linea["estado"], linea["estado"])),
            )
        self._tabla_detalle_reposicion.setSortingEnabled(True)
        ajustar_columnas(self._tabla_detalle_reposicion)

        self._tabla_detalle_especiales.setSortingEnabled(False)
        self._tabla_detalle_especiales.setRowCount(len(especiales))
        for fila_linea, linea in enumerate(especiales):
            self._tabla_detalle_especiales.setItem(
                fila_linea, COLUMNA_ESP_CRISTAL,
                QTableWidgetItem(linea["tipo_cristal_nombre"] or linea["descripcion"] or ""),
            )
            self._tabla_detalle_especiales.setItem(
                fila_linea, COLUMNA_ESP_CLIENTE, QTableWidgetItem(linea["cliente_nombre"] or "")
            )
            self._tabla_detalle_especiales.setItem(
                fila_linea, COLUMNA_ESP_CANTIDAD, QTableWidgetItem(str(linea["cantidad"]))
            )
            self._tabla_detalle_especiales.setItem(
                fila_linea, COLUMNA_ESP_GRAD_SOLICITADA,
                QTableWidgetItem(linea["graduacion_solicitada"] or ""),
            )
            self._tabla_detalle_especiales.setItem(
                fila_linea, COLUMNA_ESP_ESTADO,
                QTableWidgetItem(ETIQUETAS_ESTADO_LINEA.get(linea["estado"], linea["estado"])),
            )
        self._tabla_detalle_especiales.setSortingEnabled(True)
        ajustar_columnas(self._tabla_detalle_especiales)

    def _generar_pdf(self) -> None:
        if self._pedido_seleccionado_id is None:
            QMessageBox.warning(self, "Nada seleccionado", "Elegí un pedido de la lista.")
            return
        fila = self._tabla_listado.currentRow()
        proveedor_nombre = self._tabla_listado.item(fila, COLUMNA_PROVEEDOR).text()
        fecha = self._tabla_listado.item(fila, COLUMNA_FECHA).text().replace("/", "-")
        ruta = ruta_pdf_automatica(
            f"Pedido {self._pedido_seleccionado_id} - {proveedor_nombre} - {fecha}.pdf",
            subcarpeta="Pedidos a proveedor",
        )
        generar_pdf_pedido_proveedor(self.conexion, self._pedido_seleccionado_id, ruta)
        abrir_pdf(ruta)
