"""Pantalla Caja diaria: movimientos del día por forma de pago; carga de
gastos, retiros, aportes y transferencias internas; cierre con saldo
teórico, arqueo por forma de pago y diferencia; historial de cierres
(docs/PLAN.md, "Pantallas" y etapa 7)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ios.data import caja as datos_caja
from ios.data import categorias_caja as datos_categorias
from ios.data import cierres_caja as datos_cierres
from ios.data import formas_pago as datos_formas_pago
from ios.reports.formato import formato_fecha, formato_moneda
from ios.services.caja import (
    abrir_caja,
    ajustar_saldo_inicial,
    cerrar_caja,
    cerrar_cajas_vencidas,
    registrar_movimiento_manual,
    registrar_transferencia_interna,
    saldo_inicial_propuesto,
    vista_previa_cierre,
)
from ios.ui.widgets import CampoDecimal, ajustar_columnas

ETIQUETAS_ESTADO_CIERRE = {"abierto": "Abierto", "cerrado": "Cerrado"}


class DialogoAbrirCaja(QDialog):
    """Muestra, por forma de pago, el saldo del último cierre (0 el primer
    día) y deja corregirlo antes de abrir la caja (docs/AJUSTES_V1.1.md,
    etapa 3.2). Si se corrige algún saldo, la nota es obligatoria."""

    def __init__(self, conexion: sqlite3.Connection, fecha: str, parent=None) -> None:
        super().__init__(parent)
        self.conexion = conexion
        self.fecha = fecha
        self.setWindowTitle("Abrir caja")
        self.modificados: list[tuple[int, Decimal]] = []
        self.nota: str | None = None

        layout = QVBoxLayout(self)

        encabezado = QHBoxLayout()
        for texto, ancho in (("Forma de pago", 170), ("Saldo del último cierre", 170), ("Saldo inicial", 170)):
            etiqueta = QLabel(f"<b>{texto}</b>")
            etiqueta.setFixedWidth(ancho)
            encabezado.addWidget(etiqueta)
        encabezado.addStretch(1)
        layout.addLayout(encabezado)

        self._campos: dict[int, tuple[Decimal, QDoubleSpinBox]] = {}
        for forma in datos_formas_pago.listar_formas_pago(conexion):
            propuesto = saldo_inicial_propuesto(conexion, forma["id"])

            fila = QHBoxLayout()
            etiqueta_forma = QLabel(forma["nombre"])
            etiqueta_forma.setFixedWidth(170)
            fila.addWidget(etiqueta_forma)
            etiqueta_propuesto = QLabel(formato_moneda(propuesto))
            etiqueta_propuesto.setFixedWidth(170)
            fila.addWidget(etiqueta_propuesto)
            campo = CampoDecimal()
            campo.setFixedWidth(170)
            campo.setRange(0, 99_999_999)
            campo.setDecimals(2)
            campo.setValue(float(propuesto))
            fila.addWidget(campo)
            fila.addStretch(1)
            layout.addLayout(fila)

            self._campos[forma["id"]] = (propuesto, campo)

        fila_nota = QHBoxLayout()
        fila_nota.addWidget(QLabel("Nota (obligatoria si corregís algún saldo)"))
        self.campo_nota = QLineEdit()
        fila_nota.addWidget(self.campo_nota, stretch=1)
        layout.addLayout(fila_nota)

        botones = QHBoxLayout()
        boton_abrir = QPushButton("Abrir caja")
        boton_abrir.clicked.connect(self._confirmar)
        botones.addWidget(boton_abrir)
        boton_cancelar = QPushButton("Cancelar")
        boton_cancelar.clicked.connect(self.reject)
        botones.addWidget(boton_cancelar)
        layout.addLayout(botones)

    def _confirmar(self) -> None:
        modificados = [
            (forma_id, Decimal(str(campo.value())))
            for forma_id, (propuesto, campo) in self._campos.items()
            if Decimal(str(campo.value())) != propuesto
        ]
        nota = self.campo_nota.text().strip()
        if modificados and not nota:
            QMessageBox.warning(
                self, "Falta la nota", "Si corregís un saldo inicial, la nota es obligatoria."
            )
            return
        self.modificados = modificados
        self.nota = nota or None
        self.accept()


def abrir_caja_con_dialogo(conexion: sqlite3.Connection, fecha: str, parent: QWidget) -> bool:
    """Abre la caja de ``fecha`` mostrando el diálogo de apertura (propone
    el saldo del último cierre, deja corregirlo con nota). Devuelve si se
    abrió. Reutilizado por Caja diaria y por Cobranzas, que necesita la
    caja abierta para poder cobrar (docs/AJUSTES_V1.1.md, Caja obligatoria
    para cobrar)."""
    dialogo = DialogoAbrirCaja(conexion, fecha, parent)
    if dialogo.exec() != QDialog.Accepted:
        return False

    try:
        abrir_caja(conexion, fecha)
        for forma_pago_id, saldo_real in dialogo.modificados:
            ajustar_saldo_inicial(conexion, f"{fecha} 08:00", forma_pago_id, saldo_real, dialogo.nota)
    except ValueError as error:
        QMessageBox.warning(parent, "No se pudo abrir", str(error))
        return False
    return True


class PaginaCajaDiaria(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self._fecha_hoy = date.today().isoformat()

        layout_general = QVBoxLayout(self)
        pestanas = QTabWidget()
        layout_general.addWidget(pestanas)

        pestanas.addTab(self._armar_pestana_hoy(), "Hoy")
        pestanas.addTab(self._armar_pestana_historial(), "Historial de cierres")

        self.actualizar()

    # --- pestaña Hoy ---

    def _armar_pestana_hoy(self) -> QWidget:
        pagina = QWidget()
        layout = QVBoxLayout(pagina)

        encabezado = QHBoxLayout()
        self._etiqueta_estado = QLabel()
        encabezado.addWidget(self._etiqueta_estado)
        encabezado.addStretch(1)
        self._boton_abrir = QPushButton("Abrir caja de hoy")
        self._boton_abrir.clicked.connect(self._abrir_caja)
        encabezado.addWidget(self._boton_abrir)
        layout.addLayout(encabezado)

        layout.addWidget(QLabel("Movimientos de hoy"))
        self._tabla_movimientos = QTableWidget(0, 6)
        self._tabla_movimientos.setHorizontalHeaderLabels(
            ["Hora", "Tipo", "Forma de pago", "Monto", "Concepto", "Nota"]
        )
        self._tabla_movimientos.verticalHeader().setVisible(False)
        self._tabla_movimientos.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla_movimientos.setMaximumHeight(180)
        layout.addWidget(self._tabla_movimientos)

        operaciones = QHBoxLayout()

        grupo_manual = QGroupBox("Gasto / retiro / aporte")
        form_manual = QFormLayout(grupo_manual)
        self._campo_manual_tipo = QComboBox()
        self._campo_manual_tipo.addItem("Egreso (gasto / retiro)", "egreso")
        self._campo_manual_tipo.addItem("Ingreso (aporte)", "ingreso")
        self._campo_manual_forma = QComboBox()
        self._campo_manual_categoria = QComboBox()
        self._campo_manual_monto = CampoDecimal()
        self._campo_manual_monto.setRange(0, 99_999_999)
        self._campo_manual_monto.setDecimals(2)
        self._campo_manual_concepto = QLineEdit()
        form_manual.addRow("Tipo", self._campo_manual_tipo)
        form_manual.addRow("Forma de pago", self._campo_manual_forma)
        form_manual.addRow("Categoría", self._campo_manual_categoria)
        form_manual.addRow("Monto", self._campo_manual_monto)
        form_manual.addRow("Concepto", self._campo_manual_concepto)
        boton_manual = QPushButton("Registrar movimiento")
        boton_manual.clicked.connect(self._registrar_movimiento_manual)
        form_manual.addRow(boton_manual)
        operaciones.addWidget(grupo_manual)

        grupo_transferencia = QGroupBox("Transferencia interna")
        form_transferencia = QFormLayout(grupo_transferencia)
        self._campo_transf_origen = QComboBox()
        self._campo_transf_destino = QComboBox()
        self._campo_transf_monto = CampoDecimal()
        self._campo_transf_monto.setRange(0, 99_999_999)
        self._campo_transf_monto.setDecimals(2)
        self._campo_transf_concepto = QLineEdit()
        form_transferencia.addRow("Forma de pago origen", self._campo_transf_origen)
        form_transferencia.addRow("Forma de pago destino", self._campo_transf_destino)
        form_transferencia.addRow("Monto", self._campo_transf_monto)
        form_transferencia.addRow("Concepto", self._campo_transf_concepto)
        boton_transferencia = QPushButton("Registrar transferencia")
        boton_transferencia.clicked.connect(self._registrar_transferencia)
        form_transferencia.addRow(boton_transferencia)
        operaciones.addWidget(grupo_transferencia)

        layout.addLayout(operaciones)

        grupo_cierre = QGroupBox("Cierre")
        layout_cierre = QVBoxLayout(grupo_cierre)

        encabezado_cierre = QHBoxLayout()
        for texto, ancho in (("Forma de pago", 160), ("Saldo inicial", 120), ("Saldo teórico", 120), ("Arqueo", 140)):
            etiqueta = QLabel(f"<b>{texto}</b>")
            etiqueta.setFixedWidth(ancho)
            encabezado_cierre.addWidget(etiqueta)
        encabezado_cierre.addStretch(1)
        layout_cierre.addLayout(encabezado_cierre)

        self._filas_cierre_layout = QVBoxLayout()
        layout_cierre.addLayout(self._filas_cierre_layout)

        fila_nota = QHBoxLayout()
        fila_nota.addWidget(QLabel("Nota (obligatoria si hay diferencia)"))
        self._campo_nota_cierre = QLineEdit()
        fila_nota.addWidget(self._campo_nota_cierre, stretch=1)
        layout_cierre.addLayout(fila_nota)
        boton_cerrar = QPushButton("Cerrar caja de hoy")
        boton_cerrar.clicked.connect(self._cerrar_caja)
        layout_cierre.addWidget(boton_cerrar)
        layout.addWidget(grupo_cierre)

        return pagina

    # --- pestaña Historial ---

    def _armar_pestana_historial(self) -> QWidget:
        pagina = QWidget()
        layout = QHBoxLayout(pagina)

        columna_izquierda = QVBoxLayout()
        self._tabla_historial = QTableWidget(0, 3)
        self._tabla_historial.setHorizontalHeaderLabels(["Fecha", "Estado", "Nota"])
        self._tabla_historial.verticalHeader().setVisible(False)
        self._tabla_historial.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla_historial.setSelectionBehavior(QTableWidget.SelectRows)
        self._tabla_historial.itemSelectionChanged.connect(self._mostrar_detalle_historial)
        columna_izquierda.addWidget(self._tabla_historial)
        layout.addLayout(columna_izquierda, stretch=1)

        columna_derecha = QVBoxLayout()
        columna_derecha.addWidget(QLabel("Detalle del cierre seleccionado"))
        self._tabla_detalle_historial = QTableWidget(0, 6)
        self._tabla_detalle_historial.setHorizontalHeaderLabels(
            ["Forma de pago", "Saldo inicial", "Ingresos", "Egresos", "Saldo teórico", "Diferencia"]
        )
        self._tabla_detalle_historial.verticalHeader().setVisible(False)
        self._tabla_detalle_historial.setEditTriggers(QTableWidget.NoEditTriggers)
        columna_derecha.addWidget(self._tabla_detalle_historial)
        layout.addLayout(columna_derecha, stretch=2)

        return pagina

    # --- carga de datos ---

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar (docs/AJUSTES_V1.1.md, etapa 1)

    def actualizar(self) -> None:
        cerrar_cajas_vencidas(self.conexion, self._fecha_hoy)
        self._cargar_combos_formas_pago()
        self._cargar_categorias()
        self._actualizar_estado_caja()
        self._cargar_movimientos_de_hoy()
        self._cargar_vista_previa_cierre()
        self._cargar_historial()

    def _cargar_combos_formas_pago(self) -> None:
        formas = datos_formas_pago.listar_formas_pago(self.conexion)
        for combo in (self._campo_manual_forma, self._campo_transf_origen, self._campo_transf_destino):
            combo.clear()
            for forma in formas:
                combo.addItem(forma["nombre"], forma["id"])

    def _cargar_categorias(self) -> None:
        self._campo_manual_categoria.clear()
        self._campo_manual_categoria.addItem("(sin categoría)", None)
        for categoria in datos_categorias.listar_categorias(self.conexion):
            self._campo_manual_categoria.addItem(categoria["nombre"], categoria["id"])

    def _cierre_de_hoy(self):
        return datos_cierres.obtener_cierre_por_fecha(self.conexion, self._fecha_hoy)

    def _actualizar_estado_caja(self) -> None:
        cierre = self._cierre_de_hoy()
        if cierre is None:
            self._etiqueta_estado.setText(f"Caja del {formato_fecha(self._fecha_hoy)}: sin abrir")
            self._boton_abrir.setEnabled(True)
        elif cierre["estado"] == "abierto":
            self._etiqueta_estado.setText(f"Caja del {formato_fecha(self._fecha_hoy)}: abierta")
            self._boton_abrir.setEnabled(False)
        else:
            self._etiqueta_estado.setText(f"Caja del {formato_fecha(self._fecha_hoy)}: cerrada")
            self._boton_abrir.setEnabled(False)

    def _cargar_movimientos_de_hoy(self) -> None:
        movimientos = datos_caja.listar_movimientos_del_dia(self.conexion, self._fecha_hoy)
        self._tabla_movimientos.setRowCount(len(movimientos))
        for fila, movimiento in enumerate(movimientos):
            forma = self.conexion.execute(
                "SELECT nombre FROM formas_pago WHERE id = ?", (movimiento["forma_pago_id"],)
            ).fetchone()["nombre"]
            self._tabla_movimientos.setItem(fila, 0, QTableWidgetItem(movimiento["fecha_hora"]))
            self._tabla_movimientos.setItem(fila, 1, QTableWidgetItem(movimiento["tipo"]))
            self._tabla_movimientos.setItem(fila, 2, QTableWidgetItem(forma))
            self._tabla_movimientos.setItem(fila, 3, QTableWidgetItem(formato_moneda(movimiento["monto"])))
            self._tabla_movimientos.setItem(fila, 4, QTableWidgetItem(movimiento["concepto"] or ""))
            self._tabla_movimientos.setItem(fila, 5, QTableWidgetItem(movimiento["nota"] or ""))
        ajustar_columnas(self._tabla_movimientos)

    def _limpiar_filas_cierre(self) -> None:
        while self._filas_cierre_layout.count():
            item = self._filas_cierre_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _cargar_vista_previa_cierre(self) -> None:
        self._limpiar_filas_cierre()
        filas = vista_previa_cierre(self.conexion, self._fecha_hoy)
        self._campos_arqueo: dict[int, QDoubleSpinBox] = {}
        for dato in filas:
            forma = self.conexion.execute(
                "SELECT nombre FROM formas_pago WHERE id = ?", (dato.forma_pago_id,)
            ).fetchone()["nombre"]

            fila_widget = QWidget()
            fila_layout = QHBoxLayout(fila_widget)
            fila_layout.setContentsMargins(0, 0, 0, 0)

            etiqueta_forma = QLabel(forma)
            etiqueta_forma.setFixedWidth(160)
            fila_layout.addWidget(etiqueta_forma)

            etiqueta_inicial = QLabel(formato_moneda(dato.saldo_inicial))
            etiqueta_inicial.setFixedWidth(120)
            fila_layout.addWidget(etiqueta_inicial)

            etiqueta_teorico = QLabel(formato_moneda(dato.saldo_teorico))
            etiqueta_teorico.setFixedWidth(120)
            fila_layout.addWidget(etiqueta_teorico)

            campo_arqueo = CampoDecimal()
            campo_arqueo.setFixedWidth(140)
            campo_arqueo.setRange(0, 99_999_999)
            campo_arqueo.setDecimals(2)
            campo_arqueo.setValue(float(dato.saldo_teorico))
            fila_layout.addWidget(campo_arqueo)
            fila_layout.addStretch(1)

            self._filas_cierre_layout.addWidget(fila_widget)
            self._campos_arqueo[dato.forma_pago_id] = campo_arqueo

    def _cargar_historial(self) -> None:
        cierres = datos_cierres.listar_cierres(self.conexion)
        self._tabla_historial.setRowCount(len(cierres))
        for fila, cierre in enumerate(cierres):
            self._tabla_historial.setItem(fila, 0, QTableWidgetItem(formato_fecha(cierre["fecha"])))
            self._tabla_historial.setItem(
                fila, 1, QTableWidgetItem(ETIQUETAS_ESTADO_CIERRE.get(cierre["estado"], cierre["estado"]))
            )
            self._tabla_historial.setItem(fila, 2, QTableWidgetItem(cierre["nota"] or ""))
            self._tabla_historial.item(fila, 0).setData(Qt.UserRole, cierre["id"])
        ajustar_columnas(self._tabla_historial)

    def _mostrar_detalle_historial(self) -> None:
        filas = self._tabla_historial.selectionModel().selectedRows()
        self._tabla_detalle_historial.setRowCount(0)
        if not filas:
            return
        cierre_id = self._tabla_historial.item(filas[0].row(), 0).data(Qt.UserRole)
        detalle = datos_cierres.listar_detalle_de_cierre(self.conexion, cierre_id)
        self._tabla_detalle_historial.setRowCount(len(detalle))
        for fila, dato in enumerate(detalle):
            forma = self.conexion.execute(
                "SELECT nombre FROM formas_pago WHERE id = ?", (dato["forma_pago_id"],)
            ).fetchone()["nombre"]
            self._tabla_detalle_historial.setItem(fila, 0, QTableWidgetItem(forma))
            self._tabla_detalle_historial.setItem(fila, 1, QTableWidgetItem(formato_moneda(dato["saldo_inicial"])))
            self._tabla_detalle_historial.setItem(fila, 2, QTableWidgetItem(formato_moneda(dato["ingresos"])))
            self._tabla_detalle_historial.setItem(fila, 3, QTableWidgetItem(formato_moneda(dato["egresos"])))
            self._tabla_detalle_historial.setItem(fila, 4, QTableWidgetItem(formato_moneda(dato["saldo_teorico"])))
            self._tabla_detalle_historial.setItem(fila, 5, QTableWidgetItem(formato_moneda(dato["diferencia"])))
        ajustar_columnas(self._tabla_detalle_historial)

    # --- acciones ---

    def _abrir_caja(self) -> None:
        if abrir_caja_con_dialogo(self.conexion, self._fecha_hoy, self):
            self.actualizar()

    def _registrar_movimiento_manual(self) -> None:
        monto = Decimal(str(self._campo_manual_monto.value()))
        if monto <= 0:
            QMessageBox.warning(self, "Monto en cero", "El monto tiene que ser mayor a cero.")
            return
        registrar_movimiento_manual(
            self.conexion,
            f"{self._fecha_hoy} 12:00",
            self._campo_manual_tipo.currentData(),
            self._campo_manual_forma.currentData(),
            monto,
            categoria_id=self._campo_manual_categoria.currentData(),
            concepto=self._campo_manual_concepto.text().strip() or None,
        )
        self._campo_manual_monto.setValue(0)
        self._campo_manual_concepto.clear()
        self._cargar_movimientos_de_hoy()
        self._cargar_vista_previa_cierre()

    def _registrar_transferencia(self) -> None:
        monto = Decimal(str(self._campo_transf_monto.value()))
        if monto <= 0:
            QMessageBox.warning(self, "Monto en cero", "El monto tiene que ser mayor a cero.")
            return
        if self._campo_transf_origen.currentData() == self._campo_transf_destino.currentData():
            QMessageBox.warning(self, "Formas iguales", "Origen y destino tienen que ser distintos.")
            return
        registrar_transferencia_interna(
            self.conexion,
            f"{self._fecha_hoy} 12:00",
            self._campo_transf_origen.currentData(),
            self._campo_transf_destino.currentData(),
            monto,
            concepto=self._campo_transf_concepto.text().strip() or None,
        )
        self._campo_transf_monto.setValue(0)
        self._campo_transf_concepto.clear()
        self._cargar_movimientos_de_hoy()
        self._cargar_vista_previa_cierre()

    def _cerrar_caja(self) -> None:
        cierre = self._cierre_de_hoy()
        if cierre is None or cierre["estado"] != "abierto":
            QMessageBox.warning(self, "No hay caja abierta", "Abrí la caja de hoy antes de cerrarla.")
            return

        arqueos = {
            forma_pago_id: Decimal(str(campo.value()))
            for forma_pago_id, campo in self._campos_arqueo.items()
        }
        try:
            cerrar_caja(
                self.conexion, cierre["id"], arqueos, self._campo_nota_cierre.text().strip() or None
            )
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo cerrar", str(error))
            return

        self._campo_nota_cierre.clear()
        self.actualizar()
