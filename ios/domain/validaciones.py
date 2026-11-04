"""Validaciones de datos de negocio que no dependen de la base ni de la UI.

docs/AJUSTES_V1.1.md, etapa 4: el CUIT se valida (formato + dígito
verificador) pero nunca bloquea el alta/edición de un cliente; quien llama
decide qué hacer con el resultado (p.ej. mostrar un aviso).
"""

from __future__ import annotations

_MULTIPLICADORES = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)


def cuit_valido(cuit: str) -> bool:
    """True si ``cuit`` tiene el formato XX-XXXXXXXX-X (con o sin guiones)
    y su dígito verificador es correcto."""
    digitos = cuit.replace("-", "").strip()
    if len(digitos) != 11 or not digitos.isdigit():
        return False

    suma = sum(int(digito) * mult for digito, mult in zip(digitos[:10], _MULTIPLICADORES))
    resto = suma % 11
    verificador_esperado = 11 - resto
    if verificador_esperado == 11:
        verificador_esperado = 0
    elif verificador_esperado == 10:
        return False

    return verificador_esperado == int(digitos[10])
