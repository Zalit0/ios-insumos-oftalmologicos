"""Ventana principal: barra de menú superior + una pantalla por sección
(docs/AJUSTES_V1.1.md, etapa 1 — reemplaza el menú lateral de la v1.0).
El área central es un ``QStackedWidget``; la ventana no tiene lógica de
negocio, cada pantalla llama a ios/services/."""

from __future__ import annotations

import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QStackedWidget,
    QWidget,
)

from ios.recursos import RUTA_ICONO
from ios.services.actualizaciones import ErrorActualizacion, buscar_actualizacion, descargar_instalador
from ios.ui.dialogo_acerca_de import DialogoAcercaDeIOS
from ios.ui.pages.caja_diaria import PaginaCajaDiaria
from ios.ui.pages.cheques import PaginaCheques
from ios.ui.pages.clientes import PaginaClientes
from ios.ui.pages.cobranzas import PaginaCobranzas
from ios.ui.pages.compras_por_cliente import PaginaComprasPorCliente
from ios.ui.pages.compras_proveedores import PaginaComprasProveedores
from ios.ui.pages.comprobantes import PaginaComprobantes
from ios.ui.pages.configuracion import PaginaConfiguracion
from ios.ui.pages.cuenta_corriente import PaginaCuentaCorriente
from ios.ui.pages.deudores import PaginaDeudores
from ios.ui.pages.entrega_pedidos import PaginaEntregaPedidos
from ios.ui.pages.exportacion_contador import PaginaExportacionContador
from ios.ui.pages.facturacion import PaginaFacturacion
from ios.ui.pages.flujo_caja import PaginaFlujoCaja
from ios.ui.pages.gastos_caja_chica import PaginaGastosCajaChica
from ios.ui.pages.importar_excel import PaginaImportarExcel
from ios.ui.pages.inicio import PaginaInicio
from ios.ui.pages.iva_mes import PaginaIvaMes
from ios.ui.pages.pedidos_proveedor import PaginaPedidosProveedor
from ios.ui.pages.recepcion_pedidos import PaginaRecepcionPedidos
from ios.ui.pages.recibos import PaginaRecibos
from ios.ui.pages.ver_pedidos import PaginaVerPedidos
from ios.ui.pages.resumen_mensual import PaginaResumenMensual
from ios.version import IOS_VERSION

AccionAlMostrar = Callable[[QWidget], None]


def _ir_a_pestana_pagos(pagina: QWidget) -> None:
    pagina._pestanas.setCurrentIndex(pagina.INDICE_PESTANA_PAGOS)


@dataclass
class OpcionMenu:
    nombre: str
    fabrica: type
    atajo: str | None = None
    al_mostrar: AccionAlMostrar | None = None


# Estructura del menú (docs/AJUSTES_V1.1.md, etapa 1). Las pantallas de
# etapas posteriores (Facturación, Gastos de caja chica, Compras por
# cliente) se agregan acá cuando existan, no antes.
MENUS: list[tuple[str, list[OpcionMenu]]] = [
    ("&Inicio", [
        OpcionMenu("Dashboard", PaginaInicio),
    ]),
    ("&Ventas", [
        OpcionMenu("Facturación", PaginaFacturacion, "F2"),
        OpcionMenu("Comprobantes", PaginaComprobantes),
        OpcionMenu("Cobranzas", PaginaCobranzas, "F3"),
        OpcionMenu("Recibos", PaginaRecibos),
        OpcionMenu("Cuenta corriente", PaginaCuentaCorriente, "F5"),
        OpcionMenu("Clientes", PaginaClientes),
    ]),
    ("&Compras", [
        OpcionMenu("Compras y proveedores", PaginaComprasProveedores),
        OpcionMenu("Pagos a proveedores", PaginaComprasProveedores, al_mostrar=_ir_a_pestana_pagos),
        OpcionMenu("Pedidos a proveedor", PaginaPedidosProveedor),
        OpcionMenu("Recepción de pedidos", PaginaRecepcionPedidos),
        OpcionMenu("Entrega de pedidos especiales", PaginaEntregaPedidos),
        OpcionMenu("Ver pedidos", PaginaVerPedidos),
    ]),
    ("Ca&ja", [
        OpcionMenu("Caja diaria", PaginaCajaDiaria, "F4"),
        OpcionMenu("Cheques", PaginaCheques),
        OpcionMenu("Gastos de caja chica", PaginaGastosCajaChica),
    ]),
    ("&Reportes", [
        OpcionMenu("Resumen mensual", PaginaResumenMensual),
        OpcionMenu("Compras por cliente", PaginaComprasPorCliente),
        OpcionMenu("Deudores", PaginaDeudores),
        OpcionMenu("IVA del mes", PaginaIvaMes),
        OpcionMenu("Flujo de caja", PaginaFlujoCaja),
        OpcionMenu("Exportación para el contador", PaginaExportacionContador),
    ]),
    ("&Herramientas", [
        OpcionMenu("Importar desde Excel", PaginaImportarExcel),
        OpcionMenu("Configuración", PaginaConfiguracion),
    ]),
]


