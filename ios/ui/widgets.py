"""Widgets reutilizables entre pantallas (docs/AJUSTES_V1.1.md, etapa 2)."""

from __future__ import annotations

import sqlite3

from PySide6.QtCore import QStringListModel, Qt, Signal
from PySide6.QtWidgets import (
    QCompleter,
    QDoubleSpinBox,
    QLineEdit,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ios.data import clientes as datos_clientes
from ios.domain.texto import normalizar

__all__ = [
    "normalizar", "BuscadorCliente", "ajustar_columnas", "CampoDecimal", "CampoEntero",
    "CampoGraduacion",
]

ANCHO_MAXIMO_COLUMNA = 320


class CampoDecimal(QDoubleSpinBox):
    """``QDoubleSpinBox`` que selecciona todo su valor al recibir el foco
    (clic o Tab), para poder escribir directo encima sin tener que borrar
    primero el "0,00" precargado — se usa en vez de ``QDoubleSpinBox`` en
    todos los formularios, para agilizar la carga."""

    def focusInEvent(self, evento) -> None:
        super().focusInEvent(evento)
        self.selectAll()


class CampoEntero(QSpinBox):
    """Igual que ``CampoDecimal`` pero para ``QSpinBox`` (campos enteros:
    cantidades, años, números de configuración)."""

    def focusInEvent(self, evento) -> None:
        super().focusInEvent(evento)
        self.selectAll()


class CampoGraduacion(CampoDecimal):
    """``CampoDecimal`` que siempre muestra el signo (``+1.25``/``-0.50``),
    como se anota una graduación oftálmica — un valor positivo sin signo se
    presta a confusión con el cilíndrico, que casi siempre es negativo."""

    def textFromValue(self, valor: float) -> str:
        texto = super().textFromValue(valor)
        if valor > 0 and not texto.startswith("+"):
            texto = f"+{texto}"
        return texto

    def valueFromText(self, texto: str) -> float:
        return super().valueFromText(texto.lstrip("+"))


def ajustar_columnas(tabla: QTableWidget, ancho_maximo: int = ANCHO_MAXIMO_COLUMNA) -> None:
    """Ajusta cada columna al ancho de su contenido, para que se lea bien
    sin importar si es un texto corto o uno largo, sin dejar que una
    columna de texto libre (por ejemplo, una descripción) se coma toda la
    tabla (se la recorta a ``ancho_maximo``). El usuario siempre puede
    agrandar o achicar cualquier columna a mano, arrastrando el borde del
    encabezado: es el modo "Interactive", el que usa Qt por defecto en una
    tabla (docs/AJUSTES_V1.1.md, columnas de tabla ajustables).

    Hay que llamarla después de cargar las filas, cada vez que se vuelve a
    cargar la tabla (si las columnas quedaron con un ancho elegido a mano
    por el usuario, una nueva carga las vuelve a ajustar al contenido)."""
    tabla.resizeColumnsToContents()
    encabezado = tabla.horizontalHeader()
    for columna in range(tabla.columnCount()):
        if encabezado.sectionSize(columna) > ancho_maximo:
            encabezado.resizeSection(columna, ancho_maximo)


class BuscadorCliente(QWidget):
    """Campo con autocompletado que busca por cualquier parte del nombre
    del cliente, sin distinguir mayúsculas ni acentos. Solo clientes
    activos (docs/AJUSTES_V1.1.md, etapa 2.1)."""

    clienteElegido = Signal(int)

    def __init__(self, conexion: sqlite3.Connection, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.conexion = conexion
        self._clientes: list[sqlite3.Row] = []
        self._id_por_nombre: dict[str, int] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.campo = QLineEdit()
        self.campo.setPlaceholderText("Buscar óptica...")
        layout.addWidget(self.campo)

        self._completer = QCompleter([], self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.activated[str].connect(self._al_elegir_texto)
        self.campo.setCompleter(self._completer)
        self.campo.textEdited.connect(self._actualizar_sugerencias)
        self.campo.returnPressed.connect(self._al_presionar_enter)

        self.cargar_clientes()

    def cargar_clientes(self) -> None:
        self._clientes = datos_clientes.listar_clientes(self.conexion)
        self._id_por_nombre = {cliente["nombre"]: cliente["id"] for cliente in self._clientes}

    def limpiar(self) -> None:
        self.campo.clear()

    def _actualizar_sugerencias(self, texto: str) -> None:
        objetivo = normalizar(texto)
        if not objetivo:
            self._completer.setModel(QStringListModel([]))
            return
        coincidencias = [
            cliente["nombre"] for cliente in self._clientes
            if objetivo in normalizar(cliente["nombre"])
        ]
        self._completer.setModel(QStringListModel(coincidencias))
        self._completer.complete()

    def _al_elegir_texto(self, texto: str) -> None:
        cliente_id = self._id_por_nombre.get(texto)
        if cliente_id is not None:
            self.clienteElegido.emit(cliente_id)

    def _al_presionar_enter(self) -> None:
        self._al_elegir_texto(self.campo.text())
