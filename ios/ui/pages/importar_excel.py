"""Pantalla Importar desde Excel: vista previa (altas, remitos y pagos a
importar), resolución de conflictos uno por uno (con una acción sugerida
por defecto) y resumen final, exportable a Excel
(docs/PLAN.md, "Importación opcional desde Excel"; docs/AJUSTES_V1.1.md,
etapa 7)."""

from __future__ import annotations

import sqlite3
from datetime import date

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
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

from ios.reports.importacion_excel import TIPOS_CONFLICTO_ETIQUETAS, generar_excel_resumen_conflictos
from ios.services.importacion_excel import (
    Conflicto,
    VistaPreviaImportacion,
    confirmar_importacion,
    leer_archivo,
)
from ios.ui.widgets import ajustar_columnas

SIN_ASIGNAR = "(cliente propio)"
TODOS_LOS_TIPOS = "Todos los tipos"


class _DialogoResumenConflictos(QDialog):
    def __init__(
        self, conflictos: list[Conflicto], decisiones: dict[str, str], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resumen de conflictos resueltos")
        self.setMinimumWidth(640)
        self._conflictos = conflictos
        self._decisiones = decisiones

        layout = QVBoxLayout(self)

        tabla = QTableWidget(len(conflictos), 4)
        tabla.setHorizontalHeaderLabels(["Tipo", "Hoja", "Descripción", "Decisión aplicada"])
        tabla.verticalHeader().setVisible(False)
        tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        for fila, conflicto in enumerate(conflictos):
            tabla.setItem(fila, 0, QTableWidgetItem(
                TIPOS_CONFLICTO_ETIQUETAS.get(conflicto.tipo, conflicto.tipo)
            ))
            tabla.setItem(fila, 1, QTableWidgetItem(conflicto.hoja))
            tabla.setItem(fila, 2, QTableWidgetItem(conflicto.descripcion))
            tabla.setItem(fila, 3, QTableWidgetItem(decisiones.get(conflicto.id, conflicto.sugerida)))
        ajustar_columnas(tabla)
        layout.addWidget(tabla)

        botones = QHBoxLayout()
        botones.addStretch(1)
        boton_excel = QPushButton("Exportar a Excel")
        boton_excel.clicked.connect(self._exportar_excel)
        botones.addWidget(boton_excel)
        boton_cerrar = QPushButton("Cerrar")
        boton_cerrar.clicked.connect(self.accept)
        botones.addWidget(boton_cerrar)
        layout.addLayout(botones)

    def _exportar_excel(self) -> None:
        ruta, _ = QFileDialog.getSaveFileName(
            self, "Exportar resumen de conflictos", "Resumen de importación.xlsx", "Excel (*.xlsx)"
        )
        if not ruta:
            return
        generar_excel_resumen_conflictos(self._conflictos, self._decisiones, ruta)
        QMessageBox.information(self, "Listo", "Se exportó el resumen.")


class PaginaImportarExcel(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion
        self._vista_previa: VistaPreviaImportacion | None = None
        self._combos_sucursal: dict[str, QComboBox] = {}
        self._combos_conflicto: dict[str, QComboBox] = {}
        self._decisiones: dict[str, str] = {}

        layout_general = QVBoxLayout(self)

        fila_archivo = QHBoxLayout()
        self._campo_ruta = QLineEdit()
        self._campo_ruta.setReadOnly(True)
        self._campo_ruta.setPlaceholderText("Ningún archivo elegido")
        boton_elegir = QPushButton("Elegir archivo...")
        boton_elegir.clicked.connect(self._elegir_archivo)
        fila_archivo.addWidget(QLabel("Archivo"))
        fila_archivo.addWidget(self._campo_ruta, stretch=1)
        fila_archivo.addWidget(boton_elegir)
        fila_archivo.addWidget(QLabel("Mes (AAAA-MM)"))
        self._campo_mes = QLineEdit(date.today().strftime("%Y-%m"))
        self._campo_mes.setFixedWidth(100)
        fila_archivo.addWidget(self._campo_mes)
        boton_leer = QPushButton("Leer archivo")
        boton_leer.clicked.connect(self._leer_archivo)
        fila_archivo.addWidget(boton_leer)
        layout_general.addLayout(fila_archivo)

        layout_general.addWidget(QLabel("Hojas detectadas"))
        self._tabla_hojas = QTableWidget(0, 5)
        self._tabla_hojas.setHorizontalHeaderLabels(
            ["Hoja", "Cliente", "Remitos", "Recibos", "Es sucursal de"]
        )
        self._tabla_hojas.verticalHeader().setVisible(False)
        self._tabla_hojas.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla_hojas.setMaximumHeight(160)
        layout_general.addWidget(self._tabla_hojas)

        fila_conflictos = QHBoxLayout()
        fila_conflictos.addWidget(QLabel("Conflictos a resolver"))
        fila_conflictos.addStretch(1)
        fila_conflictos.addWidget(QLabel("Tipo"))
        self._campo_filtro_tipo = QComboBox()
        self._campo_filtro_tipo.currentIndexChanged.connect(self._filtrar_conflictos)
        fila_conflictos.addWidget(self._campo_filtro_tipo)
        boton_aplicar_sugerida = QPushButton("Aplicar la sugerida a todos los de este tipo")
        boton_aplicar_sugerida.clicked.connect(self._aplicar_sugerida_al_filtro)
        fila_conflictos.addWidget(boton_aplicar_sugerida)
        layout_general.addLayout(fila_conflictos)

        self._tabla_conflictos = QTableWidget(0, 5)
        self._tabla_conflictos.setHorizontalHeaderLabels(["Tipo", "Hoja", "Fila", "Descripción", "Acción"])
        self._tabla_conflictos.verticalHeader().setVisible(False)
        self._tabla_conflictos.setEditTriggers(QTableWidget.NoEditTriggers)
        layout_general.addWidget(self._tabla_conflictos, stretch=1)

        layout_general.addWidget(QLabel("Avisos (no requieren decisión)"))
        self._tabla_anomalias = QTableWidget(0, 3)
        self._tabla_anomalias.setHorizontalHeaderLabels(["Tipo", "Hoja", "Descripción"])
        self._tabla_anomalias.verticalHeader().setVisible(False)
        self._tabla_anomalias.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla_anomalias.setMaximumHeight(140)
        layout_general.addWidget(self._tabla_anomalias)

        self._boton_confirmar = QPushButton("Confirmar importación")
        self._boton_confirmar.setEnabled(False)
        self._boton_confirmar.clicked.connect(self._confirmar)
        layout_general.addWidget(self._boton_confirmar)

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar (docs/AJUSTES_V1.1.md, etapa 1)

    def actualizar(self) -> None:
        pass  # la importación se dispara a pedido, no hay nada que refrescar al navegar

    def _elegir_archivo(self) -> None:
        ruta, _ = QFileDialog.getOpenFileName(self, "Elegir planilla", "", "Excel (*.xlsx)")
        if ruta:
            self._campo_ruta.setText(ruta)

    def _leer_archivo(self) -> None:
        ruta = self._campo_ruta.text().strip()
        if not ruta:
            QMessageBox.warning(self, "Falta el archivo", "Elegí un archivo .xlsx primero.")
            return
        mes = self._campo_mes.text().strip()
        if len(mes) != 7 or mes[4] != "-":
            QMessageBox.warning(self, "Mes inválido", "El mes tiene que tener el formato AAAA-MM.")
            return

        try:
            self._vista_previa = leer_archivo(ruta, mes)
        except Exception as error:  # noqa: BLE001 - cualquier error de lectura se muestra tal cual
            QMessageBox.critical(self, "No se pudo leer el archivo", str(error))
            return

        self._mostrar_vista_previa()
        self._boton_confirmar.setEnabled(bool(self._vista_previa.hojas))

    def _mostrar_vista_previa(self) -> None:
        vista = self._vista_previa
        nombres_hojas = [hoja.hoja for hoja in vista.hojas]

        self._tabla_hojas.setRowCount(len(vista.hojas))
        self._combos_sucursal.clear()
        for fila, hoja in enumerate(vista.hojas):
            self._tabla_hojas.setItem(fila, 0, QTableWidgetItem(hoja.hoja))
            self._tabla_hojas.setItem(fila, 1, QTableWidgetItem(hoja.nombre_cliente))
            self._tabla_hojas.setItem(fila, 2, QTableWidgetItem(str(len(hoja.remitos))))
            self._tabla_hojas.setItem(fila, 3, QTableWidgetItem(str(len(hoja.recibos))))

            combo = QComboBox()
            combo.addItem(SIN_ASIGNAR)
            for otra in nombres_hojas:
                if otra != hoja.hoja:
                    combo.addItem(otra)
            self._tabla_hojas.setCellWidget(fila, 4, combo)
            self._combos_sucursal[hoja.hoja] = combo
        ajustar_columnas(self._tabla_hojas)

        self._decisiones = {c.id: c.sugerida for c in vista.conflictos}
        self._cargar_filtro_tipo()
        self._filtrar_conflictos()

        self._tabla_anomalias.setRowCount(len(vista.anomalias))
        for fila, anomalia in enumerate(vista.anomalias):
            self._tabla_anomalias.setItem(fila, 0, QTableWidgetItem(anomalia.tipo))
            self._tabla_anomalias.setItem(fila, 1, QTableWidgetItem(anomalia.hoja))
            self._tabla_anomalias.setItem(fila, 2, QTableWidgetItem(anomalia.descripcion))
        ajustar_columnas(self._tabla_anomalias)

    # --- conflictos ---

    def _cargar_filtro_tipo(self) -> None:
        tipos = sorted({c.tipo for c in self._vista_previa.conflictos})
        self._campo_filtro_tipo.blockSignals(True)
        self._campo_filtro_tipo.clear()
        self._campo_filtro_tipo.addItem(TODOS_LOS_TIPOS, None)
        for tipo in tipos:
            self._campo_filtro_tipo.addItem(TIPOS_CONFLICTO_ETIQUETAS.get(tipo, tipo), tipo)
        self._campo_filtro_tipo.blockSignals(False)

    def _filtrar_conflictos(self) -> None:
        tipo_filtro = self._campo_filtro_tipo.currentData()
        conflictos = [
            c for c in self._vista_previa.conflictos
            if tipo_filtro is None or c.tipo == tipo_filtro
        ]

        self._tabla_conflictos.setRowCount(len(conflictos))
        self._combos_conflicto.clear()
        for fila, conflicto in enumerate(conflictos):
            self._tabla_conflictos.setItem(
                fila, 0, QTableWidgetItem(TIPOS_CONFLICTO_ETIQUETAS.get(conflicto.tipo, conflicto.tipo))
            )
            self._tabla_conflictos.setItem(fila, 1, QTableWidgetItem(conflicto.hoja))
            self._tabla_conflictos.setItem(
                fila, 2, QTableWidgetItem(str(conflicto.fila) if conflicto.fila else "-")
            )
            self._tabla_conflictos.setItem(fila, 3, QTableWidgetItem(conflicto.descripcion))

            combo = QComboBox()
            combo.addItems(conflicto.opciones)
            combo.setCurrentText(self._decisiones.get(conflicto.id, conflicto.sugerida))
            combo.currentTextChanged.connect(
                lambda texto, id_=conflicto.id: self._decisiones.__setitem__(id_, texto)
            )
            self._tabla_conflictos.setCellWidget(fila, 4, combo)
            self._combos_conflicto[conflicto.id] = combo
        ajustar_columnas(self._tabla_conflictos)

    def _aplicar_sugerida_al_filtro(self) -> None:
        if self._vista_previa is None:
            return
        tipo_filtro = self._campo_filtro_tipo.currentData()
        for conflicto in self._vista_previa.conflictos:
            if tipo_filtro is not None and conflicto.tipo != tipo_filtro:
                continue
            self._decisiones[conflicto.id] = conflicto.sugerida
            combo = self._combos_conflicto.get(conflicto.id)
            if combo is not None:
                combo.setCurrentText(conflicto.sugerida)

    def _decisiones_actuales(self) -> dict[str, str]:
        return dict(self._decisiones)

    # --- confirmar ---

    def _confirmar(self) -> None:
        if self._vista_previa is None:
            return

        asignaciones = {
            hoja: combo.currentText()
            for hoja, combo in self._combos_sucursal.items()
            if combo.currentText() != SIN_ASIGNAR
        }
        decisiones = self._decisiones_actuales()

        try:
            resultado = confirmar_importacion(self.conexion, self._vista_previa, asignaciones, decisiones)
        except Exception as error:  # noqa: BLE001 - se muestra el motivo real del fallo
            QMessageBox.critical(self, "No se pudo importar", str(error))
            return

        QMessageBox.information(
            self, "Importación completa",
            f"Se crearon {resultado['clientes_creados']} clientes, "
            f"{resultado['comprobantes_creados']} comprobantes y "
            f"{resultado['recibos_creados']} recibos.",
        )

        if self._vista_previa.conflictos:
            _DialogoResumenConflictos(self._vista_previa.conflictos, decisiones, self).exec()

        self._vista_previa = None
        self._boton_confirmar.setEnabled(False)
        self._tabla_hojas.setRowCount(0)
        self._tabla_conflictos.setRowCount(0)
        self._tabla_anomalias.setRowCount(0)
        self._combos_sucursal.clear()
        self._combos_conflicto.clear()
        self._decisiones.clear()
        self._campo_filtro_tipo.clear()
