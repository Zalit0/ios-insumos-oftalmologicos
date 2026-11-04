"""Punto de entrada de IOS."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from ios.data.db import conectar
from ios.ui.main_window import MainWindow


def main() -> int:
    conexion = conectar()
    app = QApplication(sys.argv)
    ventana = MainWindow(conexion)
    ventana.show()
    codigo = app.exec()
    conexion.close()
    return codigo


if __name__ == "__main__":
    sys.exit(main())
