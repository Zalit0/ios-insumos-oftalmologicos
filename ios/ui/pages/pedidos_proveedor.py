"""Pantalla Pedidos a proveedor (plan de detalle de comprobantes, etapa 4):
armar el pedido "en carga" de un proveedor — nunca hay más de uno a la vez
por proveedor — con dos fuentes de líneas: reposición (se generan solas
desde lo vendido de stock) y especiales (cargadas a mano, cristales que no
hay en stock). Una vez armado, "Marcar realizado" lo manda al proveedor; de
ahí en adelante se recibe desde la pantalla Recepción de pedidos, y se
consulta cualquier pedido viejo desde Ver pedidos."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, QEvent, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGroupBox,
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
from ios.data import proveedores as datos_proveedores
from ios.data import tipos_cristal as datos_tipos_cristal
from ios.data.pedidos_proveedor import obtener_pedido
from ios.domain.graduacion import formatear_graduacion
from ios.reports.formato import formato_fecha
from ios.reports.pdf_comun import abrir_pdf, ruta_pdf_automatica
from ios.reports.pedido_proveedor import generar_pdf_pedido_proveedor
from ios.services.pedidos_proveedor import (
    agregar_linea_especial,
    alta_pedido,
    generar_lineas_reposicion,
    listar_lineas_pedido,
    marcar_pedido_realizado,
    pedido_en_carga,
)
from ios.ui.widgets import CampoEntero, CampoGraduacion, ajustar_columnas

COLUMNA_REPO_CRISTAL = 0
COLUMNA_REPO_CANTIDAD = 1
COLUMNA_REPO_GRAD_SOLICITADA = 2

COLUMNA_ESP_CRISTAL = 0
COLUMNA_ESP_CLIENTE = 1
COLUMNA_ESP_CANTIDAD = 2
COLUMNA_ESP_GRAD_SOLICITADA = 3


class PaginaPedidosProveedor(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self._pedido_id: int | None = None

        layout_general = QVBoxLayout(self)

        fila_pedido = QHBoxLayout()
        fila_pedido.addWidget(QLabel("Proveedor"))
        self._campo_proveedor = QComboBox()
        self._campo_proveedor.currentIndexChanged.connect(self._al_elegir_proveedor)
        fila_pedido.addWidget(self._campo_proveedor, stretch=1)
        self._etiqueta_pedido = QLabel("Sin pedido en carga")
        fila_pedido.addWidget(self._etiqueta_pedido, stretch=1)
        boton_nuevo_pedido = QPushButton("Nuevo pedido")
        boton_nuevo_pedido.clicked.connect(self._nuevo_pedido)
        fila_pedido.addWidget(boton_nuevo_pedido)
        self._boton_marcar_realizado = QPushButton("Marcar realizado")
        self._boton_marcar_realizado.clicked.connect(self._marcar_pedido_realizado)
        fila_pedido.addWidget(self._boton_marcar_realizado)
        layout_general.addLayout(fila_pedido)

        fila_generadores = QHBoxLayout()

        grupo_reposicion = QGroupBox("Generar reposición")
        formulario_reposicion = QFormLayout(grupo_reposicion)
        hoy = date.today()
        self._campo_repo_desde = QDateEdit(QDate(hoy.year, hoy.month, 1))
        self._campo_repo_desde.setCalendarPopup(True)
        self._campo_repo_hasta = QDateEdit(QDate.currentDate())
        self._campo_repo_hasta.setCalendarPopup(True)
        formulario_reposicion.addRow("Desde", self._campo_repo_desde)
        formulario_reposicion.addRow("Hasta", self._campo_repo_hasta)
        boton_generar_reposicion = QPushButton("Generar reposición")
        boton_generar_reposicion.clicked.connect(self._generar_reposicion)
        formulario_reposicion.addRow(boton_generar_reposicion)
        fila_generadores.addWidget(grupo_reposicion, stretch=1)

        grupo_especial = QGroupBox("Agregar línea especial")
        formulario_especial = QFormLayout(grupo_especial)
        self._campo_especial_tipo = QComboBox()
        formulario_especial.addRow("Cristal", self._campo_especial_tipo)
        self._campo_especial_descripcion = QLineEdit()
        self._campo_especial_descripcion.setPlaceholderText("Descripción (si no está en el catálogo)")
        formulario_especial.addRow("Descripción", self._campo_especial_descripcion)
        self._campo_especial_cliente = QComboBox()
        formulario_especial.addRow("Cliente", self._campo_especial_cliente)
        fila_graduacion_especial = QHBoxLayout()
        fila_graduacion_especial.addWidget(QLabel("Esférico"))
        self._campo_especial_esferico = CampoGraduacion()
        self._campo_especial_esferico.setRange(-30, 30)
        self._campo_especial_esferico.setSingleStep(0.25)
        self._campo_especial_esferico.setDecimals(2)
        fila_graduacion_especial.addWidget(self._campo_especial_esferico)
        fila_graduacion_especial.addWidget(QLabel("Cilíndrico"))
        self._campo_especial_cilindrico = CampoGraduacion()
        self._campo_especial_cilindrico.setRange(-30, 30)
        self._campo_especial_cilindrico.setSingleStep(0.25)
        self._campo_especial_cilindrico.setDecimals(2)
        fila_graduacion_especial.addWidget(self._campo_especial_cilindrico)
        formulario_especial.addRow("Graduación solicitada", fila_graduacion_especial)
        self._campo_especial_cantidad = CampoEntero()
        self._campo_especial_cantidad.setRange(1, 999)
        self._campo_especial_cantidad.setValue(1)
        formulario_especial.addRow("Cantidad", self._campo_especial_cantidad)
        boton_agregar_especial = QPushButton("Agregar línea especial")
        boton_agregar_especial.clicked.connect(self._agregar_linea_especial)
        formulario_especial.addRow(boton_agregar_especial)
        fila_generadores.addWidget(grupo_especial, stretch=1)

        layout_general.addLayout(fila_generadores)

        for campo in self._campos_con_enter_especial():
            campo.installEventFilter(self)

        layout_general.addWidget(QLabel("Reposición del pedido en carga"))
        self._tabla_reposicion = QTableWidget(0, 3)
        self._tabla_reposicion.setHorizontalHeaderLabels(["Cristal", "Cantidad", "Graduación solicitada"])
        self._tabla_reposicion.verticalHeader().setVisible(False)
        self._tabla_reposicion.setSelectionBehavior(QTableWidget.SelectRows)
        self._tabla_reposicion.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla_reposicion.setSortingEnabled(True)
        layout_general.addWidget(self._tabla_reposicion, stretch=1)

        layout_general.addWidget(QLabel("Especiales del pedido en carga"))
        self._tabla_especiales = QTableWidget(0, 4)
        self._tabla_especiales.setHorizontalHeaderLabels(
            ["Cristal/Descripción", "Cliente", "Cantidad", "Graduación solicitada"]
        )
        self._tabla_especiales.verticalHeader().setVisible(False)
        self._tabla_especiales.setSelectionBehavior(QTableWidget.SelectRows)
        self._tabla_especiales.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla_especiales.setSortingEnabled(True)
        layout_general.addWidget(self._tabla_especiales, stretch=1)

        self.actualizar()

    # --- carga de datos ---

    def actualizar(self) -> None:
        self._cargar_combo_proveedores()
        self._cargar_combo_tipos_cristal()
        self._cargar_combo_clientes()

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar

    def _cargar_combo_proveedores(self) -> None:
        proveedor_actual = self._campo_proveedor.currentData()
        self._campo_proveedor.blockSignals(True)
        self._campo_proveedor.clear()
        for proveedor in datos_proveedores.listar_proveedores(self.conexion):
            self._campo_proveedor.addItem(proveedor["nombre"], proveedor["id"])
        indice = self._campo_proveedor.findData(proveedor_actual)
        self._campo_proveedor.setCurrentIndex(max(indice, 0))
        self._campo_proveedor.blockSignals(False)
        self._al_elegir_proveedor()

    def _cargar_combo_tipos_cristal(self) -> None:
        self._campo_especial_tipo.clear()
        self._campo_especial_tipo.addItem("(ninguno, usar descripción)", None)
        for tipo in datos_tipos_cristal.listar_tipos_cristal(self.conexion):
            self._campo_especial_tipo.addItem(tipo["nombre"], tipo["id"])

    def _cargar_combo_clientes(self) -> None:
        self._campo_especial_cliente.clear()
        self._campo_especial_cliente.addItem("(sin cliente)", None)
        for cliente in datos_clientes.listar_clientes(self.conexion):
            self._campo_especial_cliente.addItem(cliente["nombre"], cliente["id"])

    # --- proveedor / pedido en carga ---

    def _al_elegir_proveedor(self) -> None:
        proveedor_id = self._campo_proveedor.currentData()
        pedido = pedido_en_carga(self.conexion, proveedor_id) if proveedor_id is not None else None
        self._pedido_id = pedido["id"] if pedido is not None else None
        if pedido is not None:
            self._etiqueta_pedido.setText(f"Pedido del {formato_fecha(pedido['fecha'])} — en carga")
        else:
            self._etiqueta_pedido.setText("Sin pedido en carga")
        self._boton_marcar_realizado.setEnabled(self._pedido_id is not None)
        self._cargar_tabla()

    def _nuevo_pedido(self) -> None:
        proveedor_id = self._campo_proveedor.currentData()
        if proveedor_id is None:
            QMessageBox.warning(self, "Falta el proveedor", "Elegí (o cargá) un proveedor primero.")
            return
        alta_pedido(self.conexion, proveedor_id, date.today().isoformat())
        self._al_elegir_proveedor()

    def _marcar_pedido_realizado(self) -> None:
        if self._pedido_id is None:
            return
        respuesta = QMessageBox.question(
            self, "Marcar realizado",
            "¿Marcar este pedido como realizado? Se genera el PDF para mandarle al proveedor, "
            "y ya no se le van a poder agregar más líneas; se recibe desde la pantalla "
            "Recepción de pedidos.",
        )
        if respuesta != QMessageBox.Yes:
            return
        pedido_id = self._pedido_id
        marcar_pedido_realizado(self.conexion, pedido_id)
        pedido = obtener_pedido(self.conexion, pedido_id)
        fecha = formato_fecha(pedido["fecha"]).replace("/", "-")
        proveedor_nombre = self._campo_proveedor.currentText()
        ruta = ruta_pdf_automatica(
            f"Pedido {pedido_id} - {proveedor_nombre} - {fecha}.pdf", subcarpeta="Pedidos a proveedor"
        )
        generar_pdf_pedido_proveedor(self.conexion, pedido_id, ruta)
        abrir_pdf(ruta)
        self._al_elegir_proveedor()

    # --- Enter avanza de campo en la línea especial; en el último, agrega ---

    def _campos_con_enter_especial(self) -> list[QWidget]:
        return [
            self._campo_especial_tipo, self._campo_especial_descripcion, self._campo_especial_cliente,
            self._campo_especial_esferico, self._campo_especial_cilindrico, self._campo_especial_cantidad,
        ]

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            orden = self._campos_con_enter_especial()
            if obj in orden:
                indice = orden.index(obj)
                if indice + 1 < len(orden):
                    siguiente = orden[indice + 1]
                    siguiente.setFocus()
                    if hasattr(siguiente, "selectAll"):
                        siguiente.selectAll()
                else:
                    self._agregar_linea_especial()
                return True
        return super().eventFilter(obj, event)

    # --- reposición / especial ---

    def _generar_reposicion(self) -> None:
        if self._pedido_id is None:
            QMessageBox.warning(self, "Sin pedido", "Elegí o creá un pedido primero.")
            return
        fecha_desde = self._campo_repo_desde.date().toString("yyyy-MM-dd")
        fecha_hasta = self._campo_repo_hasta.date().toString("yyyy-MM-dd")
        resultado = generar_lineas_reposicion(self.conexion, self._pedido_id, fecha_desde, fecha_hasta)
        self._cargar_tabla()
        mensaje = f"Se agregaron {resultado.lineas_agregadas} línea(s) de reposición."
        if resultado.ajustes:
            detalle_ajustes = "\n".join(
                f"- {ajuste.tipo_cristal_nombre} {ajuste.graduacion}: se descontaron "
                f"{ajuste.cantidad_descontada} unidad(es) ya repuestas por una devolución anterior."
                for ajuste in resultado.ajustes
            )
            mensaje += f"\n\nAjustes por devoluciones ya repuestas:\n{detalle_ajustes}"
        QMessageBox.information(self, "Listo", mensaje)

    def _agregar_linea_especial(self) -> None:
        if self._pedido_id is None:
            QMessageBox.warning(self, "Sin pedido", "Elegí o creá un pedido primero.")
            return
        graduacion_solicitada = formatear_graduacion(
            Decimal(str(self._campo_especial_esferico.value())),
            Decimal(str(self._campo_especial_cilindrico.value())),
        )
        try:
            agregar_linea_especial(
                self.conexion, self._pedido_id,
                cantidad=self._campo_especial_cantidad.value(),
                tipo_cristal_id=self._campo_especial_tipo.currentData(),
                descripcion=self._campo_especial_descripcion.text().strip() or None,
                cliente_id=self._campo_especial_cliente.currentData(),
                graduacion_solicitada=graduacion_solicitada,
            )
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo agregar", str(error))
            return
        self._campo_especial_tipo.setCurrentIndex(0)
        self._campo_especial_descripcion.clear()
        self._campo_especial_esferico.setValue(0)
        self._campo_especial_cilindrico.setValue(0)
        self._campo_especial_cantidad.setValue(1)
        self._cargar_tabla()

    # --- tablas de líneas ---

    def _cargar_tabla(self) -> None:
        lineas = listar_lineas_pedido(self.conexion, self._pedido_id) if self._pedido_id else []
        reposicion = [l for l in lineas if l["origen"] == "reposicion"]
        especiales = [l for l in lineas if l["origen"] == "especial"]

        self._tabla_reposicion.setSortingEnabled(False)
        self._tabla_reposicion.setRowCount(len(reposicion))
        for fila, linea in enumerate(reposicion):
            item_cristal = QTableWidgetItem(linea["tipo_cristal_nombre"] or linea["descripcion"] or "")
            item_cristal.setData(Qt.UserRole, linea["id"])
            self._tabla_reposicion.setItem(fila, COLUMNA_REPO_CRISTAL, item_cristal)
            self._tabla_reposicion.setItem(
                fila, COLUMNA_REPO_CANTIDAD, QTableWidgetItem(str(linea["cantidad"]))
            )
            self._tabla_reposicion.setItem(
                fila, COLUMNA_REPO_GRAD_SOLICITADA, QTableWidgetItem(linea["graduacion_solicitada"] or "")
            )
        self._tabla_reposicion.setSortingEnabled(True)
        ajustar_columnas(self._tabla_reposicion)

        self._tabla_especiales.setSortingEnabled(False)
        self._tabla_especiales.setRowCount(len(especiales))
        for fila, linea in enumerate(especiales):
            item_cristal = QTableWidgetItem(linea["tipo_cristal_nombre"] or linea["descripcion"] or "")
            item_cristal.setData(Qt.UserRole, linea["id"])
            self._tabla_especiales.setItem(fila, COLUMNA_ESP_CRISTAL, item_cristal)
            self._tabla_especiales.setItem(
                fila, COLUMNA_ESP_CLIENTE, QTableWidgetItem(linea["cliente_nombre"] or "")
            )
            self._tabla_especiales.setItem(
                fila, COLUMNA_ESP_CANTIDAD, QTableWidgetItem(str(linea["cantidad"]))
            )
            self._tabla_especiales.setItem(
                fila, COLUMNA_ESP_GRAD_SOLICITADA, QTableWidgetItem(linea["graduacion_solicitada"] or "")
            )
        self._tabla_especiales.setSortingEnabled(True)
        ajustar_columnas(self._tabla_especiales)
