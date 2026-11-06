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
from ios.data import tipos_cristal as datos_tipos_cristal
from ios.domain.calculos import calcular_iva_discriminado, calcular_monto_final
from ios.domain.graduacion import formatear_graduacion, parsear_graduacion
from ios.reports.formato import formato_fecha, formato_moneda
from ios.services import comprobantes as servicio_comprobantes
from ios.services.comprobantes import NumeroDuplicadoError, RenglonDetalle
from ios.services.cuenta_corriente import estado_de_cuenta_cliente
from ios.services.tipos_cristal import precio_unitario as _precio_unitario_tipo_cristal
from ios.ui.widgets import BuscadorCliente, CampoDecimal, CampoEntero, CampoGraduacion, ajustar_columnas


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
        self._modo_detalle = False
        self._numero_autosugerido = False
        self._renglones_actuales: list[RenglonDetalle] = []
        self._indice_renglon_editando: int | None = None
        self._tipos_cristal_cache: dict[int, sqlite3.Row] = {}

        layout_general = QVBoxLayout(self)

        fila_buscador = QHBoxLayout()
        self.buscador = BuscadorCliente(conexion)
        self.buscador.clienteElegido.connect(self._al_elegir_cliente)
        fila_buscador.addWidget(self.buscador, stretch=2)
        self._etiqueta_info_cliente = QLabel("")
        fila_buscador.addWidget(self._etiqueta_info_cliente, stretch=3)
        layout_general.addLayout(fila_buscador)

        grupo = QGroupBox("Comprobante")
        layout_grupo = QVBoxLayout(grupo)
        columnas_comprobante = QHBoxLayout()

        self.campo_tipo = QComboBox()
        self.campo_tipo.currentIndexChanged.connect(self._al_cambiar_tipo)
        self.campo_sucursal = QComboBox()
        self.campo_particular = QLineEdit()
        self.campo_numero = QLineEdit()
        self.campo_numero.textEdited.connect(self._al_tipear_numero)
        self.campo_fecha = QDateEdit(QDate.currentDate())
        self.campo_fecha.setCalendarPopup(True)

        self._formulario_izq = QFormLayout()
        self._formulario_izq.addRow("Tipo", self.campo_tipo)
        self._formulario_izq.addRow("Sucursal", self.campo_sucursal)
        self._formulario_izq.addRow("Nombre particular", self.campo_particular)
        self._formulario_izq.addRow("Número", self.campo_numero)
        self._formulario_izq.addRow("Fecha", self.campo_fecha)
        self._formulario_izq.setRowVisible(self.campo_sucursal, False)
        self._formulario_izq.setRowVisible(self.campo_particular, False)
        columnas_comprobante.addLayout(self._formulario_izq, stretch=1)

        self.campo_monto_lista = CampoDecimal()
        self.campo_monto_lista.setRange(0, 99_999_999)
        self.campo_monto_lista.setDecimals(2)
        self.campo_monto_lista.valueChanged.connect(self._recalcular)
        self.campo_descuento = CampoDecimal()
        self.campo_descuento.setRange(0, 100)
        self.campo_descuento.setDecimals(2)
        self.campo_descuento.setSuffix(" %")
        self.campo_descuento.valueChanged.connect(self._recalcular)
        self.campo_con_iva = QCheckBox("Con IVA")
        self.campo_con_iva.stateChanged.connect(self._recalcular)

        self.etiqueta_final = QLabel("$ 0,00")
        self.etiqueta_iva = QLabel("$ 0,00")
        fila_totales = QHBoxLayout()
        fila_totales.addWidget(QLabel("Final:"))
        fila_totales.addWidget(self.etiqueta_final)
        fila_totales.addWidget(QLabel("IVA:"))
        fila_totales.addWidget(self.etiqueta_iva)
        fila_totales.addStretch(1)

        formulario_der = QFormLayout()
        formulario_der.addRow("Monto de lista", self.campo_monto_lista)
        formulario_der.addRow("Descuento", self.campo_descuento)
        formulario_der.addRow(self.campo_con_iva)
        formulario_der.addRow(fila_totales)
        columnas_comprobante.addLayout(formulario_der, stretch=1)

        layout_grupo.addLayout(columnas_comprobante)

        self.campo_con_detalle = QCheckBox("Cargar con detalle (renglones de cristales)")
        self.campo_con_detalle.toggled.connect(self._cambiar_modo_detalle)
        layout_grupo.addWidget(self.campo_con_detalle)

        layout_general.addWidget(grupo)

        self._grupo_detalle = QGroupBox("Detalle")
        layout_grupo_detalle = QHBoxLayout(self._grupo_detalle)

        columna_formulario_renglon = QVBoxLayout()
        self._formulario_renglon = QFormLayout()
        self.combo_tipo_detalle = QComboBox()
        # Un combo sin editar no muestra ningún borde de foco visible por
        # defecto, y en el loop de carga con Enter es el primer campo del
        # renglón: sin esto no se nota a dónde volvió el foco.
        self.combo_tipo_detalle.setStyleSheet("QComboBox:focus { border: 2px solid #2563eb; }")
        self.combo_tipo_detalle.currentIndexChanged.connect(self._cambio_tipo_detalle)
        self._formulario_renglon.addRow("Cristal", self.combo_tipo_detalle)
        self.campo_descripcion_detalle = QLineEdit()
        self.campo_descripcion_detalle.setPlaceholderText("Descripción")
        self._formulario_renglon.addRow("Descripción", self.campo_descripcion_detalle)
        self.campo_precio_detalle = CampoDecimal()
        self.campo_precio_detalle.setRange(0, 99_999_999)
        self.campo_precio_detalle.setDecimals(2)
        self.campo_precio_detalle.setPrefix("$ ")
        self._formulario_renglon.addRow("Precio unitario", self.campo_precio_detalle)

        self._fila_graduacion = QWidget()
        layout_graduacion = QHBoxLayout(self._fila_graduacion)
        layout_graduacion.setContentsMargins(0, 0, 0, 0)
        layout_graduacion.addWidget(QLabel("Esférico"))
        self.campo_esferico_detalle = CampoGraduacion()
        self.campo_esferico_detalle.setRange(-30, 30)
        self.campo_esferico_detalle.setSingleStep(0.25)
        self.campo_esferico_detalle.setDecimals(2)
        layout_graduacion.addWidget(self.campo_esferico_detalle)
        layout_graduacion.addWidget(QLabel("Cilíndrico"))
        self.campo_cilindrico_detalle = CampoGraduacion()
        self.campo_cilindrico_detalle.setRange(-30, 30)
        self.campo_cilindrico_detalle.setSingleStep(0.25)
        self.campo_cilindrico_detalle.setDecimals(2)
        layout_graduacion.addWidget(self.campo_cilindrico_detalle)
        self._formulario_renglon.addRow(self._fila_graduacion)

        self.campo_cantidad_detalle = CampoEntero()
        self.campo_cantidad_detalle.setRange(1, 999)
        self.campo_cantidad_detalle.setValue(1)
        self._formulario_renglon.addRow("Cantidad (unidades)", self.campo_cantidad_detalle)
        columna_formulario_renglon.addLayout(self._formulario_renglon)

        botones_renglon = QHBoxLayout()
        self.boton_agregar_renglon = QPushButton("Agregar renglón")
        self.boton_agregar_renglon.clicked.connect(self._agregar_o_actualizar_renglon)
        botones_renglon.addWidget(self.boton_agregar_renglon)
        self.boton_cancelar_renglon = QPushButton("Cancelar edición")
        self.boton_cancelar_renglon.clicked.connect(self._cancelar_edicion_renglon)
        self.boton_cancelar_renglon.setVisible(False)
        botones_renglon.addWidget(self.boton_cancelar_renglon)
        columna_formulario_renglon.addLayout(botones_renglon)
        columna_formulario_renglon.addStretch(1)
        layout_grupo_detalle.addLayout(columna_formulario_renglon, stretch=1)

        columna_tabla_renglon = QVBoxLayout()
        columna_tabla_renglon.addWidget(QLabel("Renglones del remito en curso"))
        self.tabla_detalle_actual = QTableWidget(0, 5)
        self.tabla_detalle_actual.setHorizontalHeaderLabels(
            ["Cristal/Descripción", "Graduación", "Cantidad", "Precio unit.", "Subtotal"]
        )
        self.tabla_detalle_actual.verticalHeader().setVisible(False)
        self.tabla_detalle_actual.setSelectionBehavior(QTableWidget.SelectRows)
        self.tabla_detalle_actual.setEditTriggers(QTableWidget.NoEditTriggers)
        self.tabla_detalle_actual.itemDoubleClicked.connect(self._editar_renglon_actual)
        columna_tabla_renglon.addWidget(self.tabla_detalle_actual, stretch=1)
        pie_tabla_renglon = QHBoxLayout()
        self.etiqueta_total_detalle = QLabel("Total: $ 0,00")
        pie_tabla_renglon.addWidget(self.etiqueta_total_detalle)
        pie_tabla_renglon.addStretch(1)
        boton_quitar_renglon = QPushButton("Quitar renglón")
        boton_quitar_renglon.clicked.connect(self._quitar_renglon_actual)
        pie_tabla_renglon.addWidget(boton_quitar_renglon)
        columna_tabla_renglon.addLayout(pie_tabla_renglon)
        layout_grupo_detalle.addLayout(columna_tabla_renglon, stretch=2)

        self._grupo_detalle.setVisible(False)
        layout_general.addWidget(self._grupo_detalle)

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

        for campo in [*self._campos_con_enter(), *self._campos_con_enter_renglon()]:
            campo.installEventFilter(self)

        self._cargar_combo_tipos()
        self._deshabilitar_formulario(True)

    # --- Enter avanza de campo; en el último, guarda ---

    def _campos_con_enter(self) -> list[QWidget]:
        return [
            self.campo_tipo, self.campo_sucursal, self.campo_particular,
            self.campo_numero, self.campo_fecha, self.campo_monto_lista,
            self.campo_descuento, self.campo_con_iva, self.campo_con_detalle,
        ]

    def _orden_campos_visibles(self) -> list[QWidget]:
        orden = [self.campo_tipo]
        if self._mostrar_sucursal:
            orden.append(self.campo_sucursal)
        if self._mostrar_particular:
            orden.append(self.campo_particular)
        orden += [self.campo_numero, self.campo_fecha, self.campo_monto_lista, self.campo_descuento, self.campo_con_iva]
        return orden

    # --- Enter en el renglón de detalle: recorre el formulario y en el
    # último campo agrega el renglón, para cargar varios cristales seguidos
    # sin tocar el mouse (se vuelve a "Cristal" después de cada uno). ---

    def _campos_con_enter_renglon(self) -> list[QWidget]:
        return [
            self.combo_tipo_detalle, self.campo_descripcion_detalle, self.campo_precio_detalle,
            self.campo_esferico_detalle, self.campo_cilindrico_detalle, self.campo_cantidad_detalle,
        ]

    def _orden_campos_renglon_visibles(self) -> list[QWidget]:
        orden = [self.combo_tipo_detalle]
        if self._formulario_renglon.isRowVisible(self.campo_descripcion_detalle):
            orden.append(self.campo_descripcion_detalle)
        if self._formulario_renglon.isRowVisible(self.campo_precio_detalle):
            orden.append(self.campo_precio_detalle)
        if self._formulario_renglon.isRowVisible(self._fila_graduacion):
            orden += [self.campo_esferico_detalle, self.campo_cilindrico_detalle]
        orden.append(self.campo_cantidad_detalle)
        return orden

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            orden = self._orden_campos_visibles()
            if obj in orden:
                self._avanzar_o_ejecutar(orden, obj, self._guardar)
                return True
            orden_renglon = self._orden_campos_renglon_visibles()
            if obj in orden_renglon:
                self._avanzar_o_ejecutar(orden_renglon, obj, self._agregar_o_actualizar_renglon)
                return True
        return super().eventFilter(obj, event)

    @staticmethod
    def _avanzar_o_ejecutar(orden: list[QWidget], actual: QWidget, accion_final) -> None:
        indice = orden.index(actual)
        if indice + 1 < len(orden):
            siguiente = orden[indice + 1]
            siguiente.setFocus()
            if hasattr(siguiente, "selectAll"):
                siguiente.selectAll()
        else:
            accion_final()

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
        self._formulario_izq.setRowVisible(self.campo_sucursal, False)
        self._formulario_izq.setRowVisible(self.campo_particular, False)
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
        self._formulario_izq.setRowVisible(self.campo_sucursal, self._mostrar_sucursal)
        self._formulario_izq.setRowVisible(self.campo_particular, self._mostrar_particular)

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

    # --- detalle (renglones de cristales) ---

    def _al_tipear_numero(self) -> None:
        self._numero_autosugerido = False

    def _al_cambiar_tipo(self) -> None:
        if self._modo_detalle and self._numero_autosugerido:
            self._sugerir_numero_detalle()

    def _sugerir_numero_detalle(self) -> None:
        tipo_id = self.campo_tipo.currentData()
        if tipo_id is None:
            return
        numero = servicio_comprobantes.siguiente_numero_comprobante(self.conexion, tipo_id)
        self.campo_numero.setText(numero)
        self._numero_autosugerido = True

    def _cambiar_modo_detalle(self, marcado: bool) -> None:
        self._modo_detalle = marcado
        self._grupo_detalle.setVisible(marcado)
        self.campo_monto_lista.setReadOnly(marcado)
        if marcado:
            self._cargar_combo_tipos_cristal()
            if not self.campo_numero.text().strip():
                self._sugerir_numero_detalle()
            self.combo_tipo_detalle.setFocus()
        else:
            self._vaciar_renglones_actuales()

    def _cargar_combo_tipos_cristal(self) -> None:
        tipos = datos_tipos_cristal.listar_tipos_cristal(self.conexion)
        self._tipos_cristal_cache = {t["id"]: t for t in tipos}
        self.combo_tipo_detalle.clear()
        for tipo in tipos:
            self.combo_tipo_detalle.addItem(tipo["nombre"], tipo["id"])
        self.combo_tipo_detalle.addItem("Otro (descripción libre)", None)
        if not tipos:
            QMessageBox.warning(
                self, "Sin tipos de cristal",
                "No hay tipos de cristal cargados. Cargalos en Configuración → Cristales.",
            )

    def _cambio_tipo_detalle(self) -> None:
        es_libre = self.combo_tipo_detalle.currentData() is None
        self._formulario_renglon.setRowVisible(self.campo_descripcion_detalle, es_libre)
        self._formulario_renglon.setRowVisible(self.campo_precio_detalle, es_libre)
        tipo = self._tipos_cristal_cache.get(self.combo_tipo_detalle.currentData())
        requiere_graduacion = bool(tipo["requiere_graduacion"]) if tipo is not None else True
        muestra_graduacion = es_libre or requiere_graduacion
        self._formulario_renglon.setRowVisible(self._fila_graduacion, muestra_graduacion)
        if not muestra_graduacion:
            self.campo_esferico_detalle.setValue(0)
            self.campo_cilindrico_detalle.setValue(0)
        if tipo is not None:
            self.campo_precio_detalle.setValue(float(_precio_unitario_tipo_cristal(tipo)))

    def _limpiar_formulario_renglon(self) -> None:
        self.combo_tipo_detalle.setCurrentIndex(0)
        self.campo_descripcion_detalle.clear()
        self.campo_precio_detalle.setValue(0)
        self.campo_esferico_detalle.setValue(0)
        self.campo_cilindrico_detalle.setValue(0)
        self.campo_cantidad_detalle.setValue(1)
        self._cambio_tipo_detalle()
        self.combo_tipo_detalle.setFocus()

    def _info_renglon(self, renglon: RenglonDetalle) -> tuple[str, Decimal, Decimal]:
        tipo = self._tipos_cristal_cache.get(renglon.tipo_cristal_id)
        if tipo is not None:
            nombre = tipo["nombre"]
            precio_unitario = _precio_unitario_tipo_cristal(tipo)
        else:
            nombre = renglon.descripcion or ""
            precio_unitario = renglon.precio_unitario or Decimal(0)
        return nombre, precio_unitario, precio_unitario * renglon.cantidad

    def _agregar_o_actualizar_renglon(self) -> None:
        tipo_id = self.combo_tipo_detalle.currentData()
        es_libre = tipo_id is None
        cantidad = self.campo_cantidad_detalle.value()

        if es_libre and not self.campo_descripcion_detalle.text().strip():
            QMessageBox.warning(self, "Falta la descripción", "Completá la descripción del renglón.")
            return

        graduacion = formatear_graduacion(
            Decimal(str(self.campo_esferico_detalle.value())),
            Decimal(str(self.campo_cilindrico_detalle.value())),
        )

        renglon = RenglonDetalle(
            graduacion=graduacion,
            cantidad=cantidad,
            tipo_cristal_id=tipo_id,
            descripcion=self.campo_descripcion_detalle.text().strip() or None if es_libre else None,
            precio_unitario=Decimal(str(self.campo_precio_detalle.value())) if es_libre else None,
        )

        if self._indice_renglon_editando is None:
            self._renglones_actuales.append(renglon)
        else:
            self._renglones_actuales[self._indice_renglon_editando] = renglon

        self._cancelar_edicion_renglon()
        self._cargar_tabla_detalle_actual()

    def _editar_renglon_actual(self) -> None:
        fila = self.tabla_detalle_actual.currentRow()
        if fila < 0 or fila >= len(self._renglones_actuales):
            return
        renglon = self._renglones_actuales[fila]
        self._indice_renglon_editando = fila

        if renglon.tipo_cristal_id is not None:
            indice = self.combo_tipo_detalle.findData(renglon.tipo_cristal_id)
            self.combo_tipo_detalle.setCurrentIndex(max(indice, 0))
        else:
            self.combo_tipo_detalle.setCurrentIndex(self.combo_tipo_detalle.count() - 1)
            self.campo_descripcion_detalle.setText(renglon.descripcion or "")
            self.campo_precio_detalle.setValue(float(renglon.precio_unitario or 0))
        esferico, cilindrico = parsear_graduacion(renglon.graduacion)
        self.campo_esferico_detalle.setValue(float(esferico))
        self.campo_cilindrico_detalle.setValue(float(cilindrico))
        self.campo_cantidad_detalle.setValue(renglon.cantidad)

        self.boton_agregar_renglon.setText("Actualizar renglón")
        self.boton_cancelar_renglon.setVisible(True)

    def _cancelar_edicion_renglon(self) -> None:
        self._indice_renglon_editando = None
        self._limpiar_formulario_renglon()
        self.boton_agregar_renglon.setText("Agregar renglón")
        self.boton_cancelar_renglon.setVisible(False)

    def _quitar_renglon_actual(self) -> None:
        fila = self.tabla_detalle_actual.currentRow()
        if fila < 0 or fila >= len(self._renglones_actuales):
            QMessageBox.warning(self, "Nada seleccionado", "Elegí un renglón de la lista.")
            return
        self._renglones_actuales.pop(fila)
        if self._indice_renglon_editando == fila:
            self._cancelar_edicion_renglon()
        self._cargar_tabla_detalle_actual()

    def _cargar_tabla_detalle_actual(self) -> None:
        self.tabla_detalle_actual.setRowCount(len(self._renglones_actuales))
        total = Decimal(0)
        for fila, renglon in enumerate(self._renglones_actuales):
            nombre, precio_unitario, subtotal = self._info_renglon(renglon)
            self.tabla_detalle_actual.setItem(fila, 0, QTableWidgetItem(nombre))
            self.tabla_detalle_actual.setItem(fila, 1, QTableWidgetItem(renglon.graduacion))
            self.tabla_detalle_actual.setItem(fila, 2, QTableWidgetItem(str(renglon.cantidad)))
            self.tabla_detalle_actual.setItem(fila, 3, QTableWidgetItem(formato_moneda(precio_unitario)))
            self.tabla_detalle_actual.setItem(fila, 4, QTableWidgetItem(formato_moneda(subtotal)))
            total += subtotal
        ajustar_columnas(self.tabla_detalle_actual)
        self.etiqueta_total_detalle.setText(f"Total: {formato_moneda(total)}")
        self.campo_monto_lista.setValue(float(total))
        self._recalcular()

    def _vaciar_renglones_actuales(self) -> None:
        self._renglones_actuales = []
        self._indice_renglon_editando = None
        self._cancelar_edicion_renglon()
        self._cargar_tabla_detalle_actual()

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
        self.campo_con_detalle.setEnabled(True)
        self.campo_con_detalle.setChecked(False)
        self._vaciar_renglones_actuales()
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
            if self._comprobante_en_edicion is None and self._modo_detalle:
                if not self._renglones_actuales:
                    QMessageBox.warning(self, "Sin renglones", "Agregá al menos un renglón de detalle.")
                    return
                comprobante_id = servicio_comprobantes.alta_comprobante_con_detalle(
                    self.conexion, tipo_id, numero, fecha, self._cliente_id, sucursal_id,
                    self._renglones_actuales, descuento_pct=descuento, con_iva=con_iva,
                    nombre_particular=nombre_particular, forzar_numero_repetido=forzar,
                )
                self._ids_sesion.append(comprobante_id)
            elif self._comprobante_en_edicion is None:
                comprobante_id = servicio_comprobantes.alta_comprobante(
                    self.conexion, tipo_id, numero, fecha, self._cliente_id, sucursal_id,
                    monto_lista, descuento_pct=descuento, con_iva=con_iva,
                    nombre_particular=nombre_particular, forzar_numero_repetido=forzar,
                )
                self._ids_sesion.append(comprobante_id)
            else:
                comprobante_id = self._comprobante_en_edicion
                campos = {"numero": numero, "fecha": fecha}
                if not self._bloqueado_para_editar_montos(comprobante_id):
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
        self.campo_con_detalle.setEnabled(True)
        self.campo_numero.clear()
        self.campo_particular.clear()
        self.campo_monto_lista.setValue(0)
        if self._cliente_id is not None:
            cliente = datos_clientes.obtener_cliente(self.conexion, self._cliente_id)
            self.campo_descuento.setValue(float(cliente["descuento_default"]))
            self.campo_con_iva.setChecked(bool(cliente["con_iva_default"]))
        self._vaciar_renglones_actuales()
        if self._modo_detalle:
            self._sugerir_numero_detalle()
        self._recalcular()
        self.campo_numero.setFocus()

    # --- editar / anular desde la tabla de la sesión ---

    def _bloqueado_para_editar_montos(self, comprobante_id: int) -> bool:
        """Una vez que tiene pagos aplicados, o se cargó con detalle, el
        monto/descuento/IVA no se pueden tocar a mano: para corregirlos hay
        que anular y recargar (mismo criterio que con los pagos, acordado
        con el usuario para el detalle)."""
        if servicio_comprobantes.tiene_pagos_aplicados(self.conexion, comprobante_id):
            return True
        return bool(servicio_comprobantes.listar_detalle_comprobante(self.conexion, comprobante_id))

    def _editar_seleccionado(self) -> None:
        fila = self.tabla_sesion.currentRow()
        if fila < 0 or fila >= len(self._ids_sesion):
            return
        comprobante_id = self._ids_sesion[fila]
        comprobante = datos_comprobantes.obtener_comprobante(self.conexion, comprobante_id)

        self._comprobante_en_edicion = comprobante_id
        self.campo_con_detalle.setChecked(False)
        self.campo_con_detalle.setEnabled(False)
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

        tiene_pagos = servicio_comprobantes.tiene_pagos_aplicados(self.conexion, comprobante_id)
        tiene_detalle = bool(servicio_comprobantes.listar_detalle_comprobante(self.conexion, comprobante_id))
        bloqueado = tiene_pagos or tiene_detalle
        self._deshabilitar_campos_montos(bloqueado)
        self.boton_cancelar_edicion.setVisible(True)
        if tiene_pagos:
            QMessageBox.information(
                self, "Tiene pagos aplicados",
                "Este comprobante ya tiene pagos aplicados: no se puede cambiar el monto, "
                "el descuento ni el IVA. Podés corregir el número y la fecha, o anularlo.",
            )
        elif tiene_detalle:
            QMessageBox.information(
                self, "Tiene detalle cargado",
                "Este comprobante se cargó con detalle: no se puede cambiar el monto, el "
                "descuento ni el IVA desde acá. Para corregirlo, anulalo y cargalo de nuevo.",
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
