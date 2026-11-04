"""Pantalla Compras por cliente: cuánto compró un cliente entre dos
fechas (con subtotal por sucursal), o un ranking de todos los clientes
del período (docs/AJUSTES_V1.1.md, etapa 6.1)."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ios.data import clientes as datos_clientes
from ios.reports.compras_por_cliente import (
    generar_excel_compras_cliente,
    generar_excel_ranking_clientes,
    generar_pdf_compras_cliente,
    generar_pdf_ranking_clientes,
)
from ios.reports.formato import formato_fecha, formato_moneda
from ios.services.compras_por_cliente import compras_de_cliente, ranking_todos_los_clientes
from ios.ui.widgets import BuscadorCliente, ajustar_columnas

COLUMNAS_CLIENTE = ["Fecha", "Número", "Sucursal", "Lista", "Final", "IVA", "Cobrado", "Pendiente"]
COLUMNAS_RANKING = ["Cliente", "Comprobantes", "Total final"]


class PaginaComprasPorCliente(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self._cliente_id: int | None = None

        layout_general = QVBoxLayout(self)
        layout_general.addWidget(QLabel("Compras por cliente"))

        fila_cliente = QHBoxLayout()
        fila_cliente.addWidget(QLabel("Cliente"))
        self._buscador_cliente = BuscadorCliente(conexion)
        self._buscador_cliente.clienteElegido.connect(self._al_elegir_cliente)
        fila_cliente.addWidget(self._buscador_cliente, stretch=1)
        self._etiqueta_cliente = QLabel("(todos los clientes)")
        fila_cliente.addWidget(self._etiqueta_cliente)
        boton_todos = QPushButton("Ver todos")
        boton_todos.clicked.connect(self._ver_todos)
        fila_cliente.addWidget(boton_todos)
        self._campo_sucursal = QComboBox()
        self._campo_sucursal.currentIndexChanged.connect(self._cargar_tabla)
        fila_cliente.addWidget(self._campo_sucursal)
        layout_general.addLayout(fila_cliente)

        fila_fechas = QHBoxLayout()
        fila_fechas.addWidget(QLabel("Desde"))
        self._campo_desde = QDateEdit(QDate.currentDate().addMonths(-1))
        self._campo_desde.setCalendarPopup(True)
        self._campo_desde.dateChanged.connect(self._cargar_tabla)
        fila_fechas.addWidget(self._campo_desde)
        fila_fechas.addWidget(QLabel("Hasta"))
        self._campo_hasta = QDateEdit(QDate.currentDate())
        self._campo_hasta.setCalendarPopup(True)
        self._campo_hasta.dateChanged.connect(self._cargar_tabla)
        fila_fechas.addWidget(self._campo_hasta)
        fila_fechas.addStretch(1)
        boton_pdf = QPushButton("Exportar PDF")
        boton_pdf.clicked.connect(self._exportar_pdf)
        fila_fechas.addWidget(boton_pdf)
        boton_excel = QPushButton("Exportar Excel")
        boton_excel.clicked.connect(self._exportar_excel)
        fila_fechas.addWidget(boton_excel)
        layout_general.addLayout(fila_fechas)

        self._tabla = QTableWidget(0, len(COLUMNAS_RANKING))
        self._tabla.setHorizontalHeaderLabels(COLUMNAS_RANKING)
        self._tabla.verticalHeader().setVisible(False)
        self._tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        layout_general.addWidget(self._tabla, stretch=1)

        self._etiqueta_totales = QLabel("")
        layout_general.addWidget(self._etiqueta_totales)

        self._actualizar_visibilidad_sucursal()
        self.actualizar()

    # --- interfaz de navegación (docs/AJUSTES_V1.1.md, etapa 1) ---

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar

    def actualizar(self) -> None:
        self._buscador_cliente.cargar_clientes()
        self._cargar_tabla()

    # --- elegir cliente / todos ---

    def _al_elegir_cliente(self, cliente_id: int) -> None:
        self._cliente_id = cliente_id
        cliente = datos_clientes.obtener_cliente(self.conexion, cliente_id)
        self._etiqueta_cliente.setText(cliente["nombre"])
        self._cargar_combo_sucursal()
        self._actualizar_visibilidad_sucursal()
        self._cargar_tabla()

    def _ver_todos(self) -> None:
        self._cliente_id = None
        self._buscador_cliente.limpiar()
        self._etiqueta_cliente.setText("(todos los clientes)")
        self._actualizar_visibilidad_sucursal()
        self._cargar_tabla()

    def _cargar_combo_sucursal(self) -> None:
        self._campo_sucursal.blockSignals(True)
        self._campo_sucursal.clear()
        self._campo_sucursal.addItem("Todas las sucursales", None)
        if self._cliente_id is not None:
            for sucursal in datos_clientes.listar_sucursales(
                self.conexion, self._cliente_id, incluir_inactivas=True
            ):
                self._campo_sucursal.addItem(sucursal["nombre"], sucursal["id"])
        self._campo_sucursal.blockSignals(False)

    def _actualizar_visibilidad_sucursal(self) -> None:
        self._campo_sucursal.setVisible(self._cliente_id is not None)

    # --- fechas ---

    def _fecha_desde(self) -> str:
        return self._campo_desde.date().toString("yyyy-MM-dd")

    def _fecha_hasta(self) -> str:
        return self._campo_hasta.date().toString("yyyy-MM-dd")

    # --- tabla ---

    def _cargar_tabla(self) -> None:
        if self._cliente_id is None:
            self._cargar_tabla_ranking()
        else:
            self._cargar_tabla_cliente()

    def _cargar_tabla_ranking(self) -> None:
        self._tabla.setColumnCount(len(COLUMNAS_RANKING))
        self._tabla.setHorizontalHeaderLabels(COLUMNAS_RANKING)

        ranking = ranking_todos_los_clientes(self.conexion, self._fecha_desde(), self._fecha_hasta())
        self._tabla.setRowCount(len(ranking))
        for fila, item in enumerate(ranking):
            self._tabla.setItem(fila, 0, QTableWidgetItem(item.nombre))
            self._tabla.setItem(fila, 1, QTableWidgetItem(str(item.cantidad)))
            self._tabla.setItem(fila, 2, QTableWidgetItem(formato_moneda(item.total_final)))
        ajustar_columnas(self._tabla)

        total = sum((item.total_final for item in ranking), Decimal(0))
        self._etiqueta_totales.setText(f"{len(ranking)} clientes · Total: {formato_moneda(total)}")

    def _cargar_tabla_cliente(self) -> None:
        self._tabla.setColumnCount(len(COLUMNAS_CLIENTE))
        self._tabla.setHorizontalHeaderLabels(COLUMNAS_CLIENTE)

        resultado = compras_de_cliente(
            self.conexion,
            self._cliente_id,
            self._fecha_desde(),
            self._fecha_hasta(),
            sucursal_id=self._campo_sucursal.currentData(),
        )
        self._tabla.setRowCount(len(resultado.filas))
        for fila, item in enumerate(resultado.filas):
            self._tabla.setItem(fila, 0, QTableWidgetItem(formato_fecha(item.fecha)))
            self._tabla.setItem(fila, 1, QTableWidgetItem(item.numero))
            self._tabla.setItem(fila, 2, QTableWidgetItem(item.sucursal_nombre))
            self._tabla.setItem(fila, 3, QTableWidgetItem(formato_moneda(item.monto_lista)))
            self._tabla.setItem(fila, 4, QTableWidgetItem(formato_moneda(item.monto_final)))
            self._tabla.setItem(fila, 5, QTableWidgetItem(formato_moneda(item.iva_discriminado)))
            self._tabla.setItem(fila, 6, QTableWidgetItem(formato_moneda(item.cobrado)))
            self._tabla.setItem(fila, 7, QTableWidgetItem(formato_moneda(item.pendiente)))
        ajustar_columnas(self._tabla)

        texto = (
            f"{resultado.cantidad} comprobantes · Lista: {formato_moneda(resultado.total_lista)} · "
            f"Descuento: {formato_moneda(resultado.total_descuento)} · "
            f"Final: {formato_moneda(resultado.total_final)} · "
            f"IVA: {formato_moneda(resultado.total_iva)} · "
            f"Cobrado: {formato_moneda(resultado.total_cobrado)} · "
            f"Pendiente: {formato_moneda(resultado.total_pendiente)}"
        )
        if resultado.subtotales_por_sucursal:
            subtotales = " · ".join(
                f"{s.nombre}: {formato_moneda(s.monto_final)}" for s in resultado.subtotales_por_sucursal
            )
            texto += f"\nPor sucursal — {subtotales}"
        self._etiqueta_totales.setText(texto)

    # --- exportar ---

    def _exportar_pdf(self) -> None:
        if self._cliente_id is None:
            ruta, _ = QFileDialog.getSaveFileName(
                self, "Exportar ranking de clientes", "Compras por cliente.pdf", "PDF (*.pdf)"
            )
            if not ruta:
                return
            generar_pdf_ranking_clientes(self.conexion, self._fecha_desde(), self._fecha_hasta(), ruta)
        else:
            cliente = datos_clientes.obtener_cliente(self.conexion, self._cliente_id)
            ruta, _ = QFileDialog.getSaveFileName(
                self, "Exportar compras por cliente",
                f"Compras {cliente['nombre']}.pdf", "PDF (*.pdf)",
            )
            if not ruta:
                return
            generar_pdf_compras_cliente(
                self.conexion, self._cliente_id, cliente["nombre"],
                self._fecha_desde(), self._fecha_hasta(), ruta,
                sucursal_id=self._campo_sucursal.currentData(),
            )
        QMessageBox.information(self, "Listo", "Se exportó el reporte.")

    def _exportar_excel(self) -> None:
        if self._cliente_id is None:
            ruta, _ = QFileDialog.getSaveFileName(
                self, "Exportar ranking de clientes", "Compras por cliente.xlsx", "Excel (*.xlsx)"
            )
            if not ruta:
                return
            generar_excel_ranking_clientes(self.conexion, self._fecha_desde(), self._fecha_hasta(), ruta)
        else:
            cliente = datos_clientes.obtener_cliente(self.conexion, self._cliente_id)
            ruta, _ = QFileDialog.getSaveFileName(
                self, "Exportar compras por cliente",
                f"Compras {cliente['nombre']}.xlsx", "Excel (*.xlsx)",
            )
            if not ruta:
                return
            generar_excel_compras_cliente(
                self.conexion, self._cliente_id, cliente["nombre"],
                self._fecha_desde(), self._fecha_hasta(), ruta,
                sucursal_id=self._campo_sucursal.currentData(),
            )
        QMessageBox.information(self, "Listo", "Se exportó el reporte.")
