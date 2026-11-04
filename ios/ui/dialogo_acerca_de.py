"""Diálogo Ayuda → Acerca de IOS: logo y versión (docs/AJUSTES_V1.1.md,
etapa 1)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from ios.recursos import RUTA_LOGO
from ios.version import IOS_VERSION


class DialogoAcercaDeIOS(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Acerca de IOS")

        layout = QVBoxLayout(self)

        if RUTA_LOGO.exists():
            logo = QLabel()
            logo.setPixmap(
                QPixmap(str(RUTA_LOGO)).scaledToWidth(160, Qt.SmoothTransformation)
            )
            logo.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo)

        titulo = QLabel("IOS — Insumos Oftalmológicos Santiago")
        titulo.setAlignment(Qt.AlignCenter)
        titulo.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(titulo)

        version = QLabel(f"Versión {IOS_VERSION}")
        version.setAlignment(Qt.AlignCenter)
        layout.addWidget(version)

        boton_cerrar = QPushButton("Cerrar")
        boton_cerrar.clicked.connect(self.accept)
        layout.addWidget(boton_cerrar)
