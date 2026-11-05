"""Ayuda → Buscar actualización: consulta el último release de GitHub y
descarga el instalador si hay una versión más nueva."""

from __future__ import annotations

import json
import ssl
import urllib.error
from pathlib import Path

import pytest

from ios.services import actualizaciones
from ios.services.actualizaciones import (
    ErrorActualizacion,
    buscar_actualizacion,
    descargar_instalador,
)


class _RespuestaFalsa:
    def __init__(self, cuerpo: bytes, headers: dict | None = None):
        self._cuerpo = cuerpo
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, n: int | None = None) -> bytes:
        if n is None:
            cuerpo, self._cuerpo = self._cuerpo, b""
            return cuerpo
        bloque, self._cuerpo = self._cuerpo[:n], self._cuerpo[n:]
        return bloque


def _release(tag: str, assets: list[dict] | None = None, body: str = "") -> bytes:
    return json.dumps({
        "tag_name": tag,
        "body": body,
        "assets": assets if assets is not None else [
            {"name": "Instalar IOS.exe", "browser_download_url": "https://example.com/setup.exe"}
        ],
    }).encode("utf-8")


def test_hay_version_mas_nueva_devuelve_la_info(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: _RespuestaFalsa(_release("v1.2.0", body="Novedades"))
    )

    info = buscar_actualizacion("1.1.0")

    assert info is not None
    assert info.version == "1.2.0"
    assert info.url_descarga == "https://example.com/setup.exe"
    assert info.notas == "Novedades"


def test_misma_version_devuelve_none(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _RespuestaFalsa(_release("v1.1.0")))

    assert buscar_actualizacion("1.1.0") is None


def test_version_anterior_en_el_release_devuelve_none(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _RespuestaFalsa(_release("v1.0.0")))

    assert buscar_actualizacion("1.1.0") is None


def test_si_certifi_falla_por_certificado_reintenta_con_el_sistema(monkeypatch):
    """Una PC con una raíz propia instalada en Windows (por ejemplo, un
    antivirus que inspecciona HTTPS) puede no estar en el paquete de
    certifi: ahí falla por certificado y hay que reintentar con el
    almacén del sistema en vez de darse por vencido."""
    llamadas = []

    def _urlopen(pedido, timeout=None, context=None):
        llamadas.append(context)
        if context is actualizaciones._CONTEXTO_CERTIFI:
            raise urllib.error.URLError(
                ssl.SSLCertVerificationError("unable to get local issuer certificate")
            )
        return _RespuestaFalsa(_release("v1.2.0"))

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)

    info = buscar_actualizacion("1.1.0")

    assert info is not None
    assert llamadas == [actualizaciones._CONTEXTO_CERTIFI, actualizaciones._CONTEXTO_SISTEMA]


def test_sin_conexion_levanta_error_actualizacion(monkeypatch):
    def _falla(*a, **k):
        raise urllib.error.URLError("sin conexión")

    monkeypatch.setattr("urllib.request.urlopen", _falla)

    with pytest.raises(ErrorActualizacion):
        buscar_actualizacion("1.1.0")


def test_error_403_de_github_levanta_error_actualizacion_especifico(monkeypatch):
    def _falla(*a, **k):
        raise urllib.error.HTTPError("url", 403, "rate limit", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", _falla)

    with pytest.raises(ErrorActualizacion, match="límite"):
        buscar_actualizacion("1.1.0")


def test_release_sin_instalador_adjunto_levanta_error_actualizacion(monkeypatch):
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *a, **k: _RespuestaFalsa(_release("v1.2.0", assets=[]))
    )

    with pytest.raises(ErrorActualizacion):
        buscar_actualizacion("1.1.0")


def test_descargar_instalador_escribe_el_archivo(monkeypatch, tmp_path):
    contenido = b"x" * 1000
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _RespuestaFalsa(contenido, headers={"Content-Length": str(len(contenido))}),
    )

    destino = tmp_path / "setup.exe"
    progresos = []
    resultado = descargar_instalador(
        "https://example.com/setup.exe", destino, lambda leido, total: progresos.append((leido, total))
    )

    assert resultado == destino
    assert destino.read_bytes() == contenido
    assert progresos[-1] == (1000, 1000)


def test_descargar_instalador_cancelado_borra_el_archivo_parcial(monkeypatch, tmp_path):
    contenido = b"x" * 1000
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: _RespuestaFalsa(contenido, headers={"Content-Length": str(len(contenido))}),
    )

    destino = tmp_path / "setup.exe"

    def progreso_que_cancela(leido: int, total: int) -> None:
        raise RuntimeError("cancelado")

    with pytest.raises(RuntimeError):
        descargar_instalador("https://example.com/setup.exe", destino, progreso_que_cancela)

    assert not destino.exists()
