"""Pantalla Cuenta corriente: movimientos, saldo y saldo a favor de un
cliente, agrupados por sucursal, con el total consolidado. Permite ver el
total a hoy, o filtrar por un mes o un rango de fechas: en ese caso el
saldo pendiente de antes del período se arrastra como "saldo anterior"
(docs/PLAN.md, "Pantallas" y etapa 5; docs/AJUSTES_V1.1.md, Cuenta
corriente con filtro de fechas/mes). Exportable a PDF en ambos modos."""

from __future__ import annotations

import sqlite3
from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ios.data import clientes as datos_clientes
from ios.reports.estado_cuenta import (
    generar_pdf_estado_cuenta_periodo,
    generar_pdf_estado_cuenta_pendientes,
    generar_pdf_historial_movimientos,
)
from ios.reports.formato import formato_fecha, formato_moneda
from ios.services.cuenta_corriente import estado_de_cuenta_cliente, estado_de_cuenta_periodo
from ios.services.graficos_resumen_mensual import primer_dia_del_mes, ultimo_dia_del_mes
from ios.ui.widgets import BuscadorCliente, ajustar_columnas

NOMBRES_MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

MODO_PENDIENTES = "pendientes"
MODO_COMPLETO = "completo"
MODO_HISTORIAL = "historial"

OPCIONES_MODO_PDF = [
    ("Solo comprobantes con saldo pendiente", MODO_PENDIENTES),
    ("Estado de cuenta completo del período", MODO_COMPLETO),
    ("Historial completo de movimientos", MODO_HISTORIAL),
]


def _vaciar_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


