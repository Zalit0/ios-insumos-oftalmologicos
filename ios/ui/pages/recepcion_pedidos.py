"""Pantalla Recepción de pedidos (plan de detalle de comprobantes, etapa 4/5.3):
resolver cristal por cristal si llegó, llegó distinto, quedó pendiente (se
pide de nuevo) o se cancela (no se vuelve a pedir), separando las líneas de
reposición de las especiales — cada fila tiene sus propios botones de acción
(sin seleccionar una fila aparte), recién cuando no queda ninguna línea sin
resolver se puede cerrar el pedido, lo que también ofrece cargar la factura
de compra asociada."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QFormLayout,
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
from ios.domain.calculos import calcular_iva_discriminado
from ios.domain.graduacion import formatear_graduacion, parsear_graduacion
from ios.reports.formato import formato_fecha
from ios.services import compras as servicio_compras
from ios.services import configuracion as servicio_configuracion
from ios.services.pedidos_proveedor import (
    listar_lineas_pedido,
    listar_pedidos,
    marcar_linea_cancelada,
    marcar_linea_pendiente,
    marcar_linea_recibida,
    marcar_pedido_recibido,
    pedido_en_carga,
    pedido_listo_para_cerrar,
)
from ios.ui.widgets import CampoDecimal, CampoGraduacion, ajustar_columnas

ETIQUETAS_ESTADO_LINEA = {
    "pedido": "Sin resolver",
    "recibido": "Recibida",
    "recibido_con_diferencia": "Recibida con diferencia",
    "pendiente": "Pendiente (se pide de nuevo)",
    "cancelado": "Cancelada",
    "entregado": "Entregada",
}

TASAS_IVA_COMPRA = [("21%", Decimal("21")), ("10,5%", Decimal("10.5")), ("0%", Decimal("0"))]

COLUMNA_REPO_CRISTAL = 0
COLUMNA_REPO_CANTIDAD = 1
COLUMNA_REPO_GRAD_SOLICITADA = 2
COLUMNA_REPO_GRAD_RECIBIDA = 3
COLUMNA_REPO_ESTADO = 4
COLUMNA_REPO_ACCIONES = 5

COLUMNA_ESP_CRISTAL = 0
COLUMNA_ESP_CLIENTE = 1
COLUMNA_ESP_CANTIDAD = 2
COLUMNA_ESP_GRAD_SOLICITADA = 3
COLUMNA_ESP_GRAD_RECIBIDA = 4
COLUMNA_ESP_ESTADO = 5
COLUMNA_ESP_ACCIONES = 6


class _DialogoGraduacionRecibida(QDialog):
    """Graduación con la que llegó una línea — se abre al tocar "Recibida"
    en la fila, prellenada con la graduación solicitada: si el usuario la
    deja igual, llegó igual; si la cambia, llegó distinto. La distinción
    entre "recibida" y "recibida con diferencia" la calcula sola
    ``marcar_linea_recibida`` comparando contra lo solicitado — este modal
    solo junta el dato, no decide el estado."""

    def __init__(self, graduacion_solicitada: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Graduación recibida")

        formulario = QFormLayout(self)
        esferico, cilindrico = parsear_graduacion(graduacion_solicitada or "")
        self.campo_esferico = CampoGraduacion()
        self.campo_esferico.setRange(-30, 30)
        self.campo_esferico.setSingleStep(0.25)
        self.campo_esferico.setDecimals(2)
        self.campo_esferico.setValue(float(esferico))
        formulario.addRow("Esférico", self.campo_esferico)
        self.campo_cilindrico = CampoGraduacion()
        self.campo_cilindrico.setRange(-30, 30)
        self.campo_cilindrico.setSingleStep(0.25)
        self.campo_cilindrico.setDecimals(2)
        self.campo_cilindrico.setValue(float(cilindrico))
        formulario.addRow("Cilíndrico", self.campo_cilindrico)

        pie = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(self.reject)
        pie.addWidget(boton_cancelar)
        boton_confirmar = QPushButton("Confirmar")
        boton_confirmar.clicked.connect(self.accept)
        pie.addWidget(boton_confirmar)
        formulario.addRow(pie)

    def graduacion_recibida(self) -> str:
        return formatear_graduacion(
            Decimal(str(self.campo_esferico.value())),
            Decimal(str(self.campo_cilindrico.value())),
        )


class _DialogoCompraDesdePedido(QDialog):
    """Factura de compra asociada al pedido que se acaba de marcar
    recibido (plan de detalle de comprobantes, etapa 5.3) — mismos campos
    que la pestaña Compras de "Compras y proveedores", con el proveedor ya
    fijo porque es el de este pedido."""

    def __init__(
        self, conexion: sqlite3.Connection, proveedor_id: int, proveedor_nombre: str,
        pedido_id: int, parent=None,
    ) -> None:
        super().__init__(parent)
        self.conexion = conexion
        self.proveedor_id = proveedor_id
        self.pedido_id = pedido_id
        self.setWindowTitle(f"Factura de compra — {proveedor_nombre}")

        formulario = QFormLayout(self)
        formulario.addRow("Proveedor", QLabel(proveedor_nombre))
        self.campo_numero = QLineEdit()
        formulario.addRow("Nº factura", self.campo_numero)
        self.campo_fecha = QDateEdit(QDate.currentDate())
        self.campo_fecha.setCalendarPopup(True)
        formulario.addRow("Fecha", self.campo_fecha)
        self.campo_monto = CampoDecimal()
        self.campo_monto.setRange(0, 99_999_999)
        self.campo_monto.setDecimals(2)
        self.campo_monto.valueChanged.connect(self._recalcular_iva)
        formulario.addRow("Monto (con IVA)", self.campo_monto)
        self.campo_tasa_iva = QComboBox()
        for etiqueta, _tasa in TASAS_IVA_COMPRA:
            self.campo_tasa_iva.addItem(etiqueta)
        self.campo_tasa_iva.currentIndexChanged.connect(self._recalcular_iva)
        formulario.addRow("Tasa IVA", self.campo_tasa_iva)
        self.campo_iva = CampoDecimal()
        self.campo_iva.setRange(0, 99_999_999)
        self.campo_iva.setDecimals(2)
        formulario.addRow("IVA", self.campo_iva)

        pie = QHBoxLayout()
        boton_mas_tarde = QPushButton("Cargarla más tarde")
        boton_mas_tarde.clicked.connect(self.reject)
        pie.addWidget(boton_mas_tarde)
        boton_guardar = QPushButton("Guardar factura")
        boton_guardar.clicked.connect(self._guardar)
        pie.addWidget(boton_guardar)
        formulario.addRow(pie)

        self._seleccionar_tasa_iva_por_defecto()
        self._recalcular_iva()

    def _tasa_iva_elegida(self) -> Decimal:
        return TASAS_IVA_COMPRA[self.campo_tasa_iva.currentIndex()][1]

    def _seleccionar_tasa_iva_por_defecto(self) -> None:
        tasa_default = servicio_configuracion.obtener_configuracion(self.conexion)["iva_pct"]
        for indice, (_etiqueta, tasa) in enumerate(TASAS_IVA_COMPRA):
            if tasa == tasa_default:
                self.campo_tasa_iva.setCurrentIndex(indice)
                return
        self.campo_tasa_iva.setCurrentIndex(0)

    def _recalcular_iva(self) -> None:
        configuracion = servicio_configuracion.obtener_configuracion(self.conexion)
        monto = Decimal(str(self.campo_monto.value()))
        iva = calcular_iva_discriminado(
            monto, True, self._tasa_iva_elegida(), configuracion["redondeo_decimales"]
        )
        self.campo_iva.blockSignals(True)
        self.campo_iva.setValue(float(iva))
        self.campo_iva.blockSignals(False)

    def _guardar(self) -> None:
        try:
            servicio_compras.alta_compra(
                self.conexion, self.proveedor_id,
                self.campo_fecha.date().toString("yyyy-MM-dd"),
                self.campo_numero.text().strip(),
                Decimal(str(self.campo_monto.value())),
                tasa_iva=self._tasa_iva_elegida(),
                iva=Decimal(str(self.campo_iva.value())),
                pedido_id=self.pedido_id,
            )
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return
        self.accept()


class PaginaRecepcionPedidos(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self._pedido_id: int | None = None
        self._lineas_cargadas: list[sqlite3.Row] = []

        layout_general = QVBoxLayout(self)

        fila_pedido = QHBoxLayout()
        fila_pedido.addWidget(QLabel("Proveedor"))
        self._campo_proveedor = QComboBox()
        self._campo_proveedor.currentIndexChanged.connect(self._al_elegir_proveedor)
        fila_pedido.addWidget(self._campo_proveedor, stretch=1)
        fila_pedido.addWidget(QLabel("Pedido realizado"))
        self._campo_pedido = QComboBox()
        self._campo_pedido.currentIndexChanged.connect(self._al_elegir_pedido)
        fila_pedido.addWidget(self._campo_pedido, stretch=1)
        self._boton_marcar_recibido = QPushButton("Marcar pedido recibido")
        self._boton_marcar_recibido.clicked.connect(self._marcar_pedido_recibido)
        fila_pedido.addWidget(self._boton_marcar_recibido)
        layout_general.addLayout(fila_pedido)

        layout_general.addWidget(QLabel("Reposición"))
        self._tabla_reposicion = QTableWidget(0, 6)
        self._tabla_reposicion.setHorizontalHeaderLabels(
            ["Cristal", "Cantidad", "Graduación solicitada", "Graduación recibida", "Estado", "Acciones"]
        )
        self._tabla_reposicion.verticalHeader().setVisible(False)
        self._tabla_reposicion.setSelectionBehavior(QTableWidget.SelectRows)
        self._tabla_reposicion.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla_reposicion.setSortingEnabled(True)
        layout_general.addWidget(self._tabla_reposicion, stretch=1)

        layout_general.addWidget(QLabel("Especiales"))
        self._tabla_especiales = QTableWidget(0, 7)
        self._tabla_especiales.setHorizontalHeaderLabels(
            ["Cristal/Descripción", "Cliente", "Cantidad", "Graduación solicitada",
             "Graduación recibida", "Estado", "Acciones"]
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

    # --- proveedor / pedido realizado ---

    def _al_elegir_proveedor(self) -> None:
        proveedor_id = self._campo_proveedor.currentData()
        self._campo_pedido.blockSignals(True)
        self._campo_pedido.clear()
        if proveedor_id is not None:
            for pedido in listar_pedidos(self.conexion, proveedor_id=proveedor_id, estado="realizado"):
                self._campo_pedido.addItem(f"Pedido del {formato_fecha(pedido['fecha'])}", pedido["id"])
        self._campo_pedido.blockSignals(False)
        self._al_elegir_pedido()

    def _al_elegir_pedido(self) -> None:
        self._pedido_id = self._campo_pedido.currentData()
        self._cargar_tabla()

    # --- acciones por línea (botones en la columna "Acciones" de cada fila) ---

    def _marcar_linea_recibida(self, linea_id: int) -> None:
        linea = next(l for l in self._lineas_cargadas if l["id"] == linea_id)
        dialogo = _DialogoGraduacionRecibida(linea["graduacion_solicitada"], self)
        if dialogo.exec() != QDialog.Accepted:
            return
        marcar_linea_recibida(self.conexion, linea_id, dialogo.graduacion_recibida())
        self._cargar_tabla()

    def _marcar_linea_pendiente(self, linea_id: int) -> None:
        marcar_linea_pendiente(self.conexion, linea_id)
        self._cargar_tabla()

    def _cancelar_linea(self, linea_id: int) -> None:
        marcar_linea_cancelada(self.conexion, linea_id)
        self._cargar_tabla()

    def _crear_widget_acciones(self, linea_id: int) -> QWidget:
        contenedor = QWidget()
        layout = QHBoxLayout(contenedor)
        layout.setContentsMargins(2, 0, 2, 0)
        boton_recibida = QPushButton("Recibida")
        boton_recibida.clicked.connect(lambda: self._marcar_linea_recibida(linea_id))
        layout.addWidget(boton_recibida)
        boton_pendiente = QPushButton("Pendiente")
        boton_pendiente.clicked.connect(lambda: self._marcar_linea_pendiente(linea_id))
        layout.addWidget(boton_pendiente)
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(lambda: self._cancelar_linea(linea_id))
        layout.addWidget(boton_cancelar)
        return contenedor

    def _marcar_pedido_recibido(self) -> None:
        if self._pedido_id is None:
            return

        proveedor_id = self._campo_proveedor.currentData()
        lineas = listar_lineas_pedido(self.conexion, self._pedido_id)
        pendientes = [l for l in lineas if l["estado"] == "pendiente"]
        fecha_nuevo_pedido = None

        if pendientes:
            existente = pedido_en_carga(self.conexion, proveedor_id)
            if existente is not None:
                pregunta = (
                    f"Quedan {len(pendientes)} línea(s) pendiente(s). Se van a agregar al pedido "
                    f"en carga del {formato_fecha(existente['fecha'])}. ¿Continuar?"
                )
            else:
                fecha_nuevo_pedido = date.today().isoformat()
                pregunta = (
                    f"Quedan {len(pendientes)} línea(s) pendiente(s) y no hay un pedido en carga "
                    f"para este proveedor: se va a crear uno nuevo para no perderlas de vista. "
                    f"¿Continuar?"
                )
        else:
            pregunta = "¿Marcar este pedido como recibido?"

        respuesta = QMessageBox.question(self, "Marcar recibido", pregunta)
        if respuesta != QMessageBox.Yes:
            return

        pedido_id = self._pedido_id
        marcar_pedido_recibido(self.conexion, pedido_id, fecha_nuevo_pedido)

        dialogo = _DialogoCompraDesdePedido(
            self.conexion, proveedor_id, self._campo_proveedor.currentText(), pedido_id, self,
        )
        dialogo.exec()

        self._al_elegir_proveedor()

    # --- tablas de líneas ---

    def _cargar_tabla(self) -> None:
        lineas = listar_lineas_pedido(self.conexion, self._pedido_id) if self._pedido_id else []
        self._lineas_cargadas = lineas

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
            self._tabla_reposicion.setItem(
                fila, COLUMNA_REPO_GRAD_RECIBIDA, QTableWidgetItem(linea["graduacion_recibida"] or "")
            )
            self._tabla_reposicion.setItem(
                fila, COLUMNA_REPO_ESTADO,
                QTableWidgetItem(ETIQUETAS_ESTADO_LINEA.get(linea["estado"], linea["estado"])),
            )
            self._tabla_reposicion.setCellWidget(
                fila, COLUMNA_REPO_ACCIONES, self._crear_widget_acciones(linea["id"])
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
            self._tabla_especiales.setItem(
                fila, COLUMNA_ESP_GRAD_RECIBIDA, QTableWidgetItem(linea["graduacion_recibida"] or "")
            )
            self._tabla_especiales.setItem(
                fila, COLUMNA_ESP_ESTADO,
                QTableWidgetItem(ETIQUETAS_ESTADO_LINEA.get(linea["estado"], linea["estado"])),
            )
            self._tabla_especiales.setCellWidget(
                fila, COLUMNA_ESP_ACCIONES, self._crear_widget_acciones(linea["id"])
            )
        self._tabla_especiales.setSortingEnabled(True)
        ajustar_columnas(self._tabla_especiales)

        self._boton_marcar_recibido.setEnabled(
            self._pedido_id is not None and pedido_listo_para_cerrar(self.conexion, self._pedido_id)
        )
