"""Pantalla Comprobantes: consulta (buscar, filtrar, editar, anular). La
carga rápida vive en la pantalla Facturación (docs/AJUSTES_V1.1.md,
etapa 2.3, D6)."""

from __future__ import annotations

import sqlite3
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
from ios.data import tipos_comprobante as datos_tipos_comprobante
from ios.domain.calculos import calcular_iva_discriminado, calcular_monto_final
from ios.data import configuracion as datos_configuracion
from ios.reports.formato import formato_fecha, formato_moneda
from ios.services import comprobantes as servicio_comprobantes
from ios.services.comprobantes import NumeroDuplicadoError
from ios.ui.widgets import BuscadorCliente, CampoDecimal, ajustar_columnas

ETIQUETAS_ESTADO = {"vigente": "Vigente", "anulado": "Anulado"}


class _DialogoEditarComprobante(QDialog):
    """Editar número, fecha y —si no tiene pagos aplicados— monto,
    descuento e IVA de un comprobante (docs/AJUSTES_V1.1.md, etapa 2.1.5,
    reutilizado acá para "Editar y anular siguen funcionando")."""

    def __init__(self, conexion: sqlite3.Connection, comprobante_id: int, parent=None) -> None:
        super().__init__(parent)
        self.conexion = conexion
        self.comprobante_id = comprobante_id
        comprobante = datos_comprobantes.obtener_comprobante(conexion, comprobante_id)
        self.setWindowTitle(f"Editar comprobante {comprobante['numero']}")

        formulario = QFormLayout(self)
        self.campo_numero = QLineEdit(comprobante["numero"])
        self.campo_fecha = QDateEdit(QDate.fromString(comprobante["fecha"], "yyyy-MM-dd"))
        self.campo_fecha.setCalendarPopup(True)
        self.campo_monto_lista = CampoDecimal()
        self.campo_monto_lista.setRange(0, 99_999_999)
        self.campo_monto_lista.setDecimals(2)
        self.campo_monto_lista.setValue(float(comprobante["monto_lista"]))
        self.campo_monto_lista.valueChanged.connect(self._recalcular)
        self.campo_descuento = CampoDecimal()
        self.campo_descuento.setRange(0, 100)
        self.campo_descuento.setDecimals(2)
        self.campo_descuento.setSuffix(" %")
        self.campo_descuento.setValue(float(comprobante["descuento_pct"]))
        self.campo_descuento.valueChanged.connect(self._recalcular)
        self.campo_con_iva = QCheckBox("Con IVA")
        self.campo_con_iva.setChecked(bool(comprobante["con_iva"]))
        self.campo_con_iva.stateChanged.connect(self._recalcular)
        self.etiqueta_final = QLabel()
        self.etiqueta_iva = QLabel()

        formulario.addRow("Número", self.campo_numero)
        formulario.addRow("Fecha", self.campo_fecha)
        formulario.addRow("Monto de lista", self.campo_monto_lista)
        formulario.addRow("Descuento", self.campo_descuento)
        formulario.addRow(self.campo_con_iva)
        formulario.addRow("Monto final", self.etiqueta_final)
        formulario.addRow("IVA discriminado", self.etiqueta_iva)

        self._bloqueado = servicio_comprobantes.tiene_pagos_aplicados(conexion, comprobante_id)
        self.campo_monto_lista.setEnabled(not self._bloqueado)
        self.campo_descuento.setEnabled(not self._bloqueado)
        self.campo_con_iva.setEnabled(not self._bloqueado)
        if self._bloqueado:
            aviso = QLabel(
                "Ya tiene pagos aplicados: no se puede cambiar el monto, el descuento "
                "ni el IVA. Para corregirlos, anulalo y cargalo de nuevo."
            )
            aviso.setWordWrap(True)
            aviso.setStyleSheet("color: #b45309;")
            formulario.addRow(aviso)

        botones = QHBoxLayout()
        boton_guardar = QPushButton("Guardar")
        boton_guardar.clicked.connect(self._guardar)
        botones.addWidget(boton_guardar)
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(self.reject)
        botones.addWidget(boton_cancelar)
        formulario.addRow(botones)

        self._recalcular()

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

    def _guardar(self, forzar: bool = False) -> None:
        numero = self.campo_numero.text().strip()
        if not numero:
            QMessageBox.warning(self, "Falta el número", "El número de comprobante es obligatorio.")
            return

        campos = {"numero": numero, "fecha": self.campo_fecha.date().toString("yyyy-MM-dd")}
        if not self._bloqueado:
            campos.update(
                monto_lista=Decimal(str(self.campo_monto_lista.value())),
                descuento_pct=Decimal(str(self.campo_descuento.value())),
                con_iva=self.campo_con_iva.isChecked(),
            )

        try:
            servicio_comprobantes.editar_comprobante(
                self.conexion, self.comprobante_id, forzar_numero_repetido=forzar, **campos
            )
        except NumeroDuplicadoError as error:
            respuesta = QMessageBox.question(self, "Número repetido", f"{error} ¿Guardar igual?")
            if respuesta == QMessageBox.Yes:
                self._guardar(forzar=True)
            return
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return

        self.accept()


