"""Pantalla Inicio: panel directivo de IOS (docs/PLAN.md, "Pantallas" y
"Reportes y dashboard"; rediseño completo en docs/AJUSTES_V1.1.md).

Pensado para entender en segundos la situación comercial y financiera:
ventas y cobranzas del mes con su comparación contra el mes y el año
anterior, deuda total, total disponible, evolución de los últimos 12
meses, deuda por antigüedad y los clientes con más saldo, y tres
indicadores chicos de actividad comercial. Las tarjetas y filas
relevantes llevan a la pantalla correspondiente (se resuelve en
ios/ui/main_window.py, que es quien conoce la navegación entre pantallas).
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLayout,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ios.domain.periodos import Variacion
from ios.reports.formato import formato_moneda
from ios.services.dashboard import (
    actividad_comercial_del_mes,
    comparacion_cobranzas,
    comparacion_ventas,
    deuda_de_lo_vendido_del_mes,
    deuda_total,
    estado_de_caja_del_dia,
    evolucion_ventas_cobranzas_12_meses,
    porcentaje_deuda_mayor_a_30_dias,
    saldos_por_antiguedad,
    top_clientes_por_saldo,
    total_remitos_cobrados_del_mes,
)
from ios.services.resumen_mensual import total_disponible_actual
from ios.ui.graficos import grafico_barras_horizontales, grafico_lineas_multiples
from ios.ui.widgets import ajustar_columnas

COLOR_POSITIVO = "#1a7f37"
COLOR_NEGATIVO = "#c62828"
COLOR_NEUTRO = "#777"

ETIQUETAS_ESTADO_CAJA = {
    (True, False): "Abierta",
    (False, True): "Cerrada",
    (False, False): "Sin abrir",
}

ESTILO_TARJETA = (
    "QFrame#tarjeta { background: #fafafa; border: 1px solid #e0e0e0; border-radius: 6px; }"
)


def _vaciar_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


def _formato_pct(valor: Decimal) -> str:
    texto = f"{valor:.1f}".replace(".", ",")
    return f"{texto}%"


def _texto_variacion(variacion: Variacion) -> tuple[str, str]:
    """Texto y color (verde/rojo/gris) de una variación porcentual, o
    "Sin datos" si el período anterior no tiene información (no hay base
    válida para calcular un porcentaje)."""
    if variacion.porcentaje is None:
        return "Sin datos", COLOR_NEUTRO
    if variacion.monto > 0:
        flecha, color = "↑", COLOR_POSITIVO
    elif variacion.monto < 0:
        flecha, color = "↓", COLOR_NEGATIVO
    else:
        flecha, color = "→", COLOR_NEUTRO
    signo = "+" if variacion.porcentaje >= 0 else ""
    return f"{flecha} {signo}{_formato_pct(variacion.porcentaje)}", color


class _TarjetaClicable(QFrame):
    """Tarjeta con aspecto clickeable (cursor de mano); emite ``clicked``
    al apretarla. El resto de la pantalla decide si la conecta a algo."""

    clicked = Signal()

    def __init__(self, clickable: bool = True) -> None:
        super().__init__()
        self.setObjectName("tarjeta")
        self.setStyleSheet(ESTILO_TARJETA)
        self.setFrameShape(QFrame.StyledPanel)
        if clickable:
            self.setCursor(Qt.PointingHandCursor)
        self._clickable = clickable

    def mousePressEvent(self, evento) -> None:
        if self._clickable:
            self.clicked.emit()
        super().mousePressEvent(evento)


def _tarjeta_principal(titulo: str, clickable: bool = True) -> tuple[_TarjetaClicable, QLabel, QLabel, QLabel]:
    """Tarjeta con título, valor grande y dos líneas de variación (mes
    anterior / interanual), para Ventas y Cobranzas del mes."""
    marco = _TarjetaClicable(clickable)
    layout = QVBoxLayout(marco)
    etiqueta_titulo = QLabel(titulo)
    etiqueta_titulo.setStyleSheet("color: #666; font-size: 11px; font-weight: bold; border: none;")
    etiqueta_valor = QLabel("—")
    etiqueta_valor.setStyleSheet("font-size: 21px; font-weight: bold; border: none;")
    etiqueta_mensual = QLabel("")
    etiqueta_mensual.setStyleSheet(f"font-size: 11px; color: {COLOR_NEUTRO}; border: none;")
    etiqueta_anual = QLabel("")
    etiqueta_anual.setStyleSheet(f"font-size: 11px; color: {COLOR_NEUTRO}; border: none;")
    layout.addWidget(etiqueta_titulo)
    layout.addWidget(etiqueta_valor)
    layout.addWidget(etiqueta_mensual)
    layout.addWidget(etiqueta_anual)
    return marco, etiqueta_valor, etiqueta_mensual, etiqueta_anual


def _tarjeta_simple(titulo: str, clickable: bool = False) -> tuple[_TarjetaClicable, QLabel]:
    """Tarjeta con título y un solo valor (Deuda total, Total disponible,
    y los indicadores chicos de actividad comercial)."""
    marco = _TarjetaClicable(clickable)
    layout = QVBoxLayout(marco)
    etiqueta_titulo = QLabel(titulo)
    etiqueta_titulo.setStyleSheet("color: #666; font-size: 11px; font-weight: bold; border: none;")
    etiqueta_valor = QLabel("—")
    etiqueta_valor.setStyleSheet("font-size: 21px; font-weight: bold; border: none;")
    layout.addWidget(etiqueta_titulo)
    layout.addWidget(etiqueta_valor)
    return marco, etiqueta_valor


def _titulo_bloque(texto: str) -> QLabel:
    etiqueta = QLabel(texto)
    etiqueta.setStyleSheet("font-size: 13px; font-weight: bold; color: #444; margin-top: 6px;")
    return etiqueta


class PaginaInicio(QWidget):
    # Señales de navegación: main_window.py decide a qué pantalla llevan
    # (esta pantalla no conoce ni crea otras pantallas).
    navegarVentas = Signal()
    navegarCobranzas = Signal()
    navegarDeuda = Signal()
    navegarCompras = Signal()
    navegarCuentaCorriente = Signal()

    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion

        layout_raiz = QVBoxLayout(self)
        layout_raiz.setContentsMargins(0, 0, 0, 0)

        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        contenido = QWidget()
        layout_general = QVBoxLayout(contenido)
        area.setWidget(contenido)
        layout_raiz.addWidget(area)

        encabezado = QHBoxLayout()
        titulo = QLabel("Panel directivo")
        titulo.setStyleSheet("font-size: 19px; font-weight: bold;")
        encabezado.addWidget(titulo)
        encabezado.addStretch(1)
        self._etiqueta_actualizado = QLabel("")
        self._etiqueta_actualizado.setStyleSheet("color: #888; font-size: 11px;")
        encabezado.addWidget(self._etiqueta_actualizado)
        boton_actualizar = QPushButton("Actualizar")
        boton_actualizar.clicked.connect(self.actualizar)
        encabezado.addWidget(boton_actualizar)
        layout_general.addLayout(encabezado)

        self._etiqueta_error = QLabel("")
        self._etiqueta_error.setStyleSheet(f"color: {COLOR_NEGATIVO}; font-size: 12px;")
        self._etiqueta_error.setWordWrap(True)
        self._etiqueta_error.setVisible(False)
        layout_general.addWidget(self._etiqueta_error)

        layout_general.addWidget(self._crear_bloque_a())
        layout_general.addWidget(_titulo_bloque("EVOLUCIÓN DE VENTAS Y COBRANZAS"))
        layout_general.addWidget(self._crear_bloque_b())
        layout_general.addWidget(_titulo_bloque("SITUACIÓN DE CUENTAS CORRIENTES"))
        layout_general.addWidget(self._crear_bloque_c())
        layout_general.addWidget(_titulo_bloque("ACTIVIDAD COMERCIAL"))
        layout_general.addWidget(self._crear_bloque_d())

        self.actualizar()

    # ---- Construcción de la pantalla (una sola vez) -----------------

    def _crear_bloque_a(self) -> QWidget:
        contenedor = QWidget()
        grid = QGridLayout(contenedor)

        tarjeta, self._valor_ventas, self._var_ventas_mensual, self._var_ventas_anual = (
            _tarjeta_principal("VENTAS DEL MES")
        )
        tarjeta.setToolTip("Ver comprobantes del período")
        tarjeta.clicked.connect(self.navegarVentas.emit)
        grid.addWidget(tarjeta, 0, 0)

        tarjeta, self._valor_cobranzas, self._var_cobranzas_mensual, self._var_cobranzas_anual = (
            _tarjeta_principal("COBRANZAS DEL MES")
        )
        tarjeta.setToolTip("Ver cobranzas")
        tarjeta.clicked.connect(self.navegarCobranzas.emit)
        self._etiqueta_remitos_cobrados = QLabel("")
        self._etiqueta_remitos_cobrados.setStyleSheet(f"font-size: 11px; color: {COLOR_NEUTRO}; border: none;")
        self._etiqueta_remitos_cobrados.setWordWrap(True)
        self._etiqueta_remitos_cobrados.setToolTip(
            "Cuánto de lo facturado en remitos de este mes ya está cobrado a hoy, sin importar "
            "cuándo se cobró (distinto de \"Cobranzas del mes\", que es por fecha del recibo: un "
            "recibo de este mes puede estar cobrando deuda vieja)."
        )
        tarjeta.layout().addWidget(self._etiqueta_remitos_cobrados)
        grid.addWidget(tarjeta, 0, 1)

        tarjeta, self._valor_deuda = _tarjeta_simple("DEUDA TOTAL", clickable=True)
        tarjeta.setToolTip("Ver deudores")
        tarjeta.clicked.connect(self.navegarDeuda.emit)
        self._etiqueta_deuda_del_mes = QLabel("")
        self._etiqueta_deuda_del_mes.setStyleSheet(f"font-size: 11px; color: {COLOR_NEUTRO}; border: none;")
        self._etiqueta_deuda_del_mes.setWordWrap(True)
        tarjeta.layout().addWidget(self._etiqueta_deuda_del_mes)
        grid.addWidget(tarjeta, 0, 2)

        tarjeta, self._valor_disponible = _tarjeta_simple("TOTAL DISPONIBLE")
        self._etiqueta_caja = QLabel("")
        self._etiqueta_caja.setStyleSheet("color: #666; font-size: 11px; border: none;")
        tarjeta.layout().addWidget(self._etiqueta_caja)
        grid.addWidget(tarjeta, 0, 3)

        for columna in range(4):
            grid.setColumnStretch(columna, 1)
        return contenedor

    def _crear_bloque_b(self) -> QWidget:
        contenedor = QWidget()
        self._layout_grafico_evolucion = QVBoxLayout(contenedor)
        return contenedor

    def _crear_bloque_c(self) -> QWidget:
        contenedor = QWidget()
        layout = QHBoxLayout(contenedor)

        columna_antiguedad = QVBoxLayout()
        columna_antiguedad.addWidget(QLabel("Deuda por antigüedad"))
        self._layout_grafico_antiguedad = QVBoxLayout()
        columna_antiguedad.addLayout(self._layout_grafico_antiguedad)
        self._etiqueta_mas_30 = QLabel("")
        self._etiqueta_mas_30.setStyleSheet("font-size: 12px; color: #444;")
        columna_antiguedad.addWidget(self._etiqueta_mas_30)
        layout.addLayout(columna_antiguedad, stretch=1)

        columna_clientes = QVBoxLayout()
        columna_clientes.addWidget(QLabel("Top 5 clientes con mayor saldo"))
        self._tabla_clientes = QTableWidget(0, 2)
        self._tabla_clientes.setHorizontalHeaderLabels(["Cliente", "Saldo"])
        self._tabla_clientes.verticalHeader().setVisible(False)
        self._tabla_clientes.setEditTriggers(QTableWidget.NoEditTriggers)
        self._tabla_clientes.setSelectionBehavior(QTableWidget.SelectRows)
        self._tabla_clientes.setCursor(Qt.PointingHandCursor)
        self._tabla_clientes.setToolTip("Ver cuenta corriente")
        self._tabla_clientes.cellClicked.connect(lambda *_: self.navegarCuentaCorriente.emit())
        columna_clientes.addWidget(self._tabla_clientes)
        layout.addLayout(columna_clientes, stretch=1)

        return contenedor

    def _crear_bloque_d(self) -> QWidget:
        contenedor = QWidget()
        grid = QGridLayout(contenedor)

        tarjeta, self._valor_compras = _tarjeta_simple("Compras del mes", clickable=True)
        tarjeta.setToolTip("Ver compras y proveedores")
        tarjeta.clicked.connect(self.navegarCompras.emit)
        grid.addWidget(tarjeta, 0, 0)

        tarjeta, self._valor_clientes_activos = _tarjeta_simple("Clientes activos")
        grid.addWidget(tarjeta, 0, 1)

        tarjeta, self._valor_remitos = _tarjeta_simple("Remitos emitidos")
        grid.addWidget(tarjeta, 0, 2)

        for columna in range(3):
            grid.setColumnStretch(columna, 1)
        return contenedor

    # ---- Actualización de datos --------------------------------------

    def reiniciar(self) -> None:
        pass  # sin estado de sesión que limpiar (docs/AJUSTES_V1.1.md, etapa 1)

    def actualizar(self) -> None:
        try:
            self._cargar_datos()
        except Exception as error:
            self._etiqueta_error.setText(f"No se pudieron actualizar los indicadores: {error}")
            self._etiqueta_error.setVisible(True)
            return
        self._etiqueta_error.setVisible(False)
        self._etiqueta_actualizado.setText(f"Actualizado a las {datetime.now().strftime('%H:%M:%S')}")

    def _cargar_datos(self) -> None:
        hoy = date.today()
        mes_actual = hoy.strftime("%Y-%m")

        comparacion_v = comparacion_ventas(self.conexion, hoy)
        self._valor_ventas.setText(formato_moneda(comparacion_v.total_actual))
        self._mostrar_variacion(self._var_ventas_mensual, "vs. mes anterior", comparacion_v.variacion_mensual)
        self._mostrar_variacion(self._var_ventas_anual, "Interanual", comparacion_v.variacion_anual)

        comparacion_c = comparacion_cobranzas(self.conexion, hoy)
        self._valor_cobranzas.setText(formato_moneda(comparacion_c.total_actual))
        self._mostrar_variacion(self._var_cobranzas_mensual, "vs. mes anterior", comparacion_c.variacion_mensual)
        self._mostrar_variacion(self._var_cobranzas_anual, "Interanual", comparacion_c.variacion_anual)
        remitos_cobrados = total_remitos_cobrados_del_mes(self.conexion, mes_actual)
        self._etiqueta_remitos_cobrados.setText(
            f"De lo vendido este mes, ya cobrado: {formato_moneda(remitos_cobrados)}"
        )

        self._valor_deuda.setText(formato_moneda(deuda_total(self.conexion)))
        deuda_del_mes = deuda_de_lo_vendido_del_mes(self.conexion, mes_actual)
        self._etiqueta_deuda_del_mes.setText(
            f"De lo vendido este mes, la deuda es: {formato_moneda(deuda_del_mes)}"
        )

        self._valor_disponible.setText(formato_moneda(total_disponible_actual(self.conexion)))
        estado_caja = estado_de_caja_del_dia(self.conexion, hoy.isoformat())
        clave = (estado_caja["abierta"], estado_caja["cerrada"])
        self._etiqueta_caja.setText(f"Caja de hoy: {ETIQUETAS_ESTADO_CAJA.get(clave, 'Sin abrir')}")

        self._actualizar_grafico_evolucion(hoy)

        antiguedad = saldos_por_antiguedad(self.conexion, hoy.isoformat())
        self._actualizar_grafico_antiguedad(antiguedad)
        porcentaje_mas_30 = porcentaje_deuda_mayor_a_30_dias(antiguedad)
        texto_mas_30 = _formato_pct(porcentaje_mas_30) if porcentaje_mas_30 is not None else "Sin datos"
        self._etiqueta_mas_30.setText(f"Deuda con más de 30 días: {texto_mas_30}")

        top_clientes = top_clientes_por_saldo(self.conexion, cantidad=5)
        self._tabla_clientes.setRowCount(len(top_clientes))
        for fila, cliente in enumerate(top_clientes):
            self._tabla_clientes.setItem(fila, 0, QTableWidgetItem(cliente.nombre))
            item_saldo = QTableWidgetItem(formato_moneda(cliente.saldo))
            item_saldo.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._tabla_clientes.setItem(fila, 1, item_saldo)
        ajustar_columnas(self._tabla_clientes)

        actividad = actividad_comercial_del_mes(self.conexion, mes_actual)
        self._valor_compras.setText(formato_moneda(actividad.total_compras))
        self._valor_clientes_activos.setText(str(actividad.clientes_activos))
        self._valor_remitos.setText(str(actividad.remitos_emitidos))

    def _mostrar_variacion(self, etiqueta: QLabel, prefijo: str, variacion: Variacion) -> None:
        texto, color = _texto_variacion(variacion)
        etiqueta.setText(f"{prefijo}: {texto}")
        etiqueta.setStyleSheet(f"font-size: 11px; color: {color}; border: none;")

    def _actualizar_grafico_evolucion(self, hoy: date) -> None:
        _vaciar_layout(self._layout_grafico_evolucion)
        puntos = evolucion_ventas_cobranzas_12_meses(self.conexion, hoy)
        self._layout_grafico_evolucion.addWidget(grafico_lineas_multiples(
            "", [p.mes for p in puntos],
            [
                ("Venta", [p.venta for p in puntos]),
                ("Cobranza", [p.cobranza for p in puntos]),
            ],
            "Mes", "Monto", formateador_valor=formato_moneda,
        ))

    def _actualizar_grafico_antiguedad(self, antiguedad: dict[str, Decimal]) -> None:
        _vaciar_layout(self._layout_grafico_antiguedad)
        categorias = [f"{bucket} días" for bucket in antiguedad]
        valores = list(antiguedad.values())
        self._layout_grafico_antiguedad.addWidget(grafico_barras_horizontales(
            "", categorias, "Saldo", valores, "Monto", "Antigüedad",
        ))
