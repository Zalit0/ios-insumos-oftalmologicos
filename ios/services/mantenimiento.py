"""Instalación limpia: reiniciar la base de datos a cero desde el propio
programa, conservando siempre un respaldo de la anterior
(docs/AJUSTES_V1.1.md, Instalación limpia)."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

PALABRA_CONFIRMACION = "BORRAR"


def reiniciar_base_de_datos(ruta_base_datos: Path | str, palabra_confirmacion: str) -> Path | None:
    """Mueve la base actual a un archivo de respaldo con fecha y hora, para
    que la próxima conexión cree una base nueva y vacía (igual que hace
    ``ios.data.db.conectar`` cuando el archivo no existe). Exige escribir
    la palabra de confirmación exacta, para no borrar datos por error.
    Devuelve la ruta del respaldo, o ``None`` si no había base para mover."""
    if palabra_confirmacion != PALABRA_CONFIRMACION:
        raise ValueError(f'Para confirmar, hay que escribir exactamente "{PALABRA_CONFIRMACION}".')

    ruta_base_datos = Path(ruta_base_datos)
    if not ruta_base_datos.exists():
        return None

    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    ruta_respaldo = ruta_base_datos.with_name(
        f"{ruta_base_datos.stem}_respaldo_{marca}{ruta_base_datos.suffix}"
    )
    shutil.move(str(ruta_base_datos), str(ruta_respaldo))
    return ruta_respaldo
