"""Pantalla Clientes: buscador, alta/edición en un diálogo modal (datos +
sucursales), baja lógica y reactivación (docs/AJUSTES_V1.1.md, etapa 4)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ios.data import clientes as datos_clientes
from ios.domain.validaciones import cuit_valido
from ios.reports.formato import formato_moneda
from ios.services import clientes as servicio_clientes
from ios.services.cuenta_corriente import estado_de_cuenta_cliente
from ios.ui.widgets import ajustar_columnas, normalizar

FILTRO_ACTIVOS = "Activos"
FILTRO_DADOS_DE_BAJA = "Dados de baja"
FILTRO_TODOS = "Todos"


class _DialogoCliente(QDialog):
    """Alta/edición de un cliente: pestaña "Datos" y pestaña "Sucursales".
    Guardar con Enter, cancelar con Escape (docs/AJUSTES_V1.1.md, etapa 4)."""

    def __init__(
        self, conexion: sqlite3.Connection, cliente_id: int | None, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.conexion = conexion
        self.cliente_id = cliente_id
        self.setWindowTitle("Nuevo cliente" if cliente_id is None else "Editar cliente")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        self._pestanas = QTabWidget()
        layout.addWidget(self._pestanas)

        self._pestanas.addTab(self._crear_pestana_datos(), "Datos")
        self._pestana_sucursales = self._crear_pestana_sucursales()
        self._pestanas.addTab(self._pestana_sucursales, "Sucursales")
        self._pestanas.setTabEnabled(1, cliente_id is not None)

        botones = QHBoxLayout()
        botones.addStretch(1)
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(self.reject)
        boton_guardar = QPushButton("Guardar")
        boton_guardar.clicked.connect(self._confirmar)
        botones.addWidget(boton_cancelar)
        botones.addWidget(boton_guardar)
        layout.addLayout(botones)

        if cliente_id is not None:
            self._cargar_datos(cliente_id)
            self._cargar_sucursales()

        self._campo_nombre.setFocus()

    def _crear_pestana_datos(self) -> QWidget:
        pagina = QWidget()
        formulario = QFormLayout(pagina)

        self._campo_nombre = QLineEdit()
        self._campo_cuit = QLineEdit()
        self._campo_telefono = QLineEdit()
        self._campo_direccion = QLineEdit()
        self._campo_localidad = QLineEdit()
        self._campo_descuento = QDoubleSpinBox()
        self._campo_descuento.setRange(0, 100)
        self._campo_descuento.setDecimals(2)
        self._campo_descuento.setSuffix(" %")
        self._campo_con_iva = QCheckBox("Con IVA por defecto")
        self._campo_con_iva.setChecked(True)

        formulario.addRow("Nombre", self._campo_nombre)
        formulario.addRow("CUIT", self._campo_cuit)
        formulario.addRow("Teléfono", self._campo_telefono)
        formulario.addRow("Dirección", self._campo_direccion)
        formulario.addRow("Localidad", self._campo_localidad)
        formulario.addRow("Descuento", self._campo_descuento)
        formulario.addRow(self._campo_con_iva)
        return pagina

    def _crear_pestana_sucursales(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)

        self._lista_sucursales = QListWidget()
        layout.addWidget(self._lista_sucursales)

        botones = QHBoxLayout()
        boton_agregar = QPushButton("Agregar")
        boton_agregar.clicked.connect(self._agregar_sucursal)
        boton_renombrar = QPushButton("Renombrar")
        boton_renombrar.clicked.connect(self._renombrar_sucursal)
        self._boton_desactivar_sucursal = QPushButton("Desactivar")
        self._boton_desactivar_sucursal.clicked.connect(self._desactivar_sucursal)
        self._boton_reactivar_sucursal = QPushButton("Reactivar")
        self._boton_reactivar_sucursal.clicked.connect(self._reactivar_sucursal)
        botones.addWidget(boton_agregar)
        botones.addWidget(boton_renombrar)
        botones.addWidget(self._boton_desactivar_sucursal)
        botones.addWidget(self._boton_reactivar_sucursal)
        layout.addLayout(botones)

        self._lista_sucursales.itemSelectionChanged.connect(self._actualizar_botones_sucursal)
        return pagina

    # --- carga ---

    def _cargar_datos(self, cliente_id: int) -> None:
        cliente = datos_clientes.obtener_cliente(self.conexion, cliente_id)
        self._campo_nombre.setText(cliente["nombre"])
        self._campo_cuit.setText(cliente["cuit"] or "")
        self._campo_telefono.setText(cliente["telefono"] or "")
        self._campo_direccion.setText(cliente["direccion"] or "")
        self._campo_localidad.setText(cliente["localidad"] or "")
        self._campo_descuento.setValue(float(cliente["descuento_default"]))
        self._campo_con_iva.setChecked(bool(cliente["con_iva_default"]))

    def _cargar_sucursales(self) -> None:
        self._lista_sucursales.clear()
        for sucursal in datos_clientes.listar_sucursales(
            self.conexion, self.cliente_id, incluir_inactivas=True
        ):
            texto = sucursal["nombre"] if sucursal["activo"] else f"{sucursal['nombre']} (inactiva)"
            item = QListWidgetItem(texto)
            item.setData(Qt.UserRole, sucursal["id"])
            item.setData(Qt.UserRole + 1, bool(sucursal["activo"]))
            self._lista_sucursales.addItem(item)
        self._actualizar_botones_sucursal()

    def _actualizar_botones_sucursal(self) -> None:
        item = self._lista_sucursales.currentItem()
        activa = item is not None and item.data(Qt.UserRole + 1)
        inactiva = item is not None and not item.data(Qt.UserRole + 1)
        self._boton_desactivar_sucursal.setEnabled(activa)
        self._boton_reactivar_sucursal.setEnabled(inactiva)

    # --- acciones de sucursales ---

    def _agregar_sucursal(self) -> None:
        nombre, ok = QInputDialog.getText(self, "Nueva sucursal", "Nombre de la sucursal:")
        if not ok or not nombre.strip():
            return
        try:
            servicio_clientes.alta_sucursal(self.conexion, self.cliente_id, nombre.strip())
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo agregar", str(error))
            return
        self._cargar_sucursales()

    def _renombrar_sucursal(self) -> None:
        item = self._lista_sucursales.currentItem()
        if item is None:
            return
        nombre_actual = datos_clientes.obtener_sucursal(self.conexion, item.data(Qt.UserRole))["nombre"]
        nuevo_nombre, ok = QInputDialog.getText(
            self, "Renombrar sucursal", "Nuevo nombre:", text=nombre_actual
        )
        if not ok or not nuevo_nombre.strip():
            return
        try:
            servicio_clientes.editar_sucursal(self.conexion, item.data(Qt.UserRole), nuevo_nombre.strip())
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo renombrar", str(error))
            return
        self._cargar_sucursales()

    def _desactivar_sucursal(self) -> None:
        item = self._lista_sucursales.currentItem()
        if item is None:
            return
        try:
            servicio_clientes.desactivar_sucursal(self.conexion, item.data(Qt.UserRole))
        except servicio_clientes.UltimaSucursalActivaError as error:
            QMessageBox.warning(self, "No se puede desactivar", str(error))
            return
        self._cargar_sucursales()

    def _reactivar_sucursal(self) -> None:
        item = self._lista_sucursales.currentItem()
        if item is None:
            return
        servicio_clientes.reactivar_sucursal(self.conexion, item.data(Qt.UserRole))
        self._cargar_sucursales()

    # --- guardar ---

    def _confirmar(self) -> None:
        nombre = self._campo_nombre.text().strip()
        cuit = self._campo_cuit.text().strip() or None

        if cuit and not cuit_valido(cuit):
            respuesta = QMessageBox.question(
                self,
                "CUIT con formato inválido",
                f"El CUIT '{cuit}' no tiene un formato válido. ¿Guardar igual?",
            )
            if respuesta != QMessageBox.Yes:
                return

        campos = dict(
            nombre=nombre,
            cuit=cuit,
            telefono=self._campo_telefono.text().strip() or None,
            direccion=self._campo_direccion.text().strip() or None,
            localidad=self._campo_localidad.text().strip() or None,
            descuento_default=Decimal(str(self._campo_descuento.value())),
            con_iva_default=self._campo_con_iva.isChecked(),
        )

        try:
            if self.cliente_id is None:
                self.cliente_id = servicio_clientes.alta_cliente(self.conexion, **campos)
            else:
                servicio_clientes.editar_cliente(self.conexion, self.cliente_id, **campos)
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return

        self.accept()

    def keyPressEvent(self, evento) -> None:  # noqa: N802 (override de Qt)
        if evento.key() == Qt.Key_Escape:
            self.reject()
            return
        if evento.key() in (Qt.Key_Return, Qt.Key_Enter) and not isinstance(
            self.focusWidget(), QListWidget
        ):
            self._confirmar()
            return
        super().keyPressEvent(evento)


class PaginaClientes(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion

        layout = QVBoxLayout(self)

        encabezado = QHBoxLayout()
        encabezado.addWidget(QLabel("Clientes"))
        self._campo_buscar = QLineEdit()
        self._campo_buscar.setPlaceholderText("Buscar por nombre, CUIT o localidad...")
        self._campo_buscar.textChanged.connect(self._cargar_tabla)
        encabezado.addWidget(self._campo_buscar, stretch=1)
        self._campo_filtro = QComboBox()
        self._campo_filtro.addItems([FILTRO_ACTIVOS, FILTRO_DADOS_DE_BAJA, FILTRO_TODOS])
        self._campo_filtro.currentTextChanged.connect(self._cargar_tabla)
        encabezado.addWidget(self._campo_filtro)
        layout.addLayout(encabezado)

        self._tabla = QTableWidget(0, 4)
        self._tabla.setHorizontalHeaderLabels(["Nombre", "Localidad", "Teléfono", "Saldo"])
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.setSelectionBehavior(QTableWidget.SelectRows)
        self._tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla.itemSelectionChanged.connect(self._actualizar_botones)
        self._tabla.doubleClicked.connect(self._editar_cliente)
        layout.addWidget(self._tabla, stretch=1)

        botones = QHBoxLayout()
        boton_nuevo = QPushButton("Nuevo cliente")
        boton_nuevo.clicked.connect(self._nuevo_cliente)
        self._boton_editar = QPushButton("Editar")
        self._boton_editar.clicked.connect(self._editar_cliente)
        self._boton_baja = QPushButton("Dar de baja")
        self._boton_baja.clicked.connect(self._dar_de_baja)
        self._boton_reactivar = QPushButton("Reactivar")
        self._boton_reactivar.clicked.connect(self._reactivar_cliente)
        botones.addWidget(boton_nuevo)
        botones.addWidget(self._boton_editar)
        botones.addWidget(self._boton_baja)
        botones.addWidget(self._boton_reactivar)
        botones.addStretch(1)
        layout.addLayout(botones)

        self._actualizar_botones()
        self.actualizar()

    # --- interfaz de navegación (docs/AJUSTES_V1.1.md, etapa 1) ---

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar

    def actualizar(self) -> None:
        self._cargar_tabla()

    # --- tabla ---

    def _cargar_tabla(self) -> None:
        filtro = self._campo_filtro.currentText()
        if filtro == FILTRO_ACTIVOS:
            clientes = datos_clientes.listar_clientes(self.conexion, incluir_inactivos=False)
        elif filtro == FILTRO_DADOS_DE_BAJA:
            clientes = [
                c for c in datos_clientes.listar_clientes(self.conexion, incluir_inactivos=True)
                if not c["activo"]
            ]
        else:
            clientes = datos_clientes.listar_clientes(self.conexion, incluir_inactivos=True)

        objetivo = normalizar(self._campo_buscar.text().strip())
        if objetivo:
            clientes = [
                c for c in clientes
                if objetivo in normalizar(c["nombre"])
                or objetivo in normalizar(c["cuit"] or "")
                or objetivo in normalizar(c["localidad"] or "")
            ]

        self._tabla.setRowCount(len(clientes))
        for fila, cliente in enumerate(clientes):
            nombre = cliente["nombre"] if cliente["activo"] else f"{cliente['nombre']} (de baja)"
            saldo = estado_de_cuenta_cliente(self.conexion, cliente["id"]).saldo_consolidado
            self._tabla.setItem(fila, 0, QTableWidgetItem(nombre))
            self._tabla.setItem(fila, 1, QTableWidgetItem(cliente["localidad"] or ""))
            self._tabla.setItem(fila, 2, QTableWidgetItem(cliente["telefono"] or ""))
            self._tabla.setItem(fila, 3, QTableWidgetItem(formato_moneda(saldo)))
            self._tabla.item(fila, 0).setData(Qt.UserRole, cliente["id"])
            self._tabla.item(fila, 0).setData(Qt.UserRole + 1, bool(cliente["activo"]))
        ajustar_columnas(self._tabla)

        self._actualizar_botones()

    def _cliente_seleccionado(self) -> int | None:
        filas = self._tabla.selectionModel().selectedRows()
        if not filas:
            return None
        return self._tabla.item(filas[0].row(), 0).data(Qt.UserRole)

    def _actualizar_botones(self) -> None:
        filas = self._tabla.selectionModel().selectedRows() if self._tabla.selectionModel() else []
        if not filas:
            self._boton_editar.setEnabled(False)
            self._boton_baja.setEnabled(False)
            self._boton_reactivar.setEnabled(False)
            return
        activo = self._tabla.item(filas[0].row(), 0).data(Qt.UserRole + 1)
        self._boton_editar.setEnabled(True)
        self._boton_baja.setEnabled(bool(activo))
        self._boton_reactivar.setEnabled(not activo)

    # --- acciones ---

    def _nuevo_cliente(self) -> None:
        dialogo = _DialogoCliente(self.conexion, None, self)
        if dialogo.exec() == QDialog.Accepted:
            self._seleccionar_despues_de_guardar(dialogo.cliente_id)

    def _editar_cliente(self) -> None:
        cliente_id = self._cliente_seleccionado()
        if cliente_id is None:
            return
        dialogo = _DialogoCliente(self.conexion, cliente_id, self)
        if dialogo.exec() == QDialog.Accepted:
            self._seleccionar_despues_de_guardar(cliente_id)

    def _dar_de_baja(self) -> None:
        cliente_id = self._cliente_seleccionado()
        if cliente_id is None:
            return
        respuesta = QMessageBox.question(
            self, "Dar de baja", "¿Dar de baja a este cliente? No se borra, queda inactivo."
        )
        if respuesta != QMessageBox.Yes:
            return
        servicio_clientes.baja_logica_cliente(self.conexion, cliente_id)
        self._seleccionar_despues_de_guardar(cliente_id)

    def _reactivar_cliente(self) -> None:
        cliente_id = self._cliente_seleccionado()
        if cliente_id is None:
            return
        servicio_clientes.reactivar_cliente(self.conexion, cliente_id)
        self._seleccionar_despues_de_guardar(cliente_id)

    def _seleccionar_despues_de_guardar(self, cliente_id: int | None) -> None:
        self._cargar_tabla()
        if cliente_id is None:
            return
        for fila in range(self._tabla.rowCount()):
            if self._tabla.item(fila, 0).data(Qt.UserRole) == cliente_id:
                self._tabla.selectRow(fila)
                break