class PaginaComprobantes(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self._cliente_filtro_id: int | None = None

        layout_general = QVBoxLayout(self)
        layout_general.addWidget(QLabel("Comprobantes"))

        fila_cliente = QHBoxLayout()
        fila_cliente.addWidget(QLabel("Cliente"))
        self._buscador_cliente = BuscadorCliente(conexion)
        self._buscador_cliente.clienteElegido.connect(self._al_elegir_cliente_filtro)
        fila_cliente.addWidget(self._buscador_cliente, stretch=1)
        self._etiqueta_cliente_filtro = QLabel("(todos)")
        fila_cliente.addWidget(self._etiqueta_cliente_filtro)
        boton_quitar_cliente = QPushButton("Quitar")
        boton_quitar_cliente.clicked.connect(self._quitar_filtro_cliente)
        fila_cliente.addWidget(boton_quitar_cliente)
        layout_general.addLayout(fila_cliente)

        fila_fechas = QHBoxLayout()
        fila_fechas.addWidget(QLabel("Desde"))
        self._campo_desde = QDateEdit(QDate.currentDate().addMonths(-1))
        self._campo_desde.setCalendarPopup(True)
        fila_fechas.addWidget(self._campo_desde)
        fila_fechas.addWidget(QLabel("Hasta"))
        self._campo_hasta = QDateEdit(QDate.currentDate())
        self._campo_hasta.setCalendarPopup(True)
        fila_fechas.addWidget(self._campo_hasta)
        boton_este_mes = QPushButton("Este mes")
        boton_este_mes.clicked.connect(self._rango_este_mes)
        fila_fechas.addWidget(boton_este_mes)
        boton_mes_anterior = QPushButton("Mes anterior")
        boton_mes_anterior.clicked.connect(self._rango_mes_anterior)
        fila_fechas.addWidget(boton_mes_anterior)
        boton_este_anio = QPushButton("Este año")
        boton_este_anio.clicked.connect(self._rango_este_anio)
        fila_fechas.addWidget(boton_este_anio)
        layout_general.addLayout(fila_fechas)

        fila_otros = QHBoxLayout()
        fila_otros.addWidget(QLabel("Tipo"))
        self._filtro_tipo = QComboBox()
        fila_otros.addWidget(self._filtro_tipo)
        fila_otros.addWidget(QLabel("Número"))
        self._filtro_numero = QLineEdit()
        self._filtro_numero.setPlaceholderText("Contiene...")
        fila_otros.addWidget(self._filtro_numero)
        fila_otros.addWidget(QLabel("Estado"))
        self._filtro_estado = QComboBox()
        self._filtro_estado.addItem("Todos", None)
        self._filtro_estado.addItem("Vigentes", "vigente")
        self._filtro_estado.addItem("Anulados", "anulado")
        fila_otros.addWidget(self._filtro_estado)
        boton_filtrar = QPushButton("Filtrar")
        boton_filtrar.clicked.connect(self._cargar_tabla)
        fila_otros.addWidget(boton_filtrar)
        layout_general.addLayout(fila_otros)

        self._tabla = QTableWidget(0, 8)
        self._tabla.setHorizontalHeaderLabels(
            ["Tipo", "Número", "Fecha", "Cliente", "Lista", "Final", "IVA", "Estado"]
        )
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.setSelectionBehavior(QTableWidget.SelectRows)
        self._tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla.itemDoubleClicked.connect(self._editar_seleccionado)
        layout_general.addWidget(self._tabla, stretch=1)

        pie = QHBoxLayout()
        self._etiqueta_totales = QLabel("")
        pie.addWidget(self._etiqueta_totales)
        pie.addStretch(1)
        boton_editar = QPushButton("Editar seleccionado")
        boton_editar.clicked.connect(self._editar_seleccionado)
        pie.addWidget(boton_editar)
        boton_anular = QPushButton("Anular seleccionado")
        boton_anular.clicked.connect(self._anular_seleccionado)
        pie.addWidget(boton_anular)
        boton_devolucion = QPushButton("Registrar devolución")
        boton_devolucion.clicked.connect(self._registrar_devolucion_seleccionado)
        pie.addWidget(boton_devolucion)
        layout_general.addLayout(pie)

        self._rango_este_mes()
        self.actualizar()

    # --- carga de datos ---

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar (docs/AJUSTES_V1.1.md, etapa 1)

    def actualizar(self) -> None:
        self._cargar_combo_tipos()
        self._buscador_cliente.cargar_clientes()
        self._cargar_tabla()

    def _cargar_combo_tipos(self) -> None:
        seleccionado = self._filtro_tipo.currentData()
        self._filtro_tipo.clear()
        self._filtro_tipo.addItem("Todos los tipos", None)
        for tipo in datos_tipos_comprobante.listar_tipos_comprobante(self.conexion):
            self._filtro_tipo.addItem(f"{tipo['nombre']} ({tipo['abreviatura']})", tipo["id"])
        indice = self._filtro_tipo.findData(seleccionado)
        self._filtro_tipo.setCurrentIndex(indice if indice >= 0 else 0)

    def _al_elegir_cliente_filtro(self, cliente_id: int) -> None:
        self._cliente_filtro_id = cliente_id
        cliente = datos_clientes.obtener_cliente(self.conexion, cliente_id)
        self._etiqueta_cliente_filtro.setText(cliente["nombre"])
        self._cargar_tabla()

    def _quitar_filtro_cliente(self) -> None:
        self._cliente_filtro_id = None
        self._buscador_cliente.limpiar()
        self._etiqueta_cliente_filtro.setText("(todos)")
        self._cargar_tabla()

    # --- atajos de fecha ---

    def _rango_este_mes(self) -> None:
        hoy = QDate.currentDate()
        self._campo_desde.setDate(QDate(hoy.year(), hoy.month(), 1))
        self._campo_hasta.setDate(QDate(hoy.year(), hoy.month(), hoy.daysInMonth()))
        self._cargar_tabla()

    def _rango_mes_anterior(self) -> None:
        mes_anterior = QDate.currentDate().addMonths(-1)
        self._campo_desde.setDate(QDate(mes_anterior.year(), mes_anterior.month(), 1))
        self._campo_hasta.setDate(
            QDate(mes_anterior.year(), mes_anterior.month(), mes_anterior.daysInMonth())
        )
        self._cargar_tabla()

    def _rango_este_anio(self) -> None:
        hoy = QDate.currentDate()
        self._campo_desde.setDate(QDate(hoy.year(), 1, 1))
        self._campo_hasta.setDate(QDate(hoy.year(), 12, 31))
        self._cargar_tabla()

    # --- tabla ---

    def _cargar_tabla(self) -> None:
        comprobantes = datos_comprobantes.listar_comprobantes(
            self.conexion,
            cliente_id=self._cliente_filtro_id,
            fecha_desde=self._campo_desde.date().toString("yyyy-MM-dd"),
            fecha_hasta=self._campo_hasta.date().toString("yyyy-MM-dd"),
            estado=self._filtro_estado.currentData(),
            tipo_comprobante_id=self._filtro_tipo.currentData(),
            numero=self._filtro_numero.text().strip() or None,
        )
        self._tabla.setRowCount(len(comprobantes))
        total_lista = total_final = total_iva = Decimal(0)
        for fila, comprobante in enumerate(comprobantes):
            tipo = self.conexion.execute(
                "SELECT abreviatura FROM tipos_comprobante WHERE id = ?",
                (comprobante["tipo_comprobante_id"],),
            ).fetchone()["abreviatura"]
            cliente = datos_clientes.obtener_cliente(self.conexion, comprobante["cliente_id"])

            self._tabla.setItem(fila, 0, QTableWidgetItem(tipo))
            self._tabla.setItem(fila, 1, QTableWidgetItem(comprobante["numero"]))
            self._tabla.setItem(fila, 2, QTableWidgetItem(formato_fecha(comprobante["fecha"])))
            self._tabla.setItem(fila, 3, QTableWidgetItem(cliente["nombre"]))
            self._tabla.setItem(fila, 4, QTableWidgetItem(formato_moneda(comprobante["monto_lista"])))
            self._tabla.setItem(fila, 5, QTableWidgetItem(formato_moneda(comprobante["monto_final"])))
            self._tabla.setItem(fila, 6, QTableWidgetItem(formato_moneda(comprobante["iva_discriminado"])))
            self._tabla.setItem(
                fila, 7, QTableWidgetItem(ETIQUETAS_ESTADO.get(comprobante["estado"], comprobante["estado"]))
            )
            self._tabla.item(fila, 0).setData(Qt.UserRole, comprobante["id"])

            total_lista += comprobante["monto_lista"]
            total_final += comprobante["monto_final"]
            total_iva += comprobante["iva_discriminado"]
        ajustar_columnas(self._tabla)

        self._etiqueta_totales.setText(
            f"{len(comprobantes)} comprobantes · Lista: {formato_moneda(total_lista)} · "
            f"Final: {formato_moneda(total_final)} · IVA: {formato_moneda(total_iva)}"
        )

    def _comprobante_seleccionado(self) -> int | None:
        filas = self._tabla.selectionModel().selectedRows()
        if not filas:
            return None
        return self._tabla.item(filas[0].row(), 0).data(Qt.UserRole)

    # --- acciones ---

    def _editar_seleccionado(self) -> None:
        comprobante_id = self._comprobante_seleccionado()
        if comprobante_id is None:
            return
        dialogo = _DialogoEditarComprobante(self.conexion, comprobante_id, self)
        if dialogo.exec() == QDialog.Accepted:
            self._cargar_tabla()

    def _anular_seleccionado(self) -> None:
        comprobante_id = self._comprobante_seleccionado()
        if comprobante_id is None:
            return
        respuesta = QMessageBox.question(self, "Anular", "¿Anular este comprobante?")
        if respuesta != QMessageBox.Yes:
            return
        try:
            servicio_comprobantes.anular_comprobante(self.conexion, comprobante_id)
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo anular", str(error))
            return
        self._cargar_tabla()

    def _registrar_devolucion_seleccionado(self) -> None:
        comprobante_id = self._comprobante_seleccionado()
        if comprobante_id is None:
            return
        respuesta = QMessageBox.question(
            self, "Registrar devolución",
            "¿Registrar la devolución de este comprobante? Se anula, no se cobra.",
        )
        if respuesta != QMessageBox.Yes:
            return

        tiene_renglones_de_stock = any(
            renglon["tipo_cristal_id"] is not None and renglon["pedido_especial_linea_id"] is None
            for renglon in servicio_comprobantes.listar_detalle_comprobante(self.conexion, comprobante_id)
        )
        ya_repuesto = False
        if tiene_renglones_de_stock:
            ya_repuesto = QMessageBox.question(
                self, "¿Ya estaba repuesto?",
                "¿Ese cristal ya se había vuelto a pedir al proveedor antes de esta devolución? "
                "Si contestás que sí, no se va a pedir de más la próxima vez que generes la "
                "reposición de ese cristal y esa graduación.",
            ) == QMessageBox.Yes

        try:
            servicio_comprobantes.registrar_devolucion(self.conexion, comprobante_id, ya_repuesto)
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo registrar", str(error))
            return
        self._cargar_tabla()
