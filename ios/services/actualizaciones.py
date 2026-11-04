"""Actualización remota de IOS: Ayuda → Buscar actualización consulta el
último release publicado en GitHub y, si es más nuevo que la versión
instalada (``ios.version.IOS_VERSION``), descarga el instalador para que
la pantalla lo ejecute.

El número de versión del release en GitHub (el tag, por ejemplo "v1.2.0")
tiene que coincidir con ``IOS_VERSION`` de la versión que se publica ahí:
es la única forma en que esta función sabe si hay algo más nuevo.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPOSITORIO = "Zalit0/ios-insumos-oftalmologicos"
URL_ULTIMO_RELEASE = f"https://api.github.com/repos/{REPOSITORIO}/releases/latest"
TIMEOUT_SEGUNDOS = 10
TAMANIO_BLOQUE = 256 * 1024


class ErrorActualizacion(Exception):
    """No se pudo consultar o descargar la actualización (sin conexión,
    repositorio sin releases, release sin instalador adjunto, etc.)."""


@dataclass
class InfoActualizacion:
    version: str
    url_descarga: str
    notas: str


def _version_a_tupla(version: str) -> tuple[int, ...]:
    partes = []
    for parte in version.strip().lstrip("vV").split("."):
        try:
            partes.append(int(parte))
        except ValueError:
            break
    return tuple(partes)


def buscar_actualizacion(version_actual: str) -> InfoActualizacion | None:
    """Devuelve la info del último release si es más nuevo que
    ``version_actual``, o ``None`` si ya está al día."""
    try:
        with urllib.request.urlopen(URL_ULTIMO_RELEASE, timeout=TIMEOUT_SEGUNDOS) as respuesta:
            datos = json.loads(respuesta.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
        raise ErrorActualizacion(
            "No se pudo conectar para buscar actualizaciones. Revisá tu conexión a internet."
        ) from error
    except json.JSONDecodeError as error:
        raise ErrorActualizacion(
            "La respuesta del servidor de actualizaciones no es válida."
        ) from error

    version_nueva = _version_a_tupla(datos.get("tag_name", ""))
    if not version_nueva or version_nueva <= _version_a_tupla(version_actual):
        return None

    instalador = next(
        (
            activo for activo in datos.get("assets", [])
            if activo.get("name", "").lower().endswith(".exe")
        ),
        None,
    )
    if instalador is None:
        raise ErrorActualizacion(
            "Hay una versión nueva, pero el release no tiene un instalador adjunto."
        )

    return InfoActualizacion(
        version=datos.get("tag_name", "").strip().lstrip("vV"),
        url_descarga=instalador["browser_download_url"],
        notas=(datos.get("body") or "").strip(),
    )


def descargar_instalador(
    url: str, destino: Path, progreso: Callable[[int, int], None] | None = None,
) -> Path:
    """Descarga el instalador a ``destino``. Si se indica ``progreso``, se
    llama con (bytes leídos, bytes totales) después de cada bloque; si esa
    llamada levanta una excepción (por ejemplo, para cancelar), se borra el
    archivo parcial y la excepción se propaga."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SEGUNDOS) as respuesta:
            total = int(respuesta.headers.get("Content-Length", 0))
            leido = 0
            with open(destino, "wb") as archivo:
                while True:
                    bloque = respuesta.read(TAMANIO_BLOQUE)
                    if not bloque:
                        break
                    archivo.write(bloque)
                    leido += len(bloque)
                    if progreso is not None:
                        progreso(leido, total)
    except BaseException:
        Path(destino).unlink(missing_ok=True)
        raise
    return destino
