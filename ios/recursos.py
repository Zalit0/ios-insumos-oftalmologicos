"""Resuelve la ruta de assets/ (logo, ícono) tanto corriendo desde el
código fuente como empaquetado con PyInstaller.

Empaquetado (modo carpeta u onefile), PyInstaller copia los datos
agregados con ``--add-data`` a una carpeta propia (``_internal/`` en modo
carpeta; una carpeta temporal en onefile) expuesta en ``sys._MEIPASS``.
En desarrollo, la base es la raíz del proyecto.
"""

from __future__ import annotations

import sys
from pathlib import Path


def ruta_base() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass is not None:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


RUTA_ASSETS = ruta_base() / "assets"
RUTA_LOGO = RUTA_ASSETS / "logo.png"
RUTA_ICONO = RUTA_ASSETS / "ios.ico"
