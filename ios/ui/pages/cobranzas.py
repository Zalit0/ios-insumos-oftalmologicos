"""Pantalla Cobranzas: elegir cliente, ver sus remitos pendientes, tildar
cuáles cubre el pago, indicar una o varias formas de pago (con los datos
del cheque si corresponde), y aplicar saldo a favor a remitos pendientes
sin movimiento de caja (docs/PLAN.md, "Pantallas")."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ios.data import clientes as datos_clientes
from ios.data import comprobantes as datos_comprobantes
from ios.data import formas_pago as datos_formas_pago
from ios.data import recibos as datos_recibos
from ios.domain.calculos import calcular_saldo_a_favor, calcular_saldo_comprobante
from ios.reports.formato import formato_fecha, formato_moneda
from ios.reports.pdf_comun import abrir_pdf, ruta_pdf_automatica
from ios.reports.recibo import generar_pdf_recibo
from ios.services.caja import hay_caja_abierta_hoy
from ios.services.cobranzas import AplicacionARemito, DatosCheque, Pago, aplicar_saldo_a_favor, asentar_cobranza
from ios.ui.pages.caja_diaria import abrir_caja_con_dialogo
from ios.ui.widgets import CampoDecimal, ajustar_columnas

COLUMNA_TILDE = 0
COLUMNA_NUMERO = 1
COLUMNA_FECHA = 2
COLUMNA_SALDO = 3
COLUMNA_MONTO = 4


class _FilaFormaPago(QWidget):
    """Una forma de pago del recibo: forma, monto y —si es cheque— sus
    datos (número, banco, fecha de cobro)."""

    def __init__(self, formas_pago: list[sqlite3.Row], al_quitar, al_cambiar_monto=None) -> None:
        super().__init__()
        self._tipos_por_id = {f["id"]: f["tipo"] for f in formas_pago}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.combo_forma = QComboBox()
        for forma in formas_pago:
            self.combo_forma.addItem(forma["nombre"], forma["id"])
        self.combo_forma.currentIndexChanged.connect(self._actualizar_visibilidad_cheque)

        self.monto = CampoDecimal()
        self.monto.setRange(0, 99_999_999)
        self.monto.setDecimals(2)
        if al_cambiar_monto is not None:
            self.monto.valueChanged.connect(al_cambiar_monto)

        self.cheque_numero = QLineEdit()
        self.cheque_numero.setPlaceholderText("Nº cheque")
        self.cheque_banco = QLineEdit()
        self.cheque_banco.setPlaceholderText("Banco")
        self.cheque_fecha_cobro = QDateEdit(QDate.currentDate())
        self.cheque_fecha_cobro.setCalendarPopup(True)

        boton_quitar = QPushButton("Quitar")
        boton_quitar.clicked.connect(lambda: al_quitar(self))

        layout.addWidget(self.combo_forma)
        layout.addWidget(self.monto)
        layout.addWidget(self.cheque_numero)
        layout.addWidget(self.cheque_banco)
        layout.addWidget(self.cheque_fecha_cobro)
        layout.addWidget(boton_quitar)

        self._actualizar_visibilidad_cheque()

    def _es_cheque(self) -> bool:
        return self._tipos_por_id.get(self.combo_forma.currentData()) == "cheque"

    def _actualizar_visibilidad_cheque(self) -> None:
        es_cheque = self._es_cheque()
        self.cheque_numero.setVisible(es_cheque)
        self.cheque_banco.setVisible(es_cheque)
        self.cheque_fecha_cobro.setVisible(es_cheque)

    def a_pago(self) -> Pago:
        cheque = None
        if self._es_cheque():
            cheque = DatosCheque(
                numero=self.cheque_numero.text().strip(),
                banco=self.cheque_banco.text().strip() or None,
                fecha_cobro=self.cheque_fecha_cobro.date().toString("yyyy-MM-dd"),
            )
        return Pago(
            forma_pago_id=self.combo_forma.currentData(),
            monto=Decimal(str(self.monto.value())),
            cheque=cheque,
        )


class PaginaCobranzas(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self._filas_pago: list[_FilaFormaPago] = []

        layout_general = QVBoxLayout(self)

        encabezado = QHBoxLayout()
        encabezado.addWidget(QLabel("Cliente"))
        self._campo_cliente = QComboBox()
        self._campo_cliente.currentIndexChanged.connect(self._cargar_remitos_pendientes)
        encabezado.addWidget(self._campo_cliente, stretch=1)
        self._etiqueta_saldo_favor = QLabel("Saldo a favor: $ 0,00")
        encabezado.addWidget(self._etiqueta_saldo_favor)
        layout_general.addLayout(encabezado)

        fila_remitos = QHBoxLayout()
        fila_remitos.addWidget(QLabel("Remitos pendientes"))
        fila_remitos.addStretch(1)
        boton_seleccionar_todos = QPushButton("Seleccionar todos")
        boton_seleccionar_todos.clicked.connect(self._seleccionar_todos)
        fila_remitos.addWidget(boton_seleccionar_todos)
        layout_general.addLayout(fila_remitos)

        self._tabla = QTableWidget(0, 5)
        self._tabla.setHorizontalHeaderLabels(["Cubre", "Remito", "Fecha", "Saldo", "Monto a aplicar"])
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.itemChanged.connect(self._al_cambiar_item_tabla)
        layout_general.addWidget(self._tabla, stretch=1)

        # Suma de lo seleccionado, siempre visible (docs/AJUSTES_V1.1.md, 3.1).
        resumen_seleccion = QHBoxLayout()
        self._etiqueta_seleccionados = QLabel("Remitos seleccionados: 0 — $ 0,00")
        resumen_seleccion.addWidget(self._etiqueta_seleccionados)
        self._etiqueta_pagado = QLabel("Formas de pago cargadas: $ 0,00")
        resumen_seleccion.addWidget(self._etiqueta_pagado)
        self._etiqueta_diferencia = QLabel("Diferencia: $ 0,00")
        self._etiqueta_diferencia.setStyleSheet("font-weight: bold;")
        resumen_seleccion.addWidget(self._etiqueta_diferencia)
        resumen_seleccion.addStretch(1)
        layout_general.addLayout(resumen_seleccion)

        grupo_pagos = QGroupBox("Formas de pago")
        layout_grupo_pagos = QVBoxLayout(grupo_pagos)
        self._contenedor_filas = QVBoxLayout()
        area = QScrollArea()
        area.setWidgetResizable(True)
        contenido = QWidget()
        contenido.setLayout(self._contenedor_filas)
        area.setWidget(contenido)
        area.setMinimumHeight(110)
        area.setMaximumHeight(220)
        layout_grupo_pagos.addWidget(area)
        fila_botones_pago = QHBoxLayout()
        boton_agregar_pago = QPushButton("Agregar forma de pago")
        boton_agregar_pago.clicked.connect(self._agregar_fila_pago)
        fila_botones_pago.addWidget(boton_agregar_pago)
        boton_completar = QPushButton("Completar con el total seleccionado")
        boton_completar.clicked.connect(self._completar_con_total_seleccionado)
        fila_botones_pago.addWidget(boton_completar)
        layout_grupo_pagos.addLayout(fila_botones_pago)
        layout_general.addWidget(grupo_pagos)

        pie = QHBoxLayout()
        pie.addWidget(QLabel("Fecha del recibo"))
        self._campo_fecha = QDateEdit(QDate.currentDate())
        self._campo_fecha.setCalendarPopup(True)
        self._campo_fecha.setMaximumDate(QDate.currentDate())
        pie.addWidget(self._campo_fecha)
        pie.addStretch(1)
        boton_aplicar_favor = QPushButton("Aplicar saldo a favor (sin caja)")
        boton_aplicar_favor.clicked.connect(self._aplicar_saldo_a_favor)
        pie.addWidget(boton_aplicar_favor)
        boton_confirmar = QPushButton("Confirmar cobranza")
        boton_confirmar.clicked.connect(self._confirmar_cobranza)
        pie.addWidget(boton_confirmar)
        layout_general.addLayout(pie)

        self.actualizar()

    # --- carga de datos ---

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar (docs/AJUSTES_V1.1.md, etapa 1)

    def actualizar(self) -> None:
        self._campo_cliente.blockSignals(True)
        self._campo_cliente.clear()
        for cliente in datos_clientes.listar_clientes(self.conexion):
            self._campo_cliente.addItem(cliente["nombre"], cliente["id"])
        self._campo_cliente.blockSignals(False)
        self._cargar_remitos_pendientes()

    def _cliente_id(self) -> int | None:
        return self._campo_cliente.currentData()

    def _cargar_remitos_pendientes(self) -> None:
        self._tabla.blockSignals(True)
        self._tabla.setRowCount(0)
        cliente_id = self._cliente_id()
        if cliente_id is None:
            self._etiqueta_saldo_favor.setText("Saldo a favor: $ 0,00")
            self._tabla.blockSignals(False)
            self._actualizar_resumen()
            return

        pendientes = []
        for comprobante in datos_comprobantes.listar_comprobantes(
            self.conexion, cliente_id=cliente_id, estado="vigente"
        ):
            aplicado = datos_recibos.total_aplicado_a_comprobante(self.conexion, comprobante["id"])
            saldo = calcular_saldo_comprobante(comprobante["monto_final"], aplicado)
            if saldo > 0:
                pendientes.append((comprobante, saldo))

        self._tabla.setRowCount(len(pendientes))
        for fila, (comprobante, saldo) in enumerate(pendientes):
            item_tilde = QTableWidgetItem()
            item_tilde.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            item_tilde.setCheckState(Qt.Unchecked)
            item_tilde.setData(Qt.UserRole, comprobante["id"])
            self._tabla.setItem(fila, COLUMNA_TILDE, item_tilde)
            self._tabla.setItem(fila, COLUMNA_NUMERO, QTableWidgetItem(comprobante["numero"]))
            self._tabla.setItem(fila, COLUMNA_FECHA, QTableWidgetItem(formato_fecha(comprobante["fecha"])))
            self._tabla.setItem(fila, COLUMNA_SALDO, QTableWidgetItem(formato_moneda(saldo)))

            campo_monto = CampoDecimal()
            campo_monto.setRange(0, float(saldo))
            campo_monto.setDecimals(2)
            campo_monto.setValue(float(saldo))
            campo_monto.valueChanged.connect(self._actualizar_resumen)
            self._tabla.setCellWidget(fila, COLUMNA_MONTO, campo_monto)
        ajustar_columnas(self._tabla)

        total_recibos = datos_recibos.total_monto_recibos_vigentes_cliente(self.conexion, cliente_id)
        total_aplicado = datos_recibos.total_aplicado_de_recibos_cliente(self.conexion, cliente_id)
        saldo_a_favor = calcular_saldo_a_favor(total_recibos, total_aplicado)
        self._etiqueta_saldo_favor.setText(f"Saldo a favor: {formato_moneda(saldo_a_favor)}")

        self._tabla.blockSignals(False)
        self._actualizar_resumen()

    def _al_cambiar_item_tabla(self, item: QTableWidgetItem) -> None:
        if item.column() == COLUMNA_TILDE:
            self._redistribuir_montos()
            self._actualizar_resumen()

    def _seleccionar_todos(self) -> None:
        self._tabla.blockSignals(True)
        for fila in range(self._tabla.rowCount()):
            self._tabla.item(fila, COLUMNA_TILDE).setCheckState(Qt.Checked)
        self._tabla.blockSignals(False)
        self._redistribuir_montos()
        self._actualizar_resumen()

    # --- resumen en vivo (docs/AJUSTES_V1.1.md, etapa 3.1) ---

    def _total_pagado(self) -> Decimal:
        return sum((Decimal(str(fila.monto.value())) for fila in self._filas_pago), Decimal(0))

    def _filas_tildadas(self) -> list[int]:
        return [
            fila for fila in range(self._tabla.rowCount())
            if self._tabla.item(fila, COLUMNA_TILDE).checkState() == Qt.Checked
        ]

    def _total_pleno_tildado(self) -> Decimal:
        """Suma de los saldos de los remitos tildados (el total a cubrir),
        sin importar cómo haya quedado repartido el pago entre ellos."""
        return sum(
            (
                Decimal(str(self._tabla.cellWidget(fila, COLUMNA_MONTO).maximum()))
                for fila in self._filas_tildadas()
            ),
            Decimal(0),
        )

    def _redistribuir_montos(self) -> None:
        """Reparte lo pagado entre los remitos tildados, en el orden de la
        tabla (el más viejo primero): completa cada uno hasta su saldo y,
        si no alcanza, el remito donde se agota el pago queda con lo que
        llegó y el resto como saldo pendiente (docs: cobranzas, reparto
        automático del pago entre remitos tildados)."""
        if not self._filas_pago:
            return  # sin forma de pago cargada todavía: no hay nada que repartir
        filas = self._filas_tildadas()
        if not filas:
            return

        restante = self._total_pagado()
        for fila in filas:
            campo = self._tabla.cellWidget(fila, COLUMNA_MONTO)
            saldo = Decimal(str(campo.maximum()))
            asignado = min(max(restante, Decimal(0)), saldo)
            restante -= asignado
            campo.blockSignals(True)
            campo.setValue(float(asignado))
            campo.blockSignals(False)

    def _actualizar_resumen(self) -> None:
        filas_tildadas = self._filas_tildadas()
        total_seleccionado = self._total_pleno_tildado()
        total_pagado = self._total_pagado()
        diferencia = total_pagado - total_seleccionado

        self._etiqueta_seleccionados.setText(
            f"Remitos seleccionados: {len(filas_tildadas)} — {formato_moneda(total_seleccionado)}"
        )
        self._etiqueta_pagado.setText(f"Formas de pago cargadas: {formato_moneda(total_pagado)}")
        if diferencia > 0:
            texto = f"Excedente {formato_moneda(diferencia)} (queda como saldo a favor)"
        elif diferencia < 0:
            texto = f"Falta {formato_moneda(-diferencia)}"
        else:
            texto = "Coincide"
        self._etiqueta_diferencia.setText(f"Diferencia: {texto}")

    # --- formas de pago ---

    def _agregar_fila_pago(self) -> None:
        formas_pago = datos_formas_pago.listar_formas_pago(self.conexion)
        if not formas_pago:
            QMessageBox.warning(self, "Sin formas de pago", "No hay formas de pago configuradas.")
            return
        fila = _FilaFormaPago(formas_pago, self._quitar_fila_pago, self._al_cambiar_monto_pago)
        self._filas_pago.append(fila)
        self._contenedor_filas.addWidget(fila)
        self._actualizar_resumen()

    def _quitar_fila_pago(self, fila: _FilaFormaPago) -> None:
        self._filas_pago.remove(fila)
        self._contenedor_filas.removeWidget(fila)
        fila.deleteLater()
        self._redistribuir_montos()
        self._actualizar_resumen()

    def _al_cambiar_monto_pago(self) -> None:
        self._redistribuir_montos()
        self._actualizar_resumen()

    def _completar_con_total_seleccionado(self) -> None:
        if not self._filas_pago:
            QMessageBox.warning(
                self, "Sin formas de pago", "Agregá una forma de pago antes de completar el monto."
            )
            return
        total_seleccionado = self._total_pleno_tildado()
        ultima = self._filas_pago[-1]
        total_otras = self._total_pagado() - Decimal(str(ultima.monto.value()))
        faltante = max(Decimal(0), total_seleccionado - total_otras)
        ultima.monto.setValue(float(faltante))

    # --- selección de remitos tildados ---

    def _aplicaciones_tildadas(self) -> list[AplicacionARemito]:
        aplicaciones = []
        for fila in range(self._tabla.rowCount()):
            item = self._tabla.item(fila, COLUMNA_TILDE)
            if item.checkState() == Qt.Checked:
                monto = Decimal(str(self._tabla.cellWidget(fila, COLUMNA_MONTO).value()))
                if monto > 0:
                    aplicaciones.append(AplicacionARemito(item.data(Qt.UserRole), monto))
        return aplicaciones

    # --- caja obligatoria para cobrar (docs/AJUSTES_V1.1.md) ---

    def _asegurar_caja_abierta(self) -> bool:
        fecha_hoy = date.today().isoformat()
        if hay_caja_abierta_hoy(self.conexion, fecha_hoy):
            return True

        respuesta = QMessageBox.question(
            self, "Caja cerrada",
            "La caja de hoy está cerrada. ¿Querés abrirla para poder cobrar?",
        )
        if respuesta != QMessageBox.Yes:
            return False
        return abrir_caja_con_dialogo(self.conexion, fecha_hoy, self)

    # --- acciones ---

    def _confirmar_cobranza(self) -> None:
        cliente_id = self._cliente_id()
        if cliente_id is None:
            return
        if not self._filas_pago:
            QMessageBox.warning(self, "Falta la forma de pago", "Agregá al menos una forma de pago.")
            return

        pagos = [fila.a_pago() for fila in self._filas_pago]
        if sum((p.monto for p in pagos), Decimal(0)) <= 0:
            QMessageBox.warning(self, "Monto en cero", "El monto del pago tiene que ser mayor a cero.")
            return

        fecha_cobro = self._campo_fecha.date().toString("yyyy-MM-dd")
        fecha_hoy = date.today().isoformat()
        if fecha_cobro < fecha_hoy:
            respuesta = QMessageBox.question(
                self, "Fecha anterior a hoy",
                f"La fecha del pago ({formato_fecha(fecha_cobro)}) es anterior a hoy. "
                "¿Confirmás que es correcta?",
            )
            if respuesta != QMessageBox.Yes:
                return

        if not self._asegurar_caja_abierta():
            return

        aplicaciones = self._aplicaciones_tildadas()

        try:
            recibo_id = asentar_cobranza(
                self.conexion, cliente_id, fecha_cobro, pagos, aplicaciones, fecha_hoy=fecha_hoy,
            )
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo asentar la cobranza", str(error))
            return

        self._filas_pago.clear()
        while self._contenedor_filas.count():
            item = self._contenedor_filas.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cargar_remitos_pendientes()

        self._ofrecer_pdf_recibo(recibo_id)

    def _aplicar_saldo_a_favor(self) -> None:
        cliente_id = self._cliente_id()
        if cliente_id is None:
            return
        aplicaciones = self._aplicaciones_tildadas()
        if not aplicaciones:
            QMessageBox.warning(self, "Nada tildado", "Tildá los remitos a los que aplicar el saldo a favor.")
            return

        try:
            aplicar_saldo_a_favor(self.conexion, cliente_id, aplicaciones)
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo aplicar", str(error))
            return

        self._cargar_remitos_pendientes()

    def _ofrecer_pdf_recibo(self, recibo_id: int) -> None:
        recibo = datos_recibos.obtener_recibo(self.conexion, recibo_id)
        respuesta = QMessageBox.question(
            self, "Recibo generado",
            f"Se generó el recibo Nº {recibo['numero']}. ¿Guardarlo en PDF?",
        )
        if respuesta != QMessageBox.Yes:
            return
        fecha = formato_fecha(recibo["fecha"]).replace("/", "-")
        ruta = ruta_pdf_automatica(f"Recibo {recibo['numero']} - {fecha}.pdf", subcarpeta="Recibos")
        generar_pdf_recibo(self.conexion, recibo_id, ruta)
        abrir_pdf(ruta)
