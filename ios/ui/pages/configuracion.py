"""Pantalla Configuración: IVA, comisión, tipos de comprobante, formas de
pago, categorías de caja y número inicial de recibo (docs/PLAN.md,
"Pantallas")."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ios.data import categorias_caja as datos_categorias
from ios.data import formas_pago as datos_formas_pago
from ios.data import tipos_comprobante as datos_tipos
from ios.data.db import conectar, ruta_base_de_datos
from ios.services.categorias_caja import alta_categoria
from ios.services.configuracion import actualizar_configuracion, obtener_configuracion
from ios.services.formas_pago import alta_forma_pago
from ios.services.mantenimiento import PALABRA_CONFIRMACION, reiniciar_base_de_datos
from ios.services.tipos_comprobante import alta_tipo_comprobante
from ios.ui.widgets import ajustar_columnas


class PaginaConfiguracion(QWidget):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion

        layout_general = QVBoxLayout(self)
        pestanas = QTabWidget()
        layout_general.addWidget(pestanas)

        pestanas.addTab(self._armar_pestana_general(), "General")
        pestanas.addTab(self._armar_pestana_simple(
            "tipos_comprobante", "Tipo", "Abreviatura", self._guardar_tipo_comprobante,
        ), "Tipos de comprobante")
        pestanas.addTab(self._armar_pestana_formas_pago(), "Formas de pago")
        pestanas.addTab(self._armar_pestana_categorias(), "Categorías de caja")
        pestanas.addTab(self._armar_pestana_mantenimiento(), "Mantenimiento")

        self.actualizar()

    # --- General ---

    def _armar_pestana_general(self) -> QWidget:
        pagina = QWidget()
        grupo = QGroupBox("Parámetros generales")
        formulario = QFormLayout(grupo)

        self._campo_iva = QDoubleSpinBox()
        self._campo_iva.setRange(0, 100)
        self._campo_iva.setDecimals(2)
        self._campo_iva.setSuffix(" %")

        self._campo_comision = QDoubleSpinBox()
        self._campo_comision.setRange(0, 100)
        self._campo_comision.setDecimals(2)
        self._campo_comision.setSuffix(" %")

        self._campo_numero_inicial = QSpinBox()
        self._campo_numero_inicial.setRange(1, 999_999_999)

        self._campo_redondeo = QSpinBox()
        self._campo_redondeo.setRange(0, 6)

        formulario.addRow("IVA", self._campo_iva)
        formulario.addRow("Comisión", self._campo_comision)
        formulario.addRow("Número inicial de recibo", self._campo_numero_inicial)
        formulario.addRow("Redondeo (decimales)", self._campo_redondeo)

        boton_guardar = QPushButton("Guardar")
        boton_guardar.clicked.connect(self._guardar_general)
        formulario.addRow(boton_guardar)

        layout = QVBoxLayout(pagina)
        layout.addWidget(grupo)
        layout.addStretch(1)
        return pagina

    def _cargar_general(self) -> None:
        config = obtener_configuracion(self.conexion)
        self._campo_iva.setValue(float(config["iva_pct"]))
        self._campo_comision.setValue(float(config["comision_pct"]))
        self._campo_numero_inicial.setValue(config["numero_inicial_recibo"])
        self._campo_redondeo.setValue(config["redondeo_decimales"])

    def _guardar_general(self) -> None:
        try:
            actualizar_configuracion(
                self.conexion,
                iva_pct=Decimal(str(self._campo_iva.value())),
                comision_pct=Decimal(str(self._campo_comision.value())),
                numero_inicial_recibo=self._campo_numero_inicial.value(),
                redondeo_decimales=self._campo_redondeo.value(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return
        QMessageBox.information(self, "Listo", "Se guardó la configuración.")

    # --- listas simples (tipos de comprobante) ---

    def _armar_pestana_simple(self, clave: str, etiqueta_nombre: str, etiqueta_codigo: str, accion_guardar) -> QWidget:
        pagina = QWidget()
        layout = QHBoxLayout(pagina)

        tabla = QTableWidget(0, 2)
        tabla.setHorizontalHeaderLabels([etiqueta_nombre, etiqueta_codigo])
        tabla.verticalHeader().setVisible(False)
        tabla.setEditTriggers(QTableWidget.NoEditTriggers)
        setattr(self, f"_tabla_{clave}", tabla)
        layout.addWidget(tabla, stretch=2)

        grupo = QGroupBox(f"Nuevo {etiqueta_nombre.lower()}")
        formulario = QFormLayout(grupo)
        campo_nombre = QLineEdit()
        campo_codigo = QLineEdit()
        setattr(self, f"_campo_{clave}_nombre", campo_nombre)
        setattr(self, f"_campo_{clave}_codigo", campo_codigo)
        formulario.addRow(etiqueta_nombre, campo_nombre)
        formulario.addRow(etiqueta_codigo, campo_codigo)
        boton = QPushButton("Guardar")
        boton.clicked.connect(accion_guardar)
        formulario.addRow(boton)

        columna_derecha = QVBoxLayout()
        columna_derecha.addWidget(grupo)
        columna_derecha.addStretch(1)
        layout.addLayout(columna_derecha, stretch=1)

        return pagina

    def _cargar_tipos_comprobante(self) -> None:
        tipos = datos_tipos.listar_tipos_comprobante(self.conexion, incluir_inactivos=True)
        self._tabla_tipos_comprobante.setRowCount(len(tipos))
        for fila, tipo in enumerate(tipos):
            self._tabla_tipos_comprobante.setItem(fila, 0, QTableWidgetItem(tipo["nombre"]))
            self._tabla_tipos_comprobante.setItem(fila, 1, QTableWidgetItem(tipo["abreviatura"]))
        ajustar_columnas(self._tabla_tipos_comprobante)

    def _guardar_tipo_comprobante(self) -> None:
        nombre = self._campo_tipos_comprobante_nombre.text().strip()
        abreviatura = self._campo_tipos_comprobante_codigo.text().strip()
        try:
            alta_tipo_comprobante(self.conexion, nombre, abreviatura)
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return
        self._campo_tipos_comprobante_nombre.clear()
        self._campo_tipos_comprobante_codigo.clear()
        self._cargar_tipos_comprobante()

    # --- Formas de pago ---

    def _armar_pestana_formas_pago(self) -> QWidget:
        pagina = QWidget()
        layout = QHBoxLayout(pagina)

        self._tabla_formas_pago = QTableWidget(0, 2)
        self._tabla_formas_pago.setHorizontalHeaderLabels(["Nombre", "Tipo"])
        self._tabla_formas_pago.verticalHeader().setVisible(False)
        self._tabla_formas_pago.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self._tabla_formas_pago, stretch=2)

        grupo = QGroupBox("Nueva forma de pago")
        formulario = QFormLayout(grupo)
        self._campo_forma_pago_nombre = QLineEdit()
        self._campo_forma_pago_tipo = QComboBox()
        self._campo_forma_pago_tipo.addItem("Efectivo", "efectivo")
        self._campo_forma_pago_tipo.addItem("Banco", "banco")
        self._campo_forma_pago_tipo.addItem("Cheque", "cheque")
        self._campo_forma_pago_tipo.addItem("Otro", "otro")
        formulario.addRow("Nombre", self._campo_forma_pago_nombre)
        formulario.addRow("Tipo", self._campo_forma_pago_tipo)
        boton = QPushButton("Guardar")
        boton.clicked.connect(self._guardar_forma_pago)
        formulario.addRow(boton)

        columna_derecha = QVBoxLayout()
        columna_derecha.addWidget(grupo)
        columna_derecha.addStretch(1)
        layout.addLayout(columna_derecha, stretch=1)

        return pagina

    def _cargar_formas_pago(self) -> None:
        formas = datos_formas_pago.listar_formas_pago(self.conexion, incluir_inactivas=True)
        self._tabla_formas_pago.setRowCount(len(formas))
        for fila, forma in enumerate(formas):
            self._tabla_formas_pago.setItem(fila, 0, QTableWidgetItem(forma["nombre"]))
            self._tabla_formas_pago.setItem(fila, 1, QTableWidgetItem(forma["tipo"]))
        ajustar_columnas(self._tabla_formas_pago)

    def _guardar_forma_pago(self) -> None:
        nombre = self._campo_forma_pago_nombre.text().strip()
        try:
            alta_forma_pago(self.conexion, nombre, self._campo_forma_pago_tipo.currentData())
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return
        self._campo_forma_pago_nombre.clear()
        self._cargar_formas_pago()

    # --- Categorías de caja ---

    def _armar_pestana_categorias(self) -> QWidget:
        pagina = QWidget()
        layout = QHBoxLayout(pagina)

        self._tabla_categorias = QTableWidget(0, 2)
        self._tabla_categorias.setHorizontalHeaderLabels(["Nombre", "Tipo"])
        self._tabla_categorias.verticalHeader().setVisible(False)
        self._tabla_categorias.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self._tabla_categorias, stretch=2)

        grupo = QGroupBox("Nueva categoría")
        formulario = QFormLayout(grupo)
        self._campo_categoria_nombre = QLineEdit()
        self._campo_categoria_tipo = QComboBox()
        self._campo_categoria_tipo.addItem("Ingreso", "ingreso")
        self._campo_categoria_tipo.addItem("Egreso", "egreso")
        formulario.addRow("Nombre", self._campo_categoria_nombre)
        formulario.addRow("Tipo", self._campo_categoria_tipo)
        boton = QPushButton("Guardar")
        boton.clicked.connect(self._guardar_categoria)
        formulario.addRow(boton)

        columna_derecha = QVBoxLayout()
        columna_derecha.addWidget(grupo)
        columna_derecha.addStretch(1)
        layout.addLayout(columna_derecha, stretch=1)

        return pagina

    def _cargar_categorias(self) -> None:
        categorias = datos_categorias.listar_categorias(self.conexion, incluir_inactivas=True)
        self._tabla_categorias.setRowCount(len(categorias))
        for fila, categoria in enumerate(categorias):
            self._tabla_categorias.setItem(fila, 0, QTableWidgetItem(categoria["nombre"]))
            self._tabla_categorias.setItem(fila, 1, QTableWidgetItem(categoria["tipo"]))
        ajustar_columnas(self._tabla_categorias)

    def _guardar_categoria(self) -> None:
        nombre = self._campo_categoria_nombre.text().strip()
        try:
            alta_categoria(self.conexion, nombre, self._campo_categoria_tipo.currentData())
        except ValueError as error:
            QMessageBox.warning(self, "No se pudo guardar", str(error))
            return
        self._campo_categoria_nombre.clear()
        self._cargar_categorias()

    # --- Mantenimiento: instalación limpia (docs/AJUSTES_V1.1.md) ---

    def _armar_pestana_mantenimiento(self) -> QWidget:
        pagina = QWidget()
        grupo = QGroupBox("Instalación limpia")
        layout_grupo = QVBoxLayout(grupo)
        layout_grupo.addWidget(QLabel(
            "Reinicia la base de datos a cero: clientes, remitos, cobros, compras y caja.\n"
            "La base actual queda guardada como respaldo en la misma carpeta, por si hace "
            "falta volver atrás. La aplicación se cierra para poder hacerlo; al volver a "
            "abrirla, arranca con la base vacía."
        ))
        boton = QPushButton("Reiniciar base de datos…")
        boton.clicked.connect(self._reiniciar_base_de_datos)
        layout_grupo.addWidget(boton)

        layout = QVBoxLayout(pagina)
        layout.addWidget(grupo)
        layout.addStretch(1)
        return pagina

    def _reiniciar_base_de_datos(self) -> None:
        respuesta = QMessageBox.warning(
            self, "Reiniciar base de datos",
            "Esto va a borrar TODOS los datos actuales (clientes, remitos, cobros, caja). "
            "Se guarda un respaldo antes, pero la aplicación se va a cerrar. ¿Querés continuar?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if respuesta != QMessageBox.Yes:
            return

        palabra, confirmado = QInputDialog.getText(
            self, "Confirmar", f'Para confirmar, escribí la palabra "{PALABRA_CONFIRMACION}":'
        )
        if not confirmado:
            return
        if palabra.strip() != PALABRA_CONFIRMACION:
            QMessageBox.warning(
                self, "Palabra incorrecta",
                f'Tenés que escribir exactamente "{PALABRA_CONFIRMACION}". No se borró nada.',
            )
            return

        ruta_actual = ruta_base_de_datos()
        self.conexion.close()
        try:
            respaldo = reiniciar_base_de_datos(ruta_actual, palabra.strip())
        except ValueError as error:
            self.conexion = conectar(ruta_actual)
            QMessageBox.warning(self, "No se pudo reiniciar", str(error))
            return

        mensaje = (
            "Se reinició la base de datos."
            if respaldo is None
            else f"Se reinició la base de datos. El respaldo anterior quedó en:\n{respaldo}"
        )
        QMessageBox.information(self, "Listo", f"{mensaje}\n\nLa aplicación se va a cerrar.")
        QApplication.instance().quit()

    # --- general ---

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar (docs/AJUSTES_V1.1.md, etapa 1)

    def actualizar(self) -> None:
        self._cargar_general()
        self._cargar_tipos_comprobante()
        self._cargar_formas_pago()
        self._cargar_categorias()
