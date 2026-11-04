"""Pantalla Facturación: carga rápida de comprobantes pensada para usarse
con teclado (docs/AJUSTES_V1.1.md, etapa 2.1). La carga en sí vive en
ios/services/comprobantes.py; acá solo se arma el formulario y la tabla de
la sesión."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from PySide6.QtCore import QDate, QEvent, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
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
from ios.data import comprobantes as datos_comprobantes
from ios.data import configuracion as datos_configuracion
from ios.data import tipos_comprobante as datos_tipos_comprobante
from ios.domain.calculos import calcular_iva_discriminado, calcular_monto_final
from ios.reports.formato import formato_fecha, formato_moneda
from ios.services import comprobantes as servicio_comprobantes
from ios.services.comprobantes import NumeroDuplicadoError
from ios.services.cuenta_corriente import estado_de_cuenta_cliente
from ios.ui.widgets import BuscadorCliente, ajustar_columnas


class PaginaFacturacion(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self._cliente_id: int | None = None
        self._es_particular = False
        self._mostrar_sucursal = False
        self._mostrar_particular = False
        self._fecha_ultima_usada = QDate.currentDate()
        self._comprobante_en_edicion: int | None = None
        self._ids_sesion: list[int] = []

        layout_general = QVBoxLayout(self)

        fila_buscador = QHBoxLayout()
        self.buscador = BuscadorCliente(conexion)
        self.buscador.clienteElegido.connect(self._al_elegir_cliente)
        fila_buscador.addWidget(self.buscador, stretch=2)
        self._etiqueta_info_cliente = QLabel("")
        fila_buscador.addWidget(self._etiqueta_info_cliente, stretch=3)
        layout_general.addLayout(fila_buscador)

        grupo = QGroupBox("Comprobante")
        self._formulario = QFormLayout(grupo)

        self.campo_tipo = QComboBox()
        self.campo_sucursal = QComboBox()
        self.campo_particular = QLineEdit()
        self.campo_numero = QLineEdit()
        self.campo_fecha = QDateEdit(QDate.currentDate())
        self.campo_fecha.setCalendarPopup(True)
        self.campo_monto_lista = QDoubleSpinBox()
        self.campo_monto_lista.setRange(0, 99_999_999)
        self.campo_monto_lista.setDecimals(2)
        self.campo_monto_lista.valueChanged.connect(self._recalcular)
        self.campo_descuento = QDoubleSpinBox()
        self.campo_descuento.setRange(0, 100)
        self.campo_descuento.setDecimals(2)
        self.campo_descuento.setSuffix(" %")
        self.campo_descuento.valueChanged.connect(self._recalcular)
        self.campo_con_iva = QCheckBox("Con IVA")
        self.campo_con_iva.stateChanged.connect(self._recalcular)

        self.etiqueta_final = QLabel("$ 0,00")
        self.etiqueta_iva = QLabel("$ 0,00")

        self._formulario.addRow("Tipo", self.campo_tipo)
        self._formulario.addRow("Sucursal", self.campo_sucursal)
        self._formulario.addRow("Nombre particular", self.campo_particular)
        self._formulario.addRow("Número", self.campo_numero)
        self._formulario.addRow("Fecha", self.campo_fecha)
        self._formulario.addRow("Monto de lista", self.campo_monto_lista)
        self._formulario.addRow("Descuento", self.campo_descuento)
        self._formulario.addRow(self.campo_con_iva)
        self._formulario.addRow("Monto final", self.etiqueta_final)
        self._formulario.addRow("IVA discriminado", self.etiqueta_iva)
        self._formulario.setRowVisible(self.campo_sucursal, False)
        self._formulario.setRowVisible(self.campo_particular, False)

        layout_general.addWidget(grupo)

        self._etiqueta_aviso = QLabel("")
        self._etiqueta_aviso.setStyleSheet("color: #b45309;")
        self._etiqueta_aviso.setVisible(False)
        layout_general.addWidget(self._etiqueta_aviso)

        fila_botones = QHBoxLayout()
        self.boton_guardar = QPushButton("Guardar (Enter)")
        self.boton_guardar.clicked.connect(self._guardar)
        fila_botones.addWidget(self.boton_guardar)
        self.boton_cancelar_edicion = QPushButton("Cancelar edición")
        self.boton_cancelar_edicion.clicked.connect(self._cancelar_edicion)
        self.boton_cancelar_edicion.setVisible(False)
        fila_botones.addWidget(self.boton_cancelar_edicion)
        fila_botones.addStretch(1)
        layout_general.addLayout(fila_botones)

        layout_general.addWidget(QLabel("Cargados en esta sesión"))
        self.tabla_sesion = QTableWidget(0, 7)
        self.tabla_sesion.setHorizontalHeaderLabels(
            ["Número", "Fecha", "Sucursal", "Lista", "Descuento", "Final", "IVA"]
        )
        self.tabla_sesion.verticalHeader().setVisible(False)
        self.tabla_sesion.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla_sesion.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla_sesion.itemDoubleClicked.connect(self._editar_seleccionado)
        layout_general.addWidget(self.tabla_sesion, stretch=1)

        pie = QHBoxLayout()
        self.etiqueta_total_sesion = QLabel("Total: $ 0,00")
        pie.addWidget(self.etiqueta_total_sesion)
        pie.addStretch(1)
        boton_editar = QPushButton("Editar seleccionado")
        boton_editar.clicked.connect(self._editar_seleccionado)
        pie.addWidget(boton_editar)
        boton_anular = QPushButton("Anular seleccionado")
        boton_anular.clicked.connect(self._anular_seleccionado)
        pie.addWidget(boton_anular)
        layout_general.addLayout(pie)

        for campo in self._campos_con_enter():
            campo.installEventFilter(self)

        self._cargar_combo_tipos()
        self._deshabilitar_formulario(True)

    # --- Enter avanza de campo; en el último, guarda ---

    def _campos_con_enter(self) -> list[QWidget]:
        return [
            self.campo_tipo, self.campo_sucursal, self.campo_particular,
            self.campo_numero, self.campo_fecha, self.campo_monto_lista,
            self.campo_descuento, self.campo_con_iva,
        ]

    def _orden_campos_visibles(self) -> list[QWidget]:
        orden = [self.campo_tipo]
        if self._mostrar_sucursal:
            orden.append(self.campo_sucursal)
        if self._mostrar_particular:
            orden.append(self.campo_particular)
        orden += [self.campo_numero, self.campo_fecha, self.campo_monto_lista, self.campo_descuento, self.campo_con_iva]
        return orden

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            orden = self._orden_campos_visibles()
            if obj in orden:
                indice = orden.index(obj)
                if indice + 1 < len(orden):
                    siguiente = orden[indice + 1]
                    siguiente.setFocus()
                    if hasattr(siguiente, "selectAll"):
                        siguiente.selectAll()
                else:
                    self._guardar()
                return True
        return super().eventFilter(obj, event)

    # --- carga de datos ---

    def actualizar(self) -> None:
        self.buscador.cargar_clientes()
        self._cargar_combo_tipos()

    def reiniciar(self) -> None:
        """Al salir de la pantalla (cambio de menú o cierre) todo queda en
        blanco; los datos ya guardados siguen en la base, solo se borra la
        vista de la sesión (docs/AJUSTES_V1.1.md, etapa 2.1.6)."""
        self._cliente_id = None
        self.buscador.limpiar()
        self._mostrar_sucursal = False
        self._mostrar_particular = False
        self._formulario.setRowVisible(self.campo_sucursal, False)
        self._formulario.setRowVisible(self.campo_particular, False)
        self._etiqueta_info_cliente.setText("")
        self._vaciar_sesion()
        self._deshabilitar_formulario(True)

    def _cargar_combo_tipos(self) -> None:
        self.campo_tipo.clear()
        indice_rto = 0
        for indice, tipo in enumerate(datos_tipos_comprobante.listar_tipos_comprobante(self.conexion)):
            self.campo_tipo.addItem(f"{tipo['nombre']} ({tipo['abreviatura']})", tipo["id"])
            if tipo["abreviatura"] == "RTO":
                indice_rto = indice
        self.campo_tipo.setCurrentIndex(indice_rto)

    def _deshabilitar_formulario(self, deshabilitar: bool) -> None:
        for campo in [*self._campos_con_enter(), self.boton_guardar]:
            campo.setEnabled(not deshabilitar)

    def _deshabilitar_campos_montos(self, deshabilitar: bool) -> None:
        self.campo_monto_lista.setEnabled(not deshabilitar)
        self.campo_descuento.setEnabled(not deshabilitar)
        self.campo_con_iva.setEnabled(not deshabilitar)

    # --- elegir cliente ---

    def _al_elegir_cliente(self, cliente_id: int) -> None:
        self._cliente_id = cliente_id
        self._vaciar_sesion()

        cliente = datos_clientes.obtener_cliente(self.conexion, cliente_id)
        self._es_particular = bool(cliente["es_particular"])

        sucursales = datos_clientes.listar_sucursales(self.conexion, cliente_id)
        self.campo_sucursal.clear()
        for sucursal in sucursales:
            self.campo_sucursal.addItem(sucursal["nombre"], sucursal["id"])
        self._mostrar_sucursal = len(sucursales) > 1
        self._mostrar_particular = self._es_particular
        self._formulario.setRowVisible(self.campo_sucursal, self._mostrar_sucursal)
        self._formulario.setRowVisible(self.campo_particular, self._mostrar_particular)

        self.campo_descuento.setValue(float(cliente["descuento_default"]))
        self.campo_con_iva.setChecked(bool(cliente["con_iva_default"]))
        self.campo_fecha.setDate(self._fecha_ultima_usada)

        self._mostrar_info_cliente(cliente)
        self._deshabilitar_formulario(False)
        self._recalcular()

        if self._mostrar_sucursal:
            self.campo_sucursal.setFocus()
        else:
            self.campo_numero.setFocus()

    def _mostrar_info_cliente(self, cliente: sqlite3.Row) -> None:
        estado = estado_de_cuenta_cliente(self.conexion, cliente["id"])
        iva_texto = "Sí" if cliente["con_iva_default"] else "No"
        self._etiqueta_info_cliente.setText(
            f"Descuento por defecto: {cliente['descuento_default']}% · "
            f"IVA por defecto: {iva_texto} · "
            f"Saldo actual: {formato_moneda(estado.saldo_consolidado)}"
        )

    # --- cálculo en vivo ---

    def _recalcular(self) -> None:
        configuracion = datos_configuracion.obtener_configuracion(self.conexion)
        decimales = configuracion["redondeo_decimales"]
        tasa_iva = configuracion["iva_pct"]

        monto_lista = Decimal(str(self.campo_monto_lista.value()))
        descuento = Decimal(str(self.campo_descuento.value()))
        con_iva = self.campo_con_iva.isChecked()

        final = calcular_monto_final(monto_lista, descuento, decimales)
        iva = calcular_iva_discriminado(final, con_iva, tasa_iva, decimales)

        self.etiqueta_final.setText(formato_moneda(final))
        self.etiqueta_iva.setText(formato_moneda(iva))

    # --- tabla de la sesión ---

    def _vaciar_sesion(self) -> None:
        self._ids_sesion = []
        self._comprobante_en_edicion = None
        self.campo_numero.clear()
        self.campo_monto_lista.setValue(0)
        self.campo_particular.clear()
        self.boton_cancelar_edicion.setVisible(False)
        self._etiqueta_aviso.setVisible(False)
        self._deshabilitar_campos_montos(False)
        self._cargar_tabla_sesion()

    def _cargar_tabla_sesion(self) -> None:
        self.tabla_sesion.setRowCount(len(self._ids_sesion))
        total = Decimal(0)
        for fila, comprobante_id in enumerate(self._ids_sesion):
            comprobante = datos_comprobantes.obtener_comprobante(self.conexion, comprobante_id)
            sucursal = datos_clientes.listar_sucursales(
                self.conexion, comprobante["cliente_id"], incluir_inactivas=True
            )
            nombre_sucursal = next(
                (s["nombre"] for s in sucursal if s["id"] == comprobante["sucursal_id"]), ""
            )
            self.tabla_sesion.setItem(fila, 0, QTableWidgetItem(comprobante["numero"]))
            self.tabla_sesion.setItem(fila, 1, QTableWidgetItem(formato_fecha(comprobante["fecha"])))
            self.tabla_sesion.setItem(fila, 2, QTableWidgetItem(nombre_sucursal))
            self.tabla_sesion.setItem(fila, 3, QTableWidgetItem(formato_moneda(comprobante["monto_lista"])))
            self.tabla_sesion.setItem(fila, 4, QTableWidgetItem(f"{comprobante['descuento_pct']}%"))
            self.tabla_sesion.setItem(fila, 5, QTableWidgetItem(formato_moneda(comprobante["monto_final"])))
            self.tabla_sesion.setItem(fila, 6, QTableWidgetItem(formato_moneda(comprobante["iva_discriminado"])))
            total += comprobante["monto_final"]
        ajustar_columnas(self.tabla_sesion)
        self.etiqueta_total_sesion.setText(f"Total: {formato_moneda(total)}")

    # --- guardar ---

    def _guardar(self, forzar: bool = False) -> None:
        if self._cliente_id is None:
            return
        numero = self.campo_numero.text().strip()
        if not numero:
            QMessageBox.warning(self, "Falta el número", "El número de comprobante es obligatorio.")
            return

        tipo_id = self.campo_tipo.currentData()
        sucursal_id = self.campo_sucursal.currentData()
        fecha = self.campo_fecha.date().toString("yyyy-MM-dd")
        monto_lista = Decimal(str(self.campo_monto_lista.value()))
        descuento = Decimal(str(self.campo_descuento.value()))
        con_iva = self.campo_con_iva.isChecked()
        nombre_particular = (
            self.campo_particular.text().strip() or None if self._mostrar_particular else None
        )

        try:
            if self._comprobante_en_edicion is None:
                comprobante_id = servicio_comprobantes.alta_comprobante(
                    self.conexion, tipo_id, numero, fecha, self._cliente_id, sucursal_id,
                    monto_lista, descuento_pct=descuento, con_iva=con_iva,
                    nombre_particular=nombre_particular, forzar_numero_repetido=forzar,
                )
                self._ids_sesion.append(comprobante_id)
            else:
                comprobante_id = self._comprobante_en_edicion
                campos = {"numero": numero, "fecha": fecha}
                if not servicio_comprobantes.tiene_pagos_aplicados(self.conexion, comprobante_id):
                    campos.update(monto_lista=monto_lista, descuento_pct=descuento, con_iva=con_iva)
                servicio_comprobantes.editar_comprobante(
                    self.conexion, comprobante_id, forzar_numero_repetido=forzar, **campos
                )
        except NumeroDuplicadoError as error:
            respuesta = QMessageBox.question(
                self, "Número repetido", f"{error} ¿Guardar igual?"
            )
            if respuesta == QMessageBox.Yes:
                self._guardar(forzar=True)
            return
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return

        self._mostrar_aviso_otro_cliente(tipo_id, numero, comprobante_id)
        self._fecha_ultima_usada = self.campo_fecha.date()
        self._cargar_tabla_sesion()
        self._limpiar_formulario_tras_guardar()

    def _mostrar_aviso_otro_cliente(self, tipo_id: int, numero: str, comprobante_id: int) -> None:
        coincidencias = [
            c for c in servicio_comprobantes.buscar_coincidencias_numero(
                self.conexion, tipo_id, numero, excluir_comprobante_id=comprobante_id
            )
            if c.cliente_id != self._cliente_id
        ]
        if not coincidencias:
            self._etiqueta_aviso.setVisible(False)
            return
        nombres = ", ".join(sorted({c.cliente_nombre for c in coincidencias}))
        self._etiqueta_aviso.setText(f"El número {numero} también está cargado en {nombres}.")
        self._etiqueta_aviso.setVisible(True)

    def _limpiar_formulario_tras_guardar(self) -> None:
        """Mantiene cliente, sucursal, tipo y fecha; limpia el resto y
        devuelve el foco a «número» (docs/AJUSTES_V1.1.md, etapa 2.1.4)."""
        self._comprobante_en_edicion = None
        self.boton_cancelar_edicion.setVisible(False)
        self._deshabilitar_campos_montos(False)
        self.campo_numero.clear()
        self.campo_particular.clear()
        self.campo_monto_lista.setValue(0)
        if self._cliente_id is not None:
            cliente = datos_clientes.obtener_cliente(self.conexion, self._cliente_id)
            self.campo_descuento.setValue(float(cliente["descuento_default"]))
            self.campo_con_iva.setChecked(bool(cliente["con_iva_default"]))
        self._recalcular()
        self.campo_numero.setFocus()

    # --- editar / anular desde la tabla de la sesión ---

    def _editar_seleccionado(self) -> None:
        fila = self.tabla_sesion.currentRow()
        if fila < 0 or fila >= len(self._ids_sesion):
            return
        comprobante_id = self._ids_sesion[fila]
        comprobante = datos_comprobantes.obtener_comprobante(self.conexion, comprobante_id)

        self._comprobante_en_edicion = comprobante_id
        self.campo_numero.setText(comprobante["numero"])
        self.campo_fecha.setDate(QDate.fromString(comprobante["fecha"], "yyyy-MM-dd"))
        self.campo_monto_lista.setValue(float(comprobante["monto_lista"]))
        self.campo_descuento.setValue(float(comprobante["descuento_pct"]))
        self.campo_con_iva.setChecked(bool(comprobante["con_iva"]))
        if self._mostrar_sucursal:
            indice = self.campo_sucursal.findData(comprobante["sucursal_id"])
            if indice >= 0:
                self.campo_sucursal.setCurrentIndex(indice)
        if self._mostrar_particular:
            self.campo_particular.setText(comprobante["nombre_particular"] or "")

        bloqueado = servicio_comprobantes.tiene_pagos_aplicados(self.conexion, comprobante_id)
        self._deshabilitar_campos_montos(bloqueado)
        self.boton_cancelar_edicion.setVisible(True)
        if bloqueado:
            QMessageBox.information(
                self, "Tiene pagos aplicados",
                "Este comprobante ya tiene pagos aplicados: no se puede cambiar el monto, "
                "el descuento ni el IVA. Podés corregir el número y la fecha, o anularlo.",
            )
        self._recalcular()
        self.campo_numero.setFocus()

    def _cancelar_edicion(self) -> None:
        self._limpiar_formulario_tras_guardar()

    def _anular_seleccionado(self) -> None:
        fila = self.tabla_sesion.currentRow()
        if fila < 0 or fila >= len(self._ids_sesion):
            return
        comprobante_id = self._ids_sesion[fila]
        respuesta = QMessageBox.question(self, "Anular", "¿Anular este comprobante?")
        if respuesta != QMessageBox.Yes:
            return
        servicio_comprobantes.anular_comprobante(self.conexion, comprobante_id)
        self._ids_sesion.pop(fila)
        if self._comprobante_en_edicion == comprobante_id:
            self._limpiar_formulario_tras_guardar()
        self._cargar_tabla_sesion()