class MainWindow(QMainWindow):
    def __init__(self, conexion: sqlite3.Connection) -> None:
        super().__init__()
        self.conexion = conexion

        if RUTA_ICONO.exists():
            self.setWindowIcon(QIcon(str(RUTA_ICONO)))
        self.resize(1100, 700)

        self._paginas = QStackedWidget()
        self.setCentralWidget(self._paginas)

        self._paginas_por_fabrica: dict[type, QWidget] = {}
        indice_inicio = 0
        nombre_inicio = "Dashboard"

        barra_menu = self.menuBar()
        for nombre_menu, opciones in MENUS:
            menu = barra_menu.addMenu(nombre_menu)
            for opcion in opciones:
                indice = self._indice_de_pagina(opcion.fabrica)
                if nombre_menu == "&Inicio" and opcion.nombre == nombre_inicio:
                    indice_inicio = indice

                accion = QAction(opcion.nombre, self)
                if opcion.atajo:
                    accion.setShortcut(opcion.atajo)
                accion.triggered.connect(
                    lambda checked=False, i=indice, n=opcion.nombre, am=opcion.al_mostrar: (
                        self._navegar(i, n, am)
                    )
                )
                menu.addAction(accion)

        menu_ayuda = barra_menu.addMenu("A&yuda")
        accion_acerca_de = QAction("Acerca de IOS", self)
        accion_acerca_de.triggered.connect(self._mostrar_acerca_de)
        menu_ayuda.addAction(accion_acerca_de)
        accion_buscar_actualizacion = QAction("Buscar actualización", self)
        accion_buscar_actualizacion.triggered.connect(self._buscar_actualizacion)
        menu_ayuda.addAction(accion_buscar_actualizacion)

        self._conectar_navegacion_del_dashboard()
        self._navegar(indice_inicio, nombre_inicio)

    def _conectar_navegacion_del_dashboard(self) -> None:
        """Las tarjetas y filas del Dashboard (ios/ui/pages/inicio.py) solo
        emiten una señal: esta ventana es quien sabe a qué pantalla lleva
        cada una (docs/AJUSTES_V1.1.md, rediseño del Dashboard,
        interactividad)."""
        pagina_inicio = self._paginas_por_fabrica[PaginaInicio]
        pagina_inicio.navegarVentas.connect(
            lambda: self._navegar(self._indice_de_pagina(PaginaComprobantes), "Comprobantes")
        )
        pagina_inicio.navegarCobranzas.connect(
            lambda: self._navegar(self._indice_de_pagina(PaginaCobranzas), "Cobranzas")
        )
        pagina_inicio.navegarDeuda.connect(
            lambda: self._navegar(self._indice_de_pagina(PaginaDeudores), "Deudores")
        )
        pagina_inicio.navegarCompras.connect(
            lambda: self._navegar(
                self._indice_de_pagina(PaginaComprasProveedores), "Compras y proveedores"
            )
        )
        pagina_inicio.navegarCuentaCorriente.connect(
            lambda: self._navegar(self._indice_de_pagina(PaginaCuentaCorriente), "Cuenta corriente")
        )

    def _indice_de_pagina(self, fabrica: type) -> int:
        """Crea la página la primera vez que se la referencia; si dos
        opciones de menú apuntan a la misma pantalla (Compras y
        proveedores / Pagos a proveedores), comparten una sola instancia."""
        if fabrica not in self._paginas_por_fabrica:
            pagina = fabrica(self.conexion)
            self._paginas_por_fabrica[fabrica] = pagina
            self._paginas.addWidget(pagina)
        return self._paginas.indexOf(self._paginas_por_fabrica[fabrica])

    def _navegar(self, indice: int, nombre_pantalla: str, al_mostrar: AccionAlMostrar | None = None) -> None:
        pagina_actual = self._paginas.currentWidget()
        if pagina_actual is not None and hasattr(pagina_actual, "reiniciar"):
            pagina_actual.reiniciar()

        self._paginas.setCurrentIndex(indice)
        nueva_pagina = self._paginas.widget(indice)
        if hasattr(nueva_pagina, "actualizar"):
            nueva_pagina.actualizar()
        if al_mostrar is not None:
            al_mostrar(nueva_pagina)

        self.setWindowTitle(f"IOS — {nombre_pantalla}")

    def _mostrar_acerca_de(self) -> None:
        DialogoAcercaDeIOS(self).exec()

    # --- Ayuda → Buscar actualización ---

    def _buscar_actualizacion(self) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            info = buscar_actualizacion(IOS_VERSION)
        except ErrorActualizacion as error:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "No se pudo buscar la actualización", str(error))
            return
        QApplication.restoreOverrideCursor()

        if info is None:
            QMessageBox.information(
                self, "Sin novedades", f"Ya tenés la última versión instalada (v{IOS_VERSION})."
            )
            return

        mensaje = f"Hay una versión nueva disponible: v{info.version}."
        if info.notas:
            mensaje += f"\n\n{info.notas}"
        mensaje += (
            "\n\n¿Descargarla e instalarla ahora? La aplicación se va a cerrar para "
            "completar la instalación."
        )
        respuesta = QMessageBox.question(self, "Actualización disponible", mensaje)
        if respuesta != QMessageBox.Yes:
            return

        self._descargar_e_instalar_actualizacion(info.url_descarga)

    def _descargar_e_instalar_actualizacion(self, url_descarga: str) -> None:
        destino = Path(tempfile.gettempdir()) / "Instalar IOS.exe"
        dialogo = QProgressDialog("Descargando la actualización...", "Cancelar", 0, 0, self)
        dialogo.setWindowModality(Qt.WindowModal)
        dialogo.setMinimumDuration(0)
        dialogo.show()

        def progreso(leido: int, total: int) -> None:
            if total > 0:
                dialogo.setMaximum(total)
                dialogo.setValue(leido)
            QApplication.processEvents()
            if dialogo.wasCanceled():
                raise _DescargaCancelada()

        try:
            descargar_instalador(url_descarga, destino, progreso)
        except _DescargaCancelada:
            dialogo.close()
            return
        except Exception as error:
            dialogo.close()
            QMessageBox.warning(self, "No se pudo descargar la actualización", str(error))
            return
        dialogo.close()

        subprocess.Popen([str(destino)])
        QApplication.instance().quit()


class _DescargaCancelada(Exception):
    """El usuario canceló la descarga desde el diálogo de progreso."""
