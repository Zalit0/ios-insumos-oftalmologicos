"""Instalación limpia: reiniciar la base de datos moviendo la actual a un
respaldo (docs/AJUSTES_V1.1.md, Instalación limpia)."""

from pathlib import Path

import pytest

from ios.services.mantenimiento import PALABRA_CONFIRMACION, reiniciar_base_de_datos


def test_palabra_incorrecta_no_toca_el_archivo(tmp_path: Path):
    ruta = tmp_path / "ios.db"
    ruta.write_text("datos originales")

    with pytest.raises(ValueError):
        reiniciar_base_de_datos(ruta, "borrar")  # minúscula: no coincide

    assert ruta.read_text() == "datos originales"


def test_sin_base_previa_no_hace_nada_y_devuelve_none(tmp_path: Path):
    ruta = tmp_path / "ios.db"

    respaldo = reiniciar_base_de_datos(ruta, PALABRA_CONFIRMACION)

    assert respaldo is None
    assert not ruta.exists()


def test_con_base_existente_la_mueve_al_respaldo_intacta(tmp_path: Path):
    ruta = tmp_path / "ios.db"
    ruta.write_bytes(b"contenido real de la base")

    respaldo = reiniciar_base_de_datos(ruta, PALABRA_CONFIRMACION)

    assert respaldo is not None
    assert not ruta.exists()
    assert respaldo.exists()
    assert respaldo.read_bytes() == b"contenido real de la base"
    assert respaldo.parent == ruta.parent
    assert respaldo.name.startswith("ios_respaldo_")
