# -*- coding: utf-8 -*-
"""Genera docs/Manual del usuario IOS.pdf a partir de este script.

No es parte de la app: es documentación. Se vuelve a correr cada vez que
se agrega o cambia algo en el programa, para que el manual no quede
desactualizado (ver docs/CONTEXTO.md).

Las capturas de pantalla van en docs/manual/capturas/, con el nombre de
archivo que indica cada llamada a ``captura()`` más abajo. Si un archivo
todavía no existe, el manual se genera igual, con un recuadro gris que
dice qué captura falta — así nunca hace falta tener todas las imágenes
para poder generar una versión del manual.

Uso:
    .venv\\Scripts\\python.exe docs\\manual\\generar_manual.py
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    Image,
    ListFlowable,
    ListItem,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

RUTA_MANUAL = Path(__file__).parent
RUTA_CAPTURAS = RUTA_MANUAL / "capturas"
RUTA_SALIDA = RUTA_MANUAL.parent / "Manual del usuario IOS.pdf"
RUTA_LOGO = RUTA_MANUAL.parent.parent / "assets" / "logo.png"

AZUL = colors.HexColor("#2b4c7e")
GRIS = colors.HexColor("#555555")
GRIS_CLARO = colors.HexColor("#f2f2f2")
GRIS_BORDE = colors.HexColor("#cccccc")
AMBAR = colors.HexColor("#92400e")
AMBAR_FONDO = colors.HexColor("#fef3c7")
VERDE = colors.HexColor("#14532d")
VERDE_FONDO = colors.HexColor("#dcfce7")

estilos = getSampleStyleSheet()

ESTILO_PORTADA_TITULO = ParagraphStyle(
    "PortadaTitulo", parent=estilos["Title"], fontSize=26, textColor=AZUL, alignment=TA_CENTER,
)
ESTILO_PORTADA_SUB = ParagraphStyle(
    "PortadaSub", parent=estilos["Normal"], fontSize=13, textColor=GRIS, alignment=TA_CENTER,
    spaceAfter=4 * mm,
)
ESTILO_MODULO = ParagraphStyle(
    "Modulo", parent=estilos["Heading1"], fontSize=18, textColor=colors.white,
    backColor=AZUL, borderPadding=(6, 8, 6, 8), spaceAfter=9 * mm, spaceBefore=0,
)
ESTILO_PANTALLA = ParagraphStyle(
    "Pantalla", parent=estilos["Heading2"], fontSize=14, textColor=AZUL,
    spaceBefore=9 * mm, spaceAfter=5 * mm,
)
ESTILO_SUBTEMA = ParagraphStyle(
    "Subtema", parent=estilos["Heading3"], fontSize=11.5, textColor=colors.black,
    spaceBefore=6 * mm, spaceAfter=3 * mm,
)
ESTILO_CUERPO = ParagraphStyle(
    "Cuerpo", parent=estilos["Normal"], fontSize=10, leading=15.5,
    spaceBefore=1 * mm, spaceAfter=3.5 * mm,
)
ESTILO_LISTA = ParagraphStyle("Lista", parent=ESTILO_CUERPO, leftIndent=0, spaceAfter=1.5 * mm)
ESTILO_TOC_MODULO = ParagraphStyle(
    "TocModulo", parent=estilos["Normal"], fontSize=12, textColor=AZUL,
    spaceBefore=4 * mm, spaceAfter=1 * mm,
)
ESTILO_TOC_PANTALLA = ParagraphStyle(
    "TocPantalla", parent=estilos["Normal"], fontSize=10.5, leftIndent=6 * mm, spaceAfter=0.8 * mm,
)
ESTILO_PIE = ParagraphStyle(
    "Pie", parent=estilos["Normal"], fontSize=8, textColor=GRIS, alignment=TA_CENTER,
)
ESTILO_CAPTION = ParagraphStyle(
    "Caption", parent=estilos["Normal"], fontSize=8.5, textColor=GRIS, alignment=TA_CENTER,
    spaceBefore=1 * mm, spaceAfter=3 * mm,
)
ESTILO_PLACEHOLDER = ParagraphStyle(
    "Placeholder", parent=estilos["Normal"], fontSize=9, textColor=GRIS, alignment=TA_CENTER,
)
ESTILO_GLOSARIO_TERMINO = ParagraphStyle(
    "GlosarioTermino", parent=ESTILO_CUERPO, fontName="Helvetica-Bold",
    spaceBefore=3 * mm, spaceAfter=0.5 * mm,
)


class DocumentoConMarcadores(BaseDocTemplate):
    """Cada encabezado con ``bookmark_key`` (puesto por ``titulo_modulo``/
    ``titulo_pantalla``) deja un marcador: es el destino de los links del
    índice y una entrada del panel de marcadores del lector de PDF."""

    def afterFlowable(self, flowable):
        key = getattr(flowable, "bookmark_key", None)
        if key is None:
            return
        nivel = getattr(flowable, "bookmark_level", 0)
        texto = getattr(flowable, "bookmark_text", "")
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(texto, key, level=nivel, closed=False)


def pie_de_pagina(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRIS)
    canvas.drawCentredString(A4[0] / 2, 12 * mm, f"IOS — Manual del usuario · página {doc.page}")
    canvas.restoreState()


def titulo_modulo(texto: str, key: str) -> Paragraph:
    p = Paragraph(texto, ESTILO_MODULO)
    p.bookmark_key, p.bookmark_level, p.bookmark_text = key, 0, texto
    return p


def titulo_pantalla(texto: str, key: str) -> Paragraph:
    p = Paragraph(texto, ESTILO_PANTALLA)
    p.bookmark_key, p.bookmark_level, p.bookmark_text = key, 1, texto
    return p


def subtema(texto: str) -> Paragraph:
    return Paragraph(texto, ESTILO_SUBTEMA)


def cuerpo(texto: str) -> Paragraph:
    return Paragraph(texto, ESTILO_CUERPO)


def pasos(items: list[str]) -> ListFlowable:
    """Lista numerada: para procedimientos, paso a paso."""
    return ListFlowable(
        [ListItem(Paragraph(item, ESTILO_LISTA), spaceAfter=2.5 * mm) for item in items],
        bulletType="1", start="1", leftIndent=10 * mm, spaceBefore=2 * mm, spaceAfter=3 * mm,
    )


def lista(items: list[str]) -> ListFlowable:
    """Lista con viñetas: para enumerar cosas sin un orden obligatorio."""
    return ListFlowable(
        [ListItem(Paragraph(item, ESTILO_LISTA), spaceAfter=2 * mm) for item in items],
        bulletType="bullet", start="•", leftIndent=10 * mm, spaceBefore=2 * mm, spaceAfter=3 * mm,
    )


def _recuadro(texto: str, fondo, borde) -> Table:
    estilo_interno = ParagraphStyle("CuerpoRecuadro", parent=ESTILO_CUERPO, spaceBefore=0, spaceAfter=0)
    tabla = Table([[Paragraph(texto, estilo_interno)]], colWidths=[160 * mm])
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), fondo),
        ("BOX", (0, 0), (-1, -1), 0.5, borde),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    tabla.spaceBefore = 2 * mm
    tabla.spaceAfter = 4 * mm
    return tabla


def tip(texto: str) -> Table:
    return _recuadro(f"<b>Tip:</b> {texto}", GRIS_CLARO, colors.lightgrey)


def importante(texto: str) -> Table:
    return _recuadro(f"<b>Importante:</b> {texto}", AMBAR_FONDO, AMBAR)


def ejemplo(texto: str) -> Table:
    return _recuadro(f"<b>Ejemplo:</b> {texto}", VERDE_FONDO, VERDE)


def toc_link(texto: str, key: str, estilo=ESTILO_TOC_PANTALLA) -> Paragraph:
    return Paragraph(f'<a href="#{key}" color="#2b4c7e">{texto}</a>', estilo)


def captura(archivo: str, descripcion: str) -> list:
    """Inserta la captura de pantalla ``docs/manual/capturas/<archivo>`` con
    ``descripcion`` como epígrafe. Si el archivo todavía no existe, deja un
    recuadro gris indicando qué falta, para no bloquear la generación del
    manual mientras se van juntando las capturas."""
    elementos: list = [Spacer(1, 2 * mm)]
    ruta = RUTA_CAPTURAS / archivo
    if ruta.exists():
        ancho_max, alto_max = 160 * mm, 95 * mm
        iw, ih = ImageReader(str(ruta)).getSize()
        escala = min(ancho_max / iw, alto_max / ih, 1.0)
        elementos.append(Image(str(ruta), width=iw * escala, height=ih * escala, hAlign="CENTER"))
        elementos.append(Paragraph(descripcion, ESTILO_CAPTION))
    else:
        tabla = Table(
            [[Paragraph(f"[Falta la captura <b>{archivo}</b> — {descripcion}]", ESTILO_PLACEHOLDER)]],
            colWidths=[160 * mm], rowHeights=[20 * mm],
        )
        tabla.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 1, GRIS_BORDE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ]))
        elementos.append(tabla)
        elementos.append(Spacer(1, 1 * mm))
    elementos.append(Spacer(1, 2 * mm))
    return elementos


# --------------------------------------------------------------------
# Contenido
# --------------------------------------------------------------------

story: list = []

# --- Portada ---
if RUTA_LOGO.exists():
    story.append(Spacer(1, 25 * mm))
    story.append(Image(str(RUTA_LOGO), width=35 * mm, height=35 * mm, hAlign="CENTER"))
    story.append(Spacer(1, 8 * mm))
else:
    story.append(Spacer(1, 55 * mm))

story.append(Paragraph("IOS", ESTILO_PORTADA_TITULO))
story.append(Paragraph("Manual del usuario", ParagraphStyle(
    "Subtitulo2", parent=ESTILO_PORTADA_TITULO, fontSize=16, textColor=GRIS,
)))
story.append(Spacer(1, 4 * mm))
story.append(Paragraph("Insumos Oftalmológicos Santiago", ESTILO_PORTADA_SUB))
story.append(Spacer(1, 10 * mm))
story.append(Paragraph(
    "Este manual está pensado para alguien que nunca usó IOS ni un programa parecido. "
    "Explica, pantalla por pantalla, para qué sirve cada cosa y cómo se usa, con ejemplos. "
    "No hace falta leerlo de punta a punta: usá el índice (cada línea es un link, hacé clic y "
    "vas directo ahí) o el panel de marcadores del lector de PDF, a la izquierda de la "
    "ventana. Para buscar una palabra puntual (por ejemplo \"cheque\" o \"saldo a favor\"), usá "
    "el buscador del propio lector de PDF (Ctrl+F).",
    ESTILO_PORTADA_SUB,
))
story.append(PageBreak())

# --- Índice ---
indice: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("mod_conceptos", "1. Antes de empezar: palabras que vas a ver todo el tiempo", []),
    ("mod_navegacion", "2. Cómo moverte por el programa", []),
    ("mod_inicio", "3. Inicio (Dashboard)", []),
    ("mod_ventas", "4. Ventas", [
        ("pant_facturacion", "4.1 Facturación"),
        ("pant_comprobantes", "4.2 Comprobantes"),
        ("pant_cobranzas", "4.3 Cobranzas"),
        ("pant_cuenta_corriente", "4.4 Cuenta corriente"),
        ("pant_clientes", "4.5 Clientes"),
    ]),
    ("mod_compras", "5. Compras", [
        ("pant_compras_proveedores", "5.1 Compras y proveedores"),
        ("pant_pagos_proveedores", "5.2 Pagos a proveedores"),
    ]),
    ("mod_caja", "6. Caja", [
        ("pant_caja_diaria", "6.1 Caja diaria"),
        ("pant_cheques", "6.2 Cheques"),
        ("pant_gastos_caja_chica", "6.3 Gastos de caja chica"),
    ]),
    ("mod_reportes", "7. Reportes", [
        ("pant_resumen_mensual", "7.1 Resumen mensual"),
        ("pant_compras_por_cliente", "7.2 Compras por cliente"),
        ("pant_deudores", "7.3 Deudores"),
        ("pant_iva_mes", "7.4 IVA del mes"),
        ("pant_flujo_caja", "7.5 Flujo de caja"),
        ("pant_exportacion_contador", "7.6 Exportación para el contador"),
    ]),
    ("mod_herramientas", "8. Herramientas", [
        ("pant_importar_excel", "8.1 Importar desde Excel"),
        ("pant_configuracion", "8.2 Configuración"),
    ]),
    ("mod_faq", "9. Preguntas frecuentes", []),
]

story.append(Paragraph("Índice", ESTILO_MODULO))
for key_mod, texto_mod, pantallas in indice:
    story.append(toc_link(texto_mod, key_mod, ESTILO_TOC_MODULO))
    for key_pant, texto_pant in pantallas:
        story.append(toc_link(texto_pant, key_pant))
story.append(PageBreak())

# --- 1. Conceptos básicos ---
story.append(titulo_modulo("1. Antes de empezar: palabras que vas a ver todo el tiempo", "mod_conceptos"))
story.append(cuerpo(
    "IOS reemplaza la planilla de Excel que se usaba para llevar las cuentas de la "
    "distribuidora. Antes de entrar pantalla por pantalla, conviene tener claro qué significa "
    "cada palabra que el programa usa todo el tiempo — son los mismos conceptos que ya se "
    "manejaban en la planilla, solo que ahora el programa hace las cuentas solo."
))

glosario = [
    ("Cliente", "Una óptica o negocio al que se le vende. Puede tener una o varias sucursales."),
    ("Sucursal", "Una sede de un cliente. Por ejemplo, \"Croma\" y \"Croma Fdez.\" pueden ser dos "
                 "sucursales del mismo cliente \"Croma\" — cada una lleva su propio saldo, pero "
                 "las dos pertenecen al mismo cliente."),
    ("Remito (o comprobante)", "El papel de una venta: qué se le vendió a un cliente, cuándo, y "
                 "por cuánto. En IOS se carga en la pantalla Facturación."),
    ("Monto final", "Lo que el cliente realmente tiene que pagar por ese remito, después de "
                 "aplicarle el descuento (y el IVA, si corresponde). Es distinto del \"monto de "
                 "lista\", que es el precio sin descontar."),
    ("Recibo", "El papel de un cobro: el programa lo genera cuando se le registra un pago a un "
                 "cliente, en la pantalla Cobranzas. Un recibo puede cubrir uno o varios remitos "
                 "a la vez."),
    ("Saldo", "Lo que falta cobrar de un remito (o de un cliente en total). Si el saldo es $0, "
                 "ese remito ya está pagado del todo."),
    ("Saldo a favor", "Plata que el cliente pagó de más y todavía no se aplicó a ningún remito "
                 "— queda \"guardada\" para cubrir remitos futuros."),
    ("Cuenta corriente", "El resumen de todo lo que un cliente compró y pagó: cuánto debe (o "
                 "cuánto tiene a favor), con el detalle de cada remito y cada cobro."),
    ("Caja", "La plata física y en cuentas bancarias del negocio, separada por \"forma de pago\" "
                 "(Efectivo, Banco, Cheque, etc.). Se abre a la mañana y se cierra al final del "
                 "día, contando cuánto quedó de cada forma de pago."),
    ("Forma de pago", "Efectivo, transferencia bancaria, cheque... cada una se controla por "
                 "separado dentro de la caja."),
    ("Cheque en cartera", "Un cheque que un cliente entregó como pago y todavía no se cobró ni "
                 "se usó para pagarle a un proveedor — está \"guardado\", a la espera."),
    ("Proveedor", "A quien la distribuidora le compra (por ejemplo, un laboratorio de "
                 "cristales). Es la relación inversa a la de \"cliente\"."),
    ("IVA", "El impuesto que se suma (venta) o se descuenta (compra) según la tasa configurada. "
                 "El programa lo calcula solo, a partir del monto y la tasa elegida."),
]
for termino, definicion in glosario:
    story.append(Paragraph(f"{termino}:", ESTILO_GLOSARIO_TERMINO))
    story.append(cuerpo(definicion))

story.append(ejemplo(
    "La óptica \"Croma\" compra cristales por $1.000 con un 25% de descuento: el remito queda "
    "con <b>monto de lista</b> $1.000 y <b>monto final</b> $750. Si paga $750, su saldo pasa a "
    "$0. Si en cambio paga $1.000, le quedan $250 de <b>saldo a favor</b>, para usar en la "
    "próxima compra."
))

# --- 2. Navegación ---
story.append(titulo_modulo("2. Cómo moverte por el programa", "mod_navegacion"))
story.append(cuerpo(
    "Toda la app se maneja desde el menú de arriba de la ventana (como en cualquier programa "
    "de Windows: Word, Excel). No hay un menú lateral ni botones sueltos por fuera de esa "
    "barra."
))
story.extend(captura("menu_principal.png", "La ventana principal de IOS, con el menú superior abierto."))
story.append(cuerpo("El menú tiene estos grupos, cada uno con sus propias pantallas adentro:"))
story.append(lista([
    "<b>Inicio:</b> el Dashboard, el resumen general (pantalla 3 de este manual).",
    "<b>Ventas:</b> Facturación, Comprobantes, Cobranzas, Cuenta corriente, Clientes.",
    "<b>Compras:</b> Compras y proveedores, Pagos a proveedores.",
    "<b>Caja:</b> Caja diaria, Cheques, Gastos de caja chica.",
    "<b>Reportes:</b> los distintos informes para ver cómo viene el negocio.",
    "<b>Herramientas:</b> Importar desde Excel, Configuración.",
    "<b>Ayuda:</b> \"Acerca de IOS\", con la versión del programa.",
]))
story.append(cuerpo(
    "Para abrir cualquier pantalla, hacé clic en su grupo del menú y después en el nombre de "
    "la pantalla. Algunas de las más usadas tienen un atajo de teclado, que aparece al lado "
    "del nombre en el menú:"
))
story.append(Table(
    [["F2", "Facturación"], ["F3", "Cobranzas"], ["F4", "Caja diaria"], ["F5", "Cuenta corriente"]],
    colWidths=[20 * mm, 60 * mm],
    style=TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), GRIS_CLARO),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]),
))
story.append(Spacer(1, 3 * mm))
story.append(subtema("Algunas costumbres que se repiten en casi todas las pantallas"))
story.append(lista([
    "Cuando hay que elegir un cliente, casi siempre es con un <b>buscador</b> (un campo de "
    "texto con autocompletado): escribís una parte del nombre, sin importar mayúsculas ni "
    "acentos, y elegís de la lista que aparece.",
    "Las tablas casi siempre se pueden <b>editar con doble clic</b> sobre la fila.",
    "Un botón <b>\"Exportar PDF\"</b> o <b>\"Exportar Excel\"</b> abre el cuadro para guardar "
    "el archivo de Windows de siempre: ahí elegís en qué carpeta guardarlo y con qué nombre.",
    "Al cambiar de pantalla, lo que se estaba completando en un formulario (pero todavía no se "
    "guardó) se pierde — lo que ya se guardó en la base queda guardado igual, nunca se borra "
    "por cambiar de pantalla.",
]))

# --- 3. Inicio ---
story.append(titulo_modulo("3. Inicio (Dashboard)", "mod_inicio"))
story.append(cuerpo(
    "Es la primera pantalla que se ve al abrir el programa. Da una foto rápida del estado del "
    "negocio, sin tener que entrar a ningún reporte."
))
story.extend(captura("inicio.png", "Pantalla Inicio, con las tarjetas de resumen y las dos tablas de abajo."))
story.append(lista([
    "<b>Deuda total:</b> lo que deben entre todos los clientes, sumado, a hoy.",
    "<b>Venta del mes</b> y <b>Cobranza del mes</b>, comparadas con el mes anterior (para ver "
    "si se vendió/cobró más o menos que el mes pasado).",
    "<b>Total disponible:</b> cuánta plata hay en total, sumando todas las formas de pago "
    "(efectivo, bancos, etc.).",
    "<b>Caja de hoy:</b> si está \"Abierta\", \"Cerrada\" o \"Sin abrir\" — ver la sección de "
    "Caja diaria para más detalle de qué significa esto.",
    "<b>Clientes con más saldo:</b> quiénes son los que más deben en este momento.",
    "<b>Saldos por antigüedad:</b> cuánto hace que esos saldos están pendientes, agrupado por "
    "rango de días.",
]))
story.append(cuerpo("El botón \"Actualizar\" vuelve a calcular todo con los datos más recientes."))

# --- 4. Ventas ---
story.append(titulo_modulo("4. Ventas", "mod_ventas"))

story.append(titulo_pantalla("4.1 Facturación", "pant_facturacion"))
story.append(cuerpo(
    "Es la pantalla para cargar remitos (ventas) rápido. Está pensada para usarse con el "
    "teclado: apretando Enter se va pasando de un campo al siguiente, y Enter en el último "
    "campo guarda el remito — así no hace falta tocar el mouse para cargar uno tras otro."
))
story.extend(captura("facturacion.png", "Pantalla Facturación con un cliente elegido y los campos del remito."))
story.append(subtema("Cómo cargar un remito, paso a paso"))
story.append(pasos([
    "Escribí una parte del nombre del cliente en el buscador de arriba y elegilo de la lista.",
    "Si ese cliente tiene más de una sucursal, va a aparecer un campo \"Sucursal\" para elegir "
    "cuál (si solo tiene una, este campo ni aparece).",
    "Elegí el tipo de comprobante (por defecto, remito) y escribí el número.",
    "Revisá la fecha (por defecto trae la última que usaste, para no tener que escribirla cada "
    "vez).",
    "Escribí el \"Monto de lista\" (el precio sin descuento) y el porcentaje de descuento.",
    "Tildá \"Con IVA\" si ese remito lleva IVA. A medida que completás estos campos, el "
    "programa va mostrando el <b>Monto final</b> y el <b>IVA discriminado</b> ya calculados, "
    "sin que tengas que hacer la cuenta.",
    "Guardá con el botón \"Guardar\" o apretando Enter en el último campo.",
]))
story.append(cuerpo(
    "Lo que vas cargando en esa sesión aparece abajo, en la tabla \"Cargados en esta sesión\". "
    "Desde ahí podés corregir o anular algo que acabás de cargar (doble clic sobre la fila, o "
    "los botones \"Editar seleccionado\"/\"Anular seleccionado\")."
))
story.append(tip(
    "Si cargás un número de remito que ya existe <b>para el mismo cliente</b>, el programa te "
    "pide confirmar que no sea un error. Si ese número ya existe pero para <b>otro</b> "
    "cliente, solo te avisa (es normal: cada cliente numera sus remitos por su cuenta, pueden "
    "coincidir sin problema)."
))

story.append(titulo_pantalla("4.2 Comprobantes", "pant_comprobantes"))
story.append(cuerpo(
    "Es la pantalla para <b>consultar</b> remitos ya cargados — no para cargar nuevos (eso es "
    "Facturación). Sirve para buscar un remito puntual, o para revisar todo lo facturado en un "
    "período."
))
story.extend(captura("comprobantes.png", "Pantalla Comprobantes, con el filtro de fechas y la tabla de resultados."))
story.append(cuerpo("Se puede filtrar por cualquier combinación de:"))
story.append(lista([
    "Cliente (con el mismo buscador de siempre).",
    "Rango de fechas, con los atajos \"Este mes\", \"Mes anterior\" y \"Este año\" para no "
    "tener que elegir las fechas a mano.",
    "Tipo de comprobante y número (el número busca por coincidencia parcial, no hace falta "
    "escribirlo completo).",
    "Estado: Vigentes, Anulados, o Todos.",
]))
story.append(cuerpo(
    "Desde la tabla se puede editar un comprobante (doble clic) o anularlo. Si ese remito ya "
    "tiene un pago aplicado, no se puede cambiar el monto, el descuento ni el IVA — en ese "
    "caso solo se corrige el número o la fecha, o se anula directamente."
))

story.append(titulo_pantalla("4.3 Cobranzas", "pant_cobranzas"))
story.append(cuerpo(
    "Es la pantalla para registrar un cobro: elegís qué remitos cubre ese pago, y con qué "
    "forma (o formas) de pago se cobró."
))
story.extend(captura("cobranzas.png", "Pantalla Cobranzas, con remitos tildados y una forma de pago cargada."))
story.append(subtema("Cómo registrar un cobro, paso a paso"))
story.append(pasos([
    "Elegí el cliente: aparecen todos sus remitos pendientes, cada uno con su saldo.",
    "Tildá los remitos que este pago cubre (o apretá \"Seleccionar todos\" si los cubre a "
    "todos). Para cada remito tildado se puede ajustar el monto a aplicar, por si el pago no "
    "lo cubre completo.",
    "En \"Formas de pago\", apretá \"Agregar forma de pago\" y elegí con qué se cobró "
    "(efectivo, cheque, etc.) y el monto. Si es un cheque, hay que completar número, banco y "
    "fecha de cobro. Se pueden agregar varias formas de pago para un mismo cobro (por ejemplo, "
    "una parte en efectivo y otra en cheque).",
    "\"Completar con el total seleccionado\" calcula solo, en la última forma de pago que "
    "agregaste, lo que falta para llegar al total de los remitos tildados.",
    "Mirá el resumen que se actualiza solo mientras cargás: cuánto tildaste, cuánto pusiste en "
    "formas de pago, y la diferencia (si sobra, ese excedente va a quedar como saldo a favor "
    "del cliente; si falta, el programa lo avisa).",
    "Apretá \"Confirmar cobranza\". El programa genera el recibo y te pregunta si lo querés "
    "guardar en PDF.",
]))
story.append(importante(
    "Para poder cobrar, la caja de hoy tiene que estar abierta. Si está cerrada, al confirmar "
    "la cobranza aparece un aviso preguntando si querés abrirla ahí mismo — aceptá, completá "
    "la apertura (se explica en la sección de Caja diaria) y el cobro sigue su curso sin que "
    "pierdas lo que ya habías cargado."
))
story.extend(captura(
    "cobranzas_caja_cerrada.png",
    "El aviso que aparece al confirmar un cobro si la caja de hoy todavía no se abrió.",
))
story.append(cuerpo(
    "El botón \"Aplicar saldo a favor (sin caja)\" es distinto a confirmar una cobranza: usa un "
    "saldo a favor que el cliente ya tenía guardado (de un pago anterior de más), para cubrir "
    "remitos pendientes. Como no entra ni sale plata real de la caja en ese momento, no hace "
    "falta que la caja esté abierta para usarlo."
))
story.append(tip(
    "Si una cobranza se cargó con la forma de pago equivocada, <b>no</b> se corrige con una "
    "\"Transferencia interna\" de Caja diaria (eso solo mueve el total entre formas de pago "
    "dentro de la caja, pero el recibo original queda igual de mal, con el dato que no es). Lo "
    "correcto es anular el recibo (hay un botón para eso en la pantalla, sobre el recibo ya "
    "generado) y cargarlo de nuevo, bien. Anular libera los remitos que ese recibo cubría y "
    "revierte el movimiento de caja."
))

story.append(titulo_pantalla("4.4 Cuenta corriente", "pant_cuenta_corriente"))
story.append(cuerpo(
    "Muestra la cuenta corriente completa de un cliente: sus remitos y su saldo, separados por "
    "sucursal, más el saldo a favor y el total consolidado de todo el cliente."
))
story.extend(captura("cuenta_corriente.png", "Pantalla Cuenta corriente mostrando el saldo de un cliente por sucursal."))
story.append(subtema("Ver el saldo total, a hoy"))
story.append(cuerpo(
    "Es lo que se ve apenas elegís un cliente: una pestaña por sucursal con sus remitos y su "
    "saldo, y abajo el saldo a favor y el saldo consolidado del cliente completo."
))
story.append(subtema("Ver la cuenta de un mes puntual (para mandarle al cliente)"))
story.append(pasos([
    "Elegí el cliente con el buscador.",
    "Elegí un mes con el botón \"Usar mes\" — completa automáticamente las fechas Desde y "
    "Hasta de ese mes. También se puede armar un rango de fechas a mano y apretar "
    "\"Consultar\".",
    "La vista cambia: ahora, por sucursal, se ve el <b>Saldo anterior</b> (lo que venía "
    "pendiente de antes de ese período — puede ser a favor del negocio o del cliente), la "
    "lista de remitos cargados durante ese mes, y el <b>Saldo al cierre</b>.",
    "\"Ver todo\" vuelve a la vista de siempre (el saldo total a hoy, sin filtrar fechas).",
    "\"Exportar PDF\" genera el documento con lo que se está viendo en ese momento (si hay un "
    "mes elegido, exporta ese mes con su saldo anterior y su saldo al cierre).",
]))
story.append(ejemplo(
    "Croma le debía $2.000 a fin de septiembre. En octubre compró $5.000 más y pagó $4.000. Al "
    "pedir la cuenta de octubre, IOS va a mostrar: Saldo anterior $2.000, remitos de octubre "
    "por $5.000, y Saldo al cierre $3.000 ($2.000 + $5.000 − $4.000) — sin que nadie tenga que "
    "sumar el saldo de septiembre a mano."
))

story.append(titulo_pantalla("4.5 Clientes", "pant_clientes"))
story.append(cuerpo("Alta, edición y baja de clientes."))
story.extend(captura("clientes.png", "Pantalla Clientes, con la lista y el buscador/filtro de arriba."))
story.append(lista([
    "El buscador de arriba filtra por nombre, CUIT o localidad; el combo de al lado filtra por "
    "Activos / Dados de baja / Todos.",
    "\"Nuevo cliente\" y \"Editar\" abren una ventana con dos pestañas: <b>Datos</b> (nombre, "
    "CUIT, localidad, teléfono, descuento e IVA por defecto, que después se autocompletan al "
    "facturarle) y <b>Sucursales</b>.",
]))
story.extend(captura("clientes_dialogo.png", "La ventana de alta/edición de un cliente, con sus dos pestañas."))
story.append(lista([
    "El nombre no se puede repetir entre dos clientes distintos.",
    "El CUIT se valida con el dígito verificador: si está mal escrito, el programa avisa pero "
    "deja guardar igual (puede haber excepciones puntuales).",
    "\"Dar de baja\" es una baja lógica: el cliente sigue existiendo con todo su historial (sus "
    "remitos y recibos no se tocan), pero deja de aparecer para elegir cuando se carga algo "
    "nuevo. \"Reactivar\" lo revierte.",
    "Una sucursal se puede desactivar igual que un cliente, salvo que sea la única que le "
    "queda — siempre tiene que haber al menos una sucursal activa.",
]))

# --- 5. Compras ---
story.append(titulo_modulo("5. Compras", "mod_compras"))

story.append(titulo_pantalla("5.1 Compras y proveedores", "pant_compras_proveedores"))
story.append(cuerpo("Tiene tres pestañas: Proveedores, Compras y Pagos a proveedores."))
story.extend(captura("compras_proveedores.png", "Pestaña Compras, con la tasa de IVA y el monto con IVA incluido."))
story.append(lista([
    "<b>Proveedores:</b> alta con nombre y CUIT.",
    "<b>Compras:</b> se carga el <b>monto total, con el IVA ya incluido</b> (así suele venir en "
    "la factura del proveedor) — el programa calcula solo cuánto de ese monto es IVA, según la "
    "tasa elegida (21%, 10,5% o 0%). Si el IVA que calculó no coincide con el que figura en la "
    "factura real, se puede corregir a mano escribiéndolo directamente: esa fila queda marcada "
    "\"(manual)\" en la tabla, para saber que ese valor no es el que calculó el programa solo.",
]))

story.append(titulo_pantalla("5.2 Pagos a proveedores", "pant_pagos_proveedores"))
story.append(cuerpo(
    "Es la misma pantalla de \"Compras y proveedores\", abierta directamente en la pestaña de "
    "pagos (el menú tiene las dos entradas para llegar más rápido a cada una)."
))
story.extend(captura("pagos_proveedores.png", "Pestaña Pagos a proveedores, con un pago hecho con cheque en cartera."))
story.append(cuerpo(
    "Registrar un pago genera un egreso en la caja. Si se elige \"Cheque\" como forma de pago, "
    "se puede usar directamente un cheque que un cliente haya entregado y que todavía esté en "
    "cartera, en vez de pagarle al proveedor con efectivo o transferencia."
))

# --- 6. Caja ---
story.append(titulo_modulo("6. Caja", "mod_caja"))

story.append(titulo_pantalla("6.1 Caja diaria", "pant_caja_diaria"))
story.append(cuerpo(
    "Es donde se abre y se cierra la caja de cada día, y donde se cargan los movimientos que "
    "no son ni ventas ni compras: gastos, retiros, aportes y transferencias entre formas de "
    "pago."
))
story.extend(captura("caja_diaria.png", "Pestaña \"Hoy\" de Caja diaria, con el estado de la caja y sus movimientos."))
story.append(subtema("Abrir la caja"))
story.append(cuerpo(
    "Al principio del día (o cuando haga falta cobrar y la caja todavía esté cerrada), se "
    "abre con el botón \"Abrir caja de hoy\". El programa propone, para cada forma de pago, el "
    "saldo con el que cerró el día anterior."
))
story.extend(captura("abrir_caja.png", "La ventana para abrir la caja, con el saldo propuesto de cada forma de pago."))
story.append(cuerpo(
    "Ese saldo propuesto se puede corregir (por ejemplo, si se contó mal el efectivo el día "
    "anterior) — pero si se corrige, hay que escribir una nota explicando por qué, para que "
    "quede el motivo registrado."
))
story.append(subtema("Durante el día"))
story.append(lista([
    "<b>Gasto / retiro / aporte:</b> un movimiento manual de ingreso o egreso que no es ni "
    "venta ni compra — por ejemplo, un gasto de librería o un retiro del dueño. Se le puede "
    "poner una categoría y un concepto.",
    "<b>Transferencia interna:</b> mueve plata de una forma de pago a otra, dentro de la misma "
    "caja — por ejemplo, depositar el efectivo cobrado en el banco. El total disponible del "
    "negocio no cambia; lo único que cambia es en qué forma de pago está guardada esa plata.",
]))
story.append(subtema("Cerrar la caja"))
story.append(cuerpo(
    "Para cada forma de pago con movimientos ese día, el programa ya calculó el saldo teórico "
    "(saldo inicial + ingresos − egresos). Ahí se escribe el <b>arqueo</b>: lo que se contó "
    "físicamente de verdad (el efectivo en el cajón, por ejemplo). Si el arqueo no coincide con "
    "el teórico, hace falta una nota explicando la diferencia."
))
story.append(importante(
    "Si un día se olvida cerrar, el programa lo cierra solo la próxima vez que se abre el "
    "programa o se intenta cobrar — usando el saldo teórico como arqueo (sin diferencia, sin "
    "pedir nada). Esto evita que una caja vieja quede \"abierta\" para siempre, mezclada con la "
    "de días posteriores."
))
story.append(cuerpo(
    "La pestaña \"Historial de cierres\" muestra todos los días ya cerrados; al seleccionar uno "
    "se ve el detalle completo por forma de pago (saldo inicial, ingresos, egresos, saldo "
    "teórico y diferencia)."
))

story.append(titulo_pantalla("6.2 Cheques", "pant_cheques"))
story.append(cuerpo(
    "Muestra los cheques de clientes que están en cartera (ya recibidos, pero todavía sin "
    "cobrar ni usar para pagarle a un proveedor), ordenados por fecha de cobro."
))
story.extend(captura("cheques.png", "Pantalla Cheques, con la lista de cheques en cartera."))
story.append(lista([
    "<b>Cobrar seleccionado:</b> lo deposita en la forma de pago de banco que se elija.",
    "<b>Rechazar seleccionado:</b> lo marca como rechazado (por ejemplo, si rebotó).",
    "Para entregárselo a un proveedor como forma de pago, se hace desde \"Compras y "
    "proveedores\" → Pagos, no desde esta pantalla.",
]))

story.append(titulo_pantalla("6.3 Gastos de caja chica", "pant_gastos_caja_chica"))
story.append(cuerpo(
    "Un reporte de los gastos y retiros manuales de caja (los que se cargan en Caja diaria "
    "como \"Gasto / retiro\"), filtrado por fecha y agrupado por categoría. Se puede exportar a "
    "PDF o Excel."
))
story.extend(captura("gastos_caja_chica.png", "Pantalla Gastos de caja chica, con el total por categoría."))

# --- 7. Reportes ---
story.append(titulo_modulo("7. Reportes", "mod_reportes"))
story.append(cuerpo(
    "Todos los reportes de este módulo son solo de <b>consulta</b>: no se carga nada nuevo "
    "acá, solo se mira lo que ya está cargado en otras pantallas, de distintas formas."
))

story.append(titulo_pantalla("7.1 Resumen mensual", "pant_resumen_mensual"))
story.append(cuerpo(
    "El resumen completo de un mes: venta, cobranza, saldos, IVA, comisión, compras, "
    "depósitos, ganancia teórica y total disponible."
))
story.extend(captura("resumen_mensual.png", "Pestaña Resumen de Resumen mensual."))
story.append(cuerpo(
    "Tiene una pestaña \"Gráficos\" con cinco gráficos de los últimos 12 meses: venta vs. "
    "cobranza, deuda total, top 10 clientes, IVA venta vs. compra, y egresos por categoría."
))
story.extend(captura("resumen_mensual_graficos.png", "Pestaña Gráficos de Resumen mensual."))
story.append(cuerpo("Se exporta a PDF o Excel."))

story.append(titulo_pantalla("7.2 Compras por cliente", "pant_compras_por_cliente"))
story.append(cuerpo(
    "Cuánto compró un cliente en un período (con subtotal por sucursal); si no se elige ningún "
    "cliente en particular, muestra un ranking de todos los clientes de ese período. Se "
    "exporta a PDF o Excel."
))
story.extend(captura("compras_por_cliente.png", "Pantalla Compras por cliente."))

story.append(titulo_pantalla("7.3 Deudores", "pant_deudores"))
story.append(cuerpo(
    "Lista de clientes con saldo pendiente a una fecha, de mayor a menor, con la fecha y la "
    "antigüedad (en días) del remito más viejo todavía sin cobrar. Se exporta a PDF o Excel."
))
story.extend(captura("deudores.png", "Pantalla Deudores."))

story.append(titulo_pantalla("7.4 IVA del mes", "pant_iva_mes"))
story.append(cuerpo(
    "IVA venta, IVA compra, y la diferencia entre los dos, de un mes — con el detalle de los "
    "remitos y las facturas de compra que lo componen. Se exporta a Excel."
))
story.extend(captura("iva_mes.png", "Pantalla IVA del mes."))

story.append(titulo_pantalla("7.5 Flujo de caja", "pant_flujo_caja"))
story.append(cuerpo(
    "Ingresos y egresos día por día en un período, con el saldo de cada día y el saldo "
    "acumulado. Se exporta a Excel."
))
story.extend(captura("flujo_caja.png", "Pantalla Flujo de caja."))

story.append(titulo_pantalla("7.6 Exportación para el contador", "pant_exportacion_contador"))
story.append(cuerpo(
    "Genera un solo Excel con una hoja separada para comprobantes, recibos, compras y "
    "movimientos de caja de un período — pensado para mandárselo directo al contador, sin que "
    "tenga que entrar a usar el programa."
))
story.extend(captura("exportacion_contador.png", "Pantalla Exportación para el contador."))

# --- 8. Herramientas ---
story.append(titulo_modulo("8. Herramientas", "mod_herramientas"))

story.append(titulo_pantalla("8.1 Importar desde Excel", "pant_importar_excel"))
story.append(cuerpo(
    "Sirve para traer a IOS los datos de la planilla de Excel que se usaba antes de tener el "
    "programa, hoja por hoja (cada hoja suele ser un cliente o una sucursal). Es para la "
    "carga inicial o para poner al día un mes que se llevó en la planilla vieja — no es algo "
    "que se use todos los días."
))
story.extend(captura("importar_excel.png", "Pantalla Importar desde Excel, con la vista previa y los conflictos detectados."))
story.append(pasos([
    "Elegí el archivo de Excel y el mes, y apretá para leerlo: aparece una vista previa con lo "
    "que se va a importar.",
    "Si el archivo tiene algo dudoso (un remito repetido, un IVA que no coincide con el "
    "calculado, un pago suelto sin remito, un recibo repartido entre dos hojas, un recibo con "
    "texto en vez de un monto, o una hoja que parece ser una sucursal de un cliente ya "
    "cargado), aparece listado como un <b>conflicto</b>, con una acción sugerida que se puede "
    "cambiar antes de confirmar.",
    "Se puede filtrar los conflictos por tipo, y aplicar la acción sugerida a todos los de un "
    "mismo tipo de una sola vez, en vez de revisarlos uno por uno.",
    "Al confirmar, todo se guarda junto: si algo falla, no queda nada cargado a medias. Se "
    "puede exportar un resumen a Excel con la decisión que se tomó en cada conflicto, para "
    "tener registro.",
]))

story.append(titulo_pantalla("8.2 Configuración", "pant_configuracion"))
story.append(cuerpo("Parámetros y listas que usa el resto del programa, en varias pestañas:"))
story.extend(captura("configuracion.png", "Pestaña General de Configuración."))
story.append(lista([
    "<b>General:</b> porcentaje de IVA, porcentaje de comisión, número inicial de recibo, y "
    "cantidad de decimales de redondeo.",
    "<b>Tipos de comprobante, Formas de pago, Categorías de caja:</b> las listas que después "
    "aparecen en los combos de otras pantallas; desde acá se les pueden agregar valores "
    "nuevos.",
    "<b>Mantenimiento:</b> la instalación limpia, explicada abajo.",
]))
story.append(subtema("Instalación limpia (reiniciar la base de datos)"))
story.append(cuerpo(
    "Si hace falta arrancar de cero — por ejemplo, para empezar a usar el programa en serio "
    "después de haber hecho pruebas con datos inventados — esta opción borra todos los datos "
    "actuales: clientes, remitos, cobros, compras y caja."
))
story.extend(captura("configuracion_mantenimiento.png", "Pestaña Mantenimiento, con el botón de reiniciar la base de datos."))
story.append(importante(
    "Antes de borrar nada, la base actual queda guardada como respaldo (un archivo con la "
    "fecha y hora, en la misma carpeta de datos del programa), por si hace falta volver atrás. "
    "Para confirmar, hay que escribir la palabra <b>BORRAR</b> tal cual — si se escribe "
    "cualquier otra cosa, no se toca absolutamente nada. Después de confirmar, el programa se "
    "cierra solo; al volver a abrirlo, arranca con la base vacía."
))

# --- 9. Preguntas frecuentes ---
story.append(titulo_modulo("9. Preguntas frecuentes", "mod_faq"))

preguntas = [
    (
        "Nunca usé un programa así, ¿por dónde empiezo?",
        "Por la sección 2 de este manual (\"Cómo moverte por el programa\"), y después por "
        "Clientes (dar de alta a quién le vas a vender) y Facturación (cargar la primera "
        "venta). El resto se va usando a medida que hace falta.",
    ),
    (
        "\"La caja de hoy está cerrada\" al querer cobrar, ¿qué hago?",
        "Es normal: para cobrar, la caja de hoy tiene que estar abierta. El mismo aviso te "
        "ofrece abrirla ahí mismo — aceptá y seguís con el cobro sin perder lo que ya habías "
        "cargado.",
    ),
    (
        "Cargué un cobro con la forma de pago equivocada, ¿cómo lo arreglo?",
        "Anulá el recibo (desde Cobranzas) y volvé a cargarlo con la forma de pago correcta. "
        "Una \"Transferencia interna\" en Caja diaria NO corrige esto: solo mueve el total "
        "entre formas de pago, pero el recibo original queda igual de mal.",
    ),
    (
        "¿Por qué un remito no tiene un estado \"Pagado\"?",
        "Porque no existe ese estado: un remito solo puede estar \"Vigente\" o \"Anulado\". Si "
        "está pagado o no, se ve por el <b>saldo</b> (monto final menos lo que se le aplicó de "
        "recibos): saldo en $0 significa pagado, saldo mayor a $0 significa que falta cobrar.",
    ),
    (
        "Quiero la cuenta corriente de un cliente de un mes puntual, para mandarle",
        "En Cuenta corriente, elegí el cliente, usá \"Usar mes\" (o armá un rango de fechas) y "
        "\"Consultar\". Vas a ver el saldo anterior, los movimientos de ese mes y el saldo al "
        "cierre. Exportalo con \"Exportar PDF\".",
    ),
    (
        "Un cliente tenía saldo pendiente el mes pasado, ¿hay que sumarlo a mano este mes?",
        "No: en Cuenta corriente, al elegir un mes, el saldo que quedó pendiente antes de ese "
        "período aparece solo como \"Saldo anterior\", arrastrado automáticamente.",
    ),
    (
        "¿Cómo pruebo el programa sin arruinar los datos reales?",
        "Cargá los datos de prueba con cuidado y, cuando termines, usá Configuración → "
        "Mantenimiento → Reiniciar base de datos para volver a empezar de cero (igual queda "
        "guardado un respaldo, por si acaso).",
    ),
    (
        "¿Dónde quedan los PDF y Excel que exporto?",
        "Donde elijas al guardarlos: cada pantalla con un botón \"Exportar\" abre el cuadro de "
        "diálogo normal de Windows para guardar un archivo, para que elijas la carpeta.",
    ),
]

for pregunta, respuesta in preguntas:
    story.append(subtema(pregunta))
    story.append(cuerpo(respuesta))

story.append(Spacer(1, 10 * mm))
story.append(HRFlowable(width="100%", color=colors.lightgrey))
story.append(Spacer(1, 2 * mm))
story.append(Paragraph(
    "Fin del manual. Ante cualquier duda que no esté acá, consultá a quien mantiene el "
    "programa en tu negocio.", ESTILO_PIE,
))


# --------------------------------------------------------------------
# Construcción del documento
# --------------------------------------------------------------------

def generar() -> Path:
    doc = DocumentoConMarcadores(
        str(RUTA_SALIDA), pagesize=A4,
        topMargin=18 * mm, bottomMargin=18 * mm, leftMargin=18 * mm, rightMargin=18 * mm,
        title="IOS - Manual del usuario",
    )
    marco = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="todas", frames=[marco], onPage=pie_de_pagina)])
    doc.build(story)
    return RUTA_SALIDA


if __name__ == "__main__":
    ruta = generar()
    print(f"Generado: {ruta} ({ruta.stat().st_size} bytes)")
