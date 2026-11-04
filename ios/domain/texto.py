"""Normalización de texto para comparaciones sin distinguir mayúsculas ni
acentos (docs/AJUSTES_V1.1.md, etapa 2: buscador de clientes; etapa 7:
detección de hojas que parecen sucursal de otro cliente)."""

from __future__ import annotations

import unicodedata


def normalizar(texto: str) -> str:
    """Mayúsculas y sin acentos ("optica" encuentra "ÓPTICA CIUDAD")."""
    sin_acentos = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sin_acentos.upper()
