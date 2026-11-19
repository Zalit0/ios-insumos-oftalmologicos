"""Pantalla Compras y proveedores: alta de proveedores, carga de facturas
con IVA y registro de pagos a proveedores, que generan el egreso de caja
(se puede pagar con un cheque en cartera) (docs/PLAN.md, "Pantallas")."""

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
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ios.data import cheques as datos_cheques
from ios.data import compras as datos_compras
from ios.data import configuracion as datos_configuracion
from ios.data import formas_pago as datos_formas_pago
from ios.data import pagos_proveedor as datos_pagos
from ios.data import proveedores as datos_proveedores
from ios.domain.calculos import calcular_iva_discriminado
from ios.reports.formato import formato_fecha, formato_moneda
from ios.services import compras as servicio_compras
from ios.services import pagos_proveedor as servicio_pagos
from ios.services import proveedores as servicio_proveedores
from ios.ui.widgets import CampoDecimal, ajustar_columnas

TASAS_IVA_COMPRA = [("21%", Decimal("21")), ("10,5%", Decimal("10.5")), ("0%", Decimal("0"))]


class _DialogoEditarPago(QDialog):
    """Corrige un pago a proveedor ya cargado (fecha, monto, forma de
    pago, cheque entregado y referencia) -- pensado para arreglar un
    monto mal tipeado sin tener que anular nada a mano."""

    def __init__(self, conexion: sqlite3.Connection, pago: sqlite3.Row, parent=None) -> None:
        super().__init__(parent)
        self.conexion = conexion
        self.pago_id = pago["id"]
        self.setWindowTitle("Editar pago a proveedor")

        formulario = QFormLayout(self)
        self.campo_fecha = QDateEdit(QDate.fromString(pago["fecha"], "yyyy-MM-dd"))
        self.campo_fecha.setCalendarPopup(True)
        formulario.addRow("Fecha", self.campo_fecha)

        self.campo_monto = CampoDecimal()
        self.campo_monto.setRange(0, 99_999_999)
        self.campo_monto.setDecimals(2)
        self.campo_monto.setValue(float(pago["monto"]))
        formulario.addRow("Monto", self.campo_monto)

        self.campo_forma = QComboBox()
        self._formas_pago_tipos: dict[int, str] = {}
        for forma in datos_formas_pago.listar_formas_pago(conexion):
            self.campo_forma.addItem(forma["nombre"], forma["id"])
            self._formas_pago_tipos[forma["id"]] = forma["tipo"]
        self.campo_forma.setCurrentIndex(self.campo_forma.findData(pago["forma_pago_id"]))
        self.campo_forma.currentIndexChanged.connect(self._actualizar_combo_cheques)
        formulario.addRow("Forma de pago", self.campo_forma)

        self.campo_cheque = QComboBox()
        self._cheque_original_id = pago["cheque_entregado_id"]
        formulario.addRow("Cheque en cartera", self.campo_cheque)

        self.campo_referencia = QLineEdit(pago["referencia"] or "")
        formulario.addRow("Referencia", self.campo_referencia)

        pie = QHBoxLayout()
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(self.reject)
        pie.addWidget(boton_cancelar)
        boton_guardar = QPushButton("Guardar corrección")
        boton_guardar.clicked.connect(self._guardar)
        pie.addWidget(boton_guardar)
        formulario.addRow(pie)

        self._actualizar_combo_cheques()

    def _actualizar_combo_cheques(self) -> None:
        forma_id = self.campo_forma.currentData()
        es_cheque = self._formas_pago_tipos.get(forma_id) == "cheque"
        self.campo_cheque.setEnabled(es_cheque)
        self.campo_cheque.clear()
        self.campo_cheque.addItem("(no usar cheque en cartera)", None)
        if not es_cheque:
            return

        if self._cheque_original_id is not None:
            cheque_original = datos_cheques.obtener_cheque(self.conexion, self._cheque_original_id)
            if cheque_original is not None and cheque_original["estado"] != "en_cartera":
                etiqueta = (
                    f"Nº {cheque_original['numero']} · {cheque_original['banco'] or '-'} · "
                    f"{formato_moneda(cheque_original['monto'])} (el que ya tiene este pago)"
                )
                self.campo_cheque.addItem(etiqueta, cheque_original["id"])

        for cheque in datos_cheques.listar_cheques_en_cartera(self.conexion):
            etiqueta = f"Nº {cheque['numero']} · {cheque['banco'] or '-'} · {formato_moneda(cheque['monto'])}"
            self.campo_cheque.addItem(etiqueta, cheque["id"])

        indice = self.campo_cheque.findData(self._cheque_original_id)
        self.campo_cheque.setCurrentIndex(max(indice, 0))

    def _guardar(self) -> None:
        try:
            servicio_pagos.editar_pago_proveedor(
                self.conexion,
                self.pago_id,
                fecha_hoy=date.today().isoformat(),
                fecha=self.campo_fecha.date().toString("yyyy-MM-dd"),
                monto=Decimal(str(self.campo_monto.value())),
                forma_pago_id=self.campo_forma.currentData(),
                cheque_entregado_id=self.campo_cheque.currentData(),
                referencia=self.campo_referencia.text().strip() or None,
            )
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return
        self.accept()


