"""Resumen de la importación desde Excel: qué se decidió para cada
conflicto (docs/AJUSTES_V1.1.md, etapa 7)."""

from __future__ import annotations

from pathlib import Path

import openpyxl

from ios.services.importacion_excel import Conflicto

TIPOS_CONFLICTO_ETIQUETAS = {
    "remito_repetido": "Remito repetido",
    "iva_no_coincide": "IVA que no coincide",
    "pago_suelto": "Pago suelto sin remito",
    "recibo_compartido": "Recibo compartido entre hojas",
    "recibo_con_texto": "Recibo con texto",
    "posible_sucursal": "Hoja que parece sucursal de otro cliente",
}


def generar_excel_resumen_conflictos(
    conflictos: list[Conflicto], decisiones: dict[str, str], ruta_salida: Path | str
) -> Path:
    libro = openpyxl.Workbook()
    ws = libro.active
    ws.title = "Resumen de conflictos"
    ws.append(["Tipo", "Hoja", "Fila", "Descripción", "Decisión aplicada"])
    for conflicto in conflictos:
        ws.append([
            TIPOS_CONFLICTO_ETIQUETAS.get(conflicto.tipo, conflicto.tipo),
            conflicto.hoja,
            conflicto.fila or "",
            conflicto.descripcion,
            decisiones.get(conflicto.id, conflicto.sugerida),
        ])

    ruta_salida = Path(ruta_salida)
    ruta_salida.parent.mkdir(parents=True, exist_ok=True)
    libro.save(ruta_salida)
    return ruta_salida