class PaginaCuentaCorriente(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self._cliente_id: int | None = None
        self._modo_periodo = False
        hoy = date.today()

        layout_general = QVBoxLayout(self)

        fila_cliente = QHBoxLayout()
        fila_cliente.addWidget(QLabel("Cliente"))
        self._buscador_cliente = BuscadorCliente(conexion)
        self._buscador_cliente.clienteElegido.connect(self._al_elegir_cliente)
        fila_cliente.addWidget(self._buscador_cliente, stretch=1)
        self._etiqueta_cliente = QLabel("")
        fila_cliente.addWidget(self._etiqueta_cliente)
        layout_general.addLayout(fila_cliente)

        fila_periodo = QHBoxLayout()
        fila_periodo.addWidget(QLabel("Mes"))
        self._campo_mes = QComboBox()
        for numero, nombre in enumerate(NOMBRES_MESES, start=1):
            self._campo_mes.addItem(nombre, numero)
        self._campo_mes.setCurrentIndex(hoy.month - 1)
        fila_periodo.addWidget(self._campo_mes)
        self._campo_anio = QSpinBox()
        self._campo_anio.setRange(2000, 2100)
        self._campo_anio.setValue(hoy.year)
        fila_periodo.addWidget(self._campo_anio)
        boton_usar_mes = QPushButton("Usar mes")
        boton_usar_mes.clicked.connect(self._usar_mes)
        fila_periodo.addWidget(boton_usar_mes)

        fila_periodo.addWidget(QLabel("Desde"))
        self._campo_desde = QDateEdit(QDate(hoy.year, hoy.month, 1))
        self._campo_desde.setCalendarPopup(True)
        fila_periodo.addWidget(self._campo_desde)
        fila_periodo.addWidget(QLabel("Hasta"))
        self._campo_hasta = QDateEdit(QDate.currentDate())
        self._campo_hasta.setCalendarPopup(True)
        fila_periodo.addWidget(self._campo_hasta)

        boton_consultar = QPushButton("Consultar")
        boton_consultar.clicked.connect(self._consultar_periodo)
        fila_periodo.addWidget(boton_consultar)
        boton_ver_todo = QPushButton("Ver todo")
        boton_ver_todo.clicked.connect(self._ver_todo)
        fila_periodo.addWidget(boton_ver_todo)
        fila_periodo.addStretch(1)

        fila_periodo.addWidget(QLabel("Modalidad del PDF"))
        self._campo_modo_pdf = QComboBox()
        for etiqueta, valor in OPCIONES_MODO_PDF:
            self._campo_modo_pdf.addItem(etiqueta, valor)
        self._campo_modo_pdf.setToolTip(
            "Qué incluir al exportar: solo lo pendiente de cobrar (para gestionar cobranzas), "
            "el estado de cuenta completo del período elegido, o el historial de remitos y "
            "recibos del período mezclados en una sola línea de tiempo."
        )
        fila_periodo.addWidget(self._campo_modo_pdf)

        boton_exportar = QPushButton("Exportar PDF")
        boton_exportar.clicked.connect(self._exportar_pdf)
        fila_periodo.addWidget(boton_exportar)
        layout_general.addLayout(fila_periodo)

        self._pestanas_sucursales = QTabWidget()
        layout_general.addWidget(self._pestanas_sucursales, stretch=1)

        self._layout_resumen = QVBoxLayout()
        layout_general.addLayout(self._layout_resumen)

        self.actualizar()

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar (docs/AJUSTES_V1.1.md, etapa 1)

    def actualizar(self) -> None:
        self._buscador_cliente.cargar_clientes()
        self._mostrar_estado_de_cuenta()

    # --- elegir cliente / período ---

    def _al_elegir_cliente(self, cliente_id: int) -> None:
        self._cliente_id = cliente_id
        cliente = datos_clientes.obtener_cliente(self.conexion, cliente_id)
        self._etiqueta_cliente.setText(cliente["nombre"])
        self._mostrar_estado_de_cuenta()

    def _usar_mes(self) -> None:
        mes = f"{self._campo_anio.value()}-{self._campo_mes.currentData():02d}"
        self._campo_desde.setDate(QDate.fromString(primer_dia_del_mes(mes), "yyyy-MM-dd"))
        self._campo_hasta.setDate(QDate.fromString(ultimo_dia_del_mes(mes), "yyyy-MM-dd"))
        self._consultar_periodo()

    def _consultar_periodo(self) -> None:
        self._modo_periodo = True
        self._mostrar_estado_de_cuenta()

    def _ver_todo(self) -> None:
        self._modo_periodo = False
        self._mostrar_estado_de_cuenta()

    def _fecha_desde(self) -> str:
        return self._campo_desde.date().toString("yyyy-MM-dd")

    def _fecha_hasta(self) -> str:
        return self._campo_hasta.date().toString("yyyy-MM-dd")

    # --- vista total (sin filtro de fechas) ---

    def _pestana_sucursal_total(self, sucursal) -> QWidget:
        pestana = QWidget()
        layout = QVBoxLayout(pestana)

        tabla = QTableWidget(len(sucursal.comprobantes), 4)
        tabla.setHorizontalHeaderLabels(["Remito", "Fecha", "Monto final", "Saldo"])
        tabla.verticalHeader().setVisible(False)
        for fila, comprobante in enumerate(sucursal.comprobantes):
            tabla.setItem(fila, 0, QTableWidgetItem(comprobante.numero))
            tabla.setItem(fila, 1, QTableWidgetItem(formato_fecha(comprobante.fecha)))
            tabla.setItem(fila, 2, QTableWidgetItem(formato_moneda(comprobante.monto_final)))
            tabla.setItem(fila, 3, QTableWidgetItem(formato_moneda(comprobante.saldo)))
        ajustar_columnas(tabla)
        layout.addWidget(tabla)

        etiqueta_saldo = QLabel(f"<b>Saldo {sucursal.nombre}: {formato_moneda(sucursal.saldo)}</b>")
        layout.addWidget(etiqueta_saldo)
        return pestana

    def _mostrar_total(self) -> None:
        estado = estado_de_cuenta_cliente(self.conexion, self._cliente_id)

        for sucursal in estado.sucursales:
            self._pestanas_sucursales.addTab(self._pestana_sucursal_total(sucursal), sucursal.nombre)

        _vaciar_layout(self._layout_resumen)
        resumen = QHBoxLayout()
        resumen.addWidget(QLabel(f"Saldo de remitos: {formato_moneda(estado.saldo_comprobantes)}"))
        resumen.addWidget(QLabel(f"Saldo a favor: {formato_moneda(estado.saldo_a_favor)}"))
        resumen.addStretch(1)
        etiqueta_consolidado = QLabel(f"Saldo consolidado: {formato_moneda(estado.saldo_consolidado)}")
        etiqueta_consolidado.setStyleSheet("font-weight: bold; font-size: 14px;")
        resumen.addWidget(etiqueta_consolidado)
        self._layout_resumen.addLayout(resumen)

    # --- vista de período (con arrastre de saldo) ---

    def _pestana_sucursal_periodo(self, sucursal) -> QWidget:
        pestana = QWidget()
        layout = QVBoxLayout(pestana)

        layout.addWidget(QLabel(f"Saldo anterior: {formato_moneda(sucursal.saldo_anterior)}"))

        tabla = QTableWidget(len(sucursal.movimientos), 4)
        tabla.setHorizontalHeaderLabels(["Remito", "Fecha", "Monto final", "Saldo"])
        tabla.verticalHeader().setVisible(False)
        for fila, movimiento in enumerate(sucursal.movimientos):
            tabla.setItem(fila, 0, QTableWidgetItem(movimiento.numero))
            tabla.setItem(fila, 1, QTableWidgetItem(formato_fecha(movimiento.fecha)))
            tabla.setItem(fila, 2, QTableWidgetItem(formato_moneda(movimiento.monto_final)))
            tabla.setItem(fila, 3, QTableWidgetItem(formato_moneda(movimiento.saldo)))
        ajustar_columnas(tabla)
        layout.addWidget(tabla)

        fila_cierre = QHBoxLayout()
        fila_cierre.addWidget(QLabel(
            f"Saldo del período {sucursal.nombre}: {formato_moneda(sucursal.saldo_del_periodo)}"
        ))
        fila_cierre.addStretch(1)
        etiqueta_cierre = QLabel(
            f"<b>Saldo al cierre {sucursal.nombre}: {formato_moneda(sucursal.saldo_cierre)}</b>"
        )
        fila_cierre.addWidget(etiqueta_cierre)
        layout.addLayout(fila_cierre)
        return pestana

    def _mostrar_periodo(self) -> None:
        estado = estado_de_cuenta_periodo(
            self.conexion, self._cliente_id, self._fecha_desde(), self._fecha_hasta()
        )

        for sucursal in estado.sucursales:
            self._pestanas_sucursales.addTab(self._pestana_sucursal_periodo(sucursal), sucursal.nombre)

        _vaciar_layout(self._layout_resumen)

        fila_favor = QHBoxLayout()
        fila_favor.addWidget(
            QLabel(f"Saldo a favor anterior: {formato_moneda(estado.saldo_a_favor_anterior)}")
        )
        fila_favor.addStretch(1)
        fila_favor.addWidget(
            QLabel(f"Saldo a favor al cierre: {formato_moneda(estado.saldo_a_favor_cierre)}")
        )
        self._layout_resumen.addLayout(fila_favor)

        self._layout_resumen.addWidget(QLabel("<b>Recibos del período</b>"))
        tabla_recibos = QTableWidget(len(estado.recibos_del_periodo), 3)
        tabla_recibos.setHorizontalHeaderLabels(["Recibo", "Fecha", "Monto"])
        tabla_recibos.verticalHeader().setVisible(False)
        for fila, recibo in enumerate(estado.recibos_del_periodo):
            tabla_recibos.setItem(fila, 0, QTableWidgetItem(str(recibo.numero)))
            tabla_recibos.setItem(fila, 1, QTableWidgetItem(formato_fecha(recibo.fecha)))
            tabla_recibos.setItem(fila, 2, QTableWidgetItem(formato_moneda(recibo.monto_total)))
        ajustar_columnas(tabla_recibos)
        self._layout_resumen.addWidget(tabla_recibos)

        fila_consolidado = QHBoxLayout()
        fila_consolidado.addWidget(
            QLabel(f"Saldo consolidado anterior: {formato_moneda(estado.saldo_consolidado_anterior)}")
        )
        fila_consolidado.addStretch(1)
        fila_consolidado.addWidget(
            QLabel(f"Saldo del período: {formato_moneda(estado.saldo_consolidado_del_periodo)}")
        )
        fila_consolidado.addStretch(1)
        etiqueta_consolidado_cierre = QLabel(
            f"Saldo consolidado al cierre: {formato_moneda(estado.saldo_consolidado_cierre)}"
        )
        etiqueta_consolidado_cierre.setStyleSheet("font-weight: bold; font-size: 14px;")
        fila_consolidado.addWidget(etiqueta_consolidado_cierre)
        self._layout_resumen.addLayout(fila_consolidado)

        etiqueta_aclaracion = QLabel(
            "Los saldos reflejan los pagos aplicados hasta hoy, no una foto fija del período: "
            "un remito ya cobrado no vuelve a figurar como saldo, sin importar cuándo se cobró."
        )
        etiqueta_aclaracion.setStyleSheet("color: #666; font-size: 11px;")
        etiqueta_aclaracion.setWordWrap(True)
        self._layout_resumen.addWidget(etiqueta_aclaracion)

    # --- despacho según el modo ---

    def _mostrar_estado_de_cuenta(self) -> None:
        self._pestanas_sucursales.clear()
        if self._cliente_id is None:
            _vaciar_layout(self._layout_resumen)
            return

        if self._modo_periodo:
            self._mostrar_periodo()
        else:
            self._mostrar_total()

    # --- exportar ---

    def _exportar_pdf(self) -> None:
        if self._cliente_id is None:
            return
        cliente = datos_clientes.obtener_cliente(self.conexion, self._cliente_id)
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Exportar estado de cuenta", f"Estado de cuenta - {cliente['nombre']}.pdf", "PDF (*.pdf)"
        )
        if not ruta:
            return

        modo = self._campo_modo_pdf.currentData()
        if modo == MODO_PENDIENTES:
            if self._modo_periodo:
                generar_pdf_estado_cuenta_pendientes(
                    self.conexion, self._cliente_id, ruta, self._fecha_desde(), self._fecha_hasta()
                )
            else:
                generar_pdf_estado_cuenta_pendientes(self.conexion, self._cliente_id, ruta)
        elif modo == MODO_HISTORIAL:
            generar_pdf_historial_movimientos(
                self.conexion, self._cliente_id, self._fecha_desde(), self._fecha_hasta(), ruta
            )
        else:
            generar_pdf_estado_cuenta_periodo(
                self.conexion, self._cliente_id, self._fecha_desde(), self._fecha_hasta(), ruta
            )
        QMessageBox.information(self, "Listo", "Se exportó el estado de cuenta.")