class PaginaComprasProveedores(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion

        layout_general = QVBoxLayout(self)
        self._pestanas = QTabWidget()
        layout_general.addWidget(self._pestanas)

        self._pestana_proveedores = self._armar_pestana_proveedores()
        self._pestana_compras = self._armar_pestana_compras()
        self._pestana_pagos = self._armar_pestana_pagos()
        self._pestanas.addTab(self._pestana_proveedores, "Proveedores")
        self._pestanas.addTab(self._pestana_compras, "Compras")
        self._pestanas.addTab(self._pestana_pagos, "Pagos a proveedores")
        self.INDICE_PESTANA_PAGOS = self._pestanas.indexOf(self._pestana_pagos)

        self.actualizar()

    # --- pestaña Proveedores ---

    def _armar_pestana_proveedores(self) -> QWidget:
        pagina = QWidget()
        layout = QHBoxLayout(pagina)

        columna_izquierda = QVBoxLayout()
        self._tabla_proveedores = QTableWidget(0, 2)
        self._tabla_proveedores.setHorizontalHeaderLabels(["Nombre", "CUIT"])
        self._tabla_proveedores.verticalHeader().setVisible(False)
        self._tabla_proveedores.setEditTriggers(QTableWidget.NoEditTriggers)
        columna_izquierda.addWidget(self._tabla_proveedores)
        layout.addLayout(columna_izquierda, stretch=2)

        grupo = QGroupBox("Nuevo proveedor")
        formulario = QFormLayout(grupo)
        self._campo_prov_nombre = QLineEdit()
        self._campo_prov_cuit = QLineEdit()
        formulario.addRow("Nombre", self._campo_prov_nombre)
        formulario.addRow("CUIT", self._campo_prov_cuit)
        boton_guardar = QPushButton("Guardar proveedor")
        boton_guardar.clicked.connect(self._guardar_proveedor)
        formulario.addRow(boton_guardar)

        columna_derecha = QVBoxLayout()
        columna_derecha.addWidget(grupo)
        columna_derecha.addStretch(1)
        layout.addLayout(columna_derecha, stretch=1)

        return pagina

    def _cargar_proveedores(self) -> None:
        proveedores = datos_proveedores.listar_proveedores(self.conexion)
        self._tabla_proveedores.setRowCount(len(proveedores))
        for fila, proveedor in enumerate(proveedores):
            self._tabla_proveedores.setItem(fila, 0, QTableWidgetItem(proveedor["nombre"]))
            self._tabla_proveedores.setItem(fila, 1, QTableWidgetItem(proveedor["cuit"] or ""))
        ajustar_columnas(self._tabla_proveedores)

        for combo in (self._campo_compra_proveedor, self._campo_pago_proveedor):
            seleccionado = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for proveedor in proveedores:
                combo.addItem(proveedor["nombre"], proveedor["id"])
            if seleccionado is not None:
                indice = combo.findData(seleccionado)
                if indice >= 0:
                    combo.setCurrentIndex(indice)
            combo.blockSignals(False)

    def _guardar_proveedor(self) -> None:
        nombre = self._campo_prov_nombre.text().strip()
        if not nombre:
            QMessageBox.warning(self, "Falta el nombre", "El nombre del proveedor es obligatorio.")
            return
        try:
            servicio_proveedores.alta_proveedor(
                self.conexion, nombre, self._campo_prov_cuit.text().strip() or None
            )
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return
        self._campo_prov_nombre.clear()
        self._campo_prov_cuit.clear()
        self._cargar_proveedores()

    # --- pestaña Compras ---

    def _armar_pestana_compras(self) -> QWidget:
        pagina = QWidget()
        layout = QHBoxLayout(pagina)

        columna_izquierda = QVBoxLayout()
        self._tabla_compras = QTableWidget(0, 6)
        self._tabla_compras.setHorizontalHeaderLabels(
            ["Proveedor", "Nº factura", "Fecha", "Monto", "Tasa IVA", "IVA"]
        )
        self._tabla_compras.horizontalHeader().setStretchLastSection(True)
        self._tabla_compras.verticalHeader().setVisible(False)
        self._tabla_compras.setEditTriggers(QTableWidget.NoEditTriggers)
        columna_izquierda.addWidget(self._tabla_compras)
        layout.addLayout(columna_izquierda, stretch=2)

        grupo = QGroupBox("Nueva factura")
        formulario = QFormLayout(grupo)
        self._campo_compra_proveedor = QComboBox()
        self._campo_compra_numero = QLineEdit()
        self._campo_compra_fecha = QDateEdit(QDate.currentDate())
        self._campo_compra_fecha.setCalendarPopup(True)
        self._campo_compra_monto = CampoDecimal()
        self._campo_compra_monto.setRange(0, 99_999_999)
        self._campo_compra_monto.setDecimals(2)
        self._campo_compra_monto.valueChanged.connect(self._recalcular_iva_compra)
        self._campo_compra_tasa_iva = QComboBox()
        for etiqueta, _tasa in TASAS_IVA_COMPRA:
            self._campo_compra_tasa_iva.addItem(etiqueta)
        self._campo_compra_tasa_iva.currentIndexChanged.connect(self._recalcular_iva_compra)
        self._campo_compra_iva = CampoDecimal()
        self._campo_compra_iva.setRange(0, 99_999_999)
        self._campo_compra_iva.setDecimals(2)

        formulario.addRow("Proveedor", self._campo_compra_proveedor)
        formulario.addRow("Nº factura", self._campo_compra_numero)
        formulario.addRow("Fecha", self._campo_compra_fecha)
        formulario.addRow("Monto (con IVA)", self._campo_compra_monto)
        formulario.addRow("Tasa IVA", self._campo_compra_tasa_iva)
        formulario.addRow("IVA", self._campo_compra_iva)
        boton_guardar = QPushButton("Guardar factura")
        boton_guardar.clicked.connect(self._guardar_compra)
        formulario.addRow(boton_guardar)

        columna_derecha = QVBoxLayout()
        columna_derecha.addWidget(grupo)
        columna_derecha.addStretch(1)
        layout.addLayout(columna_derecha, stretch=1)

        self._seleccionar_tasa_iva_por_defecto()
        self._recalcular_iva_compra()

        return pagina

    def _cargar_compras(self) -> None:
        compras = datos_compras.listar_compras(self.conexion)
        self._tabla_compras.setRowCount(len(compras))
        for fila, compra in enumerate(compras):
            proveedor = datos_proveedores.obtener_proveedor(self.conexion, compra["proveedor_id"])
            iva_texto = formato_moneda(compra["iva"])
            if compra["iva_manual"]:
                iva_texto += " (manual)"
            self._tabla_compras.setItem(fila, 0, QTableWidgetItem(proveedor["nombre"]))
            self._tabla_compras.setItem(fila, 1, QTableWidgetItem(compra["numero_factura"]))
            self._tabla_compras.setItem(fila, 2, QTableWidgetItem(formato_fecha(compra["fecha"])))
            self._tabla_compras.setItem(fila, 3, QTableWidgetItem(formato_moneda(compra["monto"])))
            self._tabla_compras.setItem(fila, 4, QTableWidgetItem(f"{compra['tasa_iva']}%"))
            self._tabla_compras.setItem(fila, 5, QTableWidgetItem(iva_texto))
        ajustar_columnas(self._tabla_compras)

    def _tasa_iva_elegida(self) -> Decimal:
        return TASAS_IVA_COMPRA[self._campo_compra_tasa_iva.currentIndex()][1]

    def _recalcular_iva_compra(self) -> None:
        configuracion = datos_configuracion.obtener_configuracion(self.conexion)
        decimales = configuracion["redondeo_decimales"]
        monto = Decimal(str(self._campo_compra_monto.value()))
        iva = calcular_iva_discriminado(monto, True, self._tasa_iva_elegida(), decimales)
        self._campo_compra_iva.blockSignals(True)
        self._campo_compra_iva.setValue(float(iva))
        self._campo_compra_iva.blockSignals(False)

    def _guardar_compra(self) -> None:
        proveedor_id = self._campo_compra_proveedor.currentData()
        if proveedor_id is None:
            QMessageBox.warning(self, "Falta el proveedor", "Dado de alta un proveedor primero.")
            return
        try:
            servicio_compras.alta_compra(
                self.conexion,
                proveedor_id,
                self._campo_compra_fecha.date().toString("yyyy-MM-dd"),
                self._campo_compra_numero.text().strip(),
                Decimal(str(self._campo_compra_monto.value())),
                tasa_iva=self._tasa_iva_elegida(),
                iva=Decimal(str(self._campo_compra_iva.value())),
            )
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return
        self._campo_compra_numero.clear()
        self._campo_compra_monto.setValue(0)
        self._seleccionar_tasa_iva_por_defecto()
        self._recalcular_iva_compra()
        self._cargar_compras()

    def _seleccionar_tasa_iva_por_defecto(self) -> None:
        configuracion = datos_configuracion.obtener_configuracion(self.conexion)
        tasa_default = configuracion["iva_pct"]
        for indice, (_etiqueta, tasa) in enumerate(TASAS_IVA_COMPRA):
            if tasa == tasa_default:
                self._campo_compra_tasa_iva.setCurrentIndex(indice)
                return
        self._campo_compra_tasa_iva.setCurrentIndex(0)

    # --- pestaña Pagos a proveedores ---

    def _armar_pestana_pagos(self) -> QWidget:
        pagina = QWidget()
        layout = QHBoxLayout(pagina)

        columna_izquierda = QVBoxLayout()
        self._tabla_pagos = QTableWidget(0, 4)
        self._tabla_pagos.setHorizontalHeaderLabels(["Proveedor", "Fecha", "Monto", "Forma de pago"])
        self._tabla_pagos.verticalHeader().setVisible(False)
        self._tabla_pagos.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla_pagos.setSelectionBehavior(QTableWidget.SelectRows)
        columna_izquierda.addWidget(self._tabla_pagos)
        boton_editar_pago = QPushButton("Editar pago seleccionado")
        boton_editar_pago.clicked.connect(self._editar_pago_seleccionado)
        columna_izquierda.addWidget(boton_editar_pago)
        layout.addLayout(columna_izquierda, stretch=2)

        grupo = QGroupBox("Nuevo pago")
        formulario = QFormLayout(grupo)
        self._campo_pago_proveedor = QComboBox()
        self._campo_pago_fecha = QDateEdit(QDate.currentDate())
        self._campo_pago_fecha.setCalendarPopup(True)
        self._campo_pago_monto = CampoDecimal()
        self._campo_pago_monto.setRange(0, 99_999_999)
        self._campo_pago_monto.setDecimals(2)
        self._campo_pago_forma = QComboBox()
        self._campo_pago_forma.currentIndexChanged.connect(self._actualizar_combo_cheques)
        self._campo_pago_cheque = QComboBox()
        self._campo_pago_referencia = QLineEdit()

        formulario.addRow("Proveedor", self._campo_pago_proveedor)
        formulario.addRow("Fecha", self._campo_pago_fecha)
        formulario.addRow("Monto", self._campo_pago_monto)
        formulario.addRow("Forma de pago", self._campo_pago_forma)
        formulario.addRow("Cheque en cartera", self._campo_pago_cheque)
        formulario.addRow("Referencia", self._campo_pago_referencia)
        boton_registrar = QPushButton("Registrar pago")
        boton_registrar.clicked.connect(self._registrar_pago)
        formulario.addRow(boton_registrar)

        columna_derecha = QVBoxLayout()
        columna_derecha.addWidget(grupo)
        columna_derecha.addStretch(1)
        layout.addLayout(columna_derecha, stretch=1)

        return pagina

    def _cargar_formas_pago(self) -> None:
        self._campo_pago_forma.blockSignals(True)
        self._campo_pago_forma.clear()
        self._formas_pago_tipos = {}
        for forma in datos_formas_pago.listar_formas_pago(self.conexion):
            self._campo_pago_forma.addItem(forma["nombre"], forma["id"])
            self._formas_pago_tipos[forma["id"]] = forma["tipo"]
        self._campo_pago_forma.blockSignals(False)
        self._actualizar_combo_cheques()

    def _actualizar_combo_cheques(self) -> None:
        forma_id = self._campo_pago_forma.currentData()
        es_cheque = self._formas_pago_tipos.get(forma_id) == "cheque"
        self._campo_pago_cheque.setEnabled(es_cheque)
        self._campo_pago_cheque.clear()
        self._campo_pago_cheque.addItem("(no usar cheque en cartera)", None)
        if not es_cheque:
            return
        for cheque in datos_cheques.listar_cheques_en_cartera(self.conexion):
            etiqueta = f"Nº {cheque['numero']} · {cheque['banco'] or '-'} · {formato_moneda(cheque['monto'])}"
            self._campo_pago_cheque.addItem(etiqueta, cheque["id"])

    def _cargar_pagos(self) -> None:
        pagos = datos_pagos.listar_pagos_proveedor(self.conexion)
        self._tabla_pagos.setRowCount(len(pagos))
        for fila, pago in enumerate(pagos):
            proveedor = datos_proveedores.obtener_proveedor(self.conexion, pago["proveedor_id"])
            forma = self.conexion.execute(
                "SELECT nombre FROM formas_pago WHERE id = ?", (pago["forma_pago_id"],)
            ).fetchone()["nombre"]
            item_proveedor = QTableWidgetItem(proveedor["nombre"])
            item_proveedor.setData(Qt.UserRole, pago["id"])
            self._tabla_pagos.setItem(fila, 0, item_proveedor)
            self._tabla_pagos.setItem(fila, 1, QTableWidgetItem(formato_fecha(pago["fecha"])))
            self._tabla_pagos.setItem(fila, 2, QTableWidgetItem(formato_moneda(pago["monto"])))
            self._tabla_pagos.setItem(fila, 3, QTableWidgetItem(forma))
        ajustar_columnas(self._tabla_pagos)

    def _editar_pago_seleccionado(self) -> None:
        fila = self._tabla_pagos.currentRow()
        if fila < 0:
            QMessageBox.warning(self, "Nada seleccionado", "Elegí un pago de la lista.")
            return
        pago_id = self._tabla_pagos.item(fila, 0).data(Qt.UserRole)
        pago = datos_pagos.obtener_pago_proveedor(self.conexion, pago_id)
        dialogo = _DialogoEditarPago(self.conexion, pago, self)
        if dialogo.exec() == QDialog.Accepted:
            self._actualizar_combo_cheques()
            self._cargar_pagos()

    def _registrar_pago(self) -> None:
        proveedor_id = self._campo_pago_proveedor.currentData()
        if proveedor_id is None:
            QMessageBox.warning(self, "Falta el proveedor", "Dado de alta un proveedor primero.")
            return
        try:
            servicio_pagos.registrar_pago_proveedor(
                self.conexion,
                proveedor_id,
                self._campo_pago_fecha.date().toString("yyyy-MM-dd"),
                Decimal(str(self._campo_pago_monto.value())),
                self._campo_pago_forma.currentData(),
                cheque_entregado_id=self._campo_pago_cheque.currentData(),
                referencia=self._campo_pago_referencia.text().strip() or None,
            )
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo registrar", str(error))
            return
        self._campo_pago_monto.setValue(0)
        self._campo_pago_referencia.clear()
        self._actualizar_combo_cheques()
        self._cargar_pagos()

    # --- general ---

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar (docs/AJUSTES_V1.1.md, etapa 1)

    def actualizar(self) -> None:
        self._cargar_proveedores()
        self._cargar_formas_pago()
        self._cargar_compras()
        self._cargar_pagos()
