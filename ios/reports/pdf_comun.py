"""Armado común de los PDF de IOS: logo en el encabezado, título y una
tabla con estilo consistente (docs/PLAN.md: "con el logo de IOS en el
encabezado")."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ios.recursos import RUTA_LOGO

_ESTILOS = getSampleStyleSheet()
ESTILO_TITULO = ParagraphStyle(
    "TituloIOS", parent=_ESTILOS["Heading1"], fontSize=16, spaceAfter=2 * mm
)
ESTILO_SUBTITULO = ParagraphStyle(
    "SubtituloIOS", parent=_ESTILOS["Normal"], fontSize=11, textColor=colors.grey
)
ESTILO_NORMAL = _ESTILOS["Normal"]

COLOR_ENCABEZADO_TABLA = colors.HexColor("#2b4c7e")


def encabezado(titulo: str, subtitulo: str | None = None) -> list:
    elementos = []
    if RUTA_LOGO.exists():
        elementos.append(Image(str(RUTA_LOGO), width=25 * mm, height=25 * mm))
    elementos.append(Paragraph(titulo, ESTILO_TITULO))
    if subtitulo:
        elementos.append(Paragraph(subtitulo, ESTILO_SUBTITULO))
    elementos.append(Spacer(1, 4 * mm))
    return elementos


def tabla(
    encabezados: list[str],
    filas: list[list[str]],
    anchos: list[float] | None = None,
    alinear_derecha: list[int] | None = None,
) -> Table:
    """``alinear_derecha`` son los índices de columna (p. ej. los
    importes) a alinear a la derecha, encabezado incluido; por defecto
    ninguna columna se alinea (se mantiene el comportamiento de
    siempre)."""
    datos = [encabezados] + filas
    tabla_ = Table(datos, colWidths=anchos, repeatRows=1)
    estilos = [
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_ENCABEZADO_TABLA),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for columna in alinear_derecha or []:
        estilos.append(("ALIGN", (columna, 0), (columna, -1), "RIGHT"))
    tabla_.setStyle(TableStyle(estilos))
    return tabla_


def generar_pdf(ruta_salida: Path | str, elementos: list) -> Path:
    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    documento = SimpleDocTemplate(
        str(ruta_salida), pagesize=A4,
        topMargin=15 * mm, bottomMargin=15 * mm, leftMargin=15 * mm, rightMargin=15 * mm,
    )
    documento.build(elementos)
    return ruta_salida
