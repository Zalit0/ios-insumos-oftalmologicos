"""Importación opcional desde Excel (docs/PLAN.md, etapa 9).

Dos pasos separados:

- ``leer_archivo``: solo lee la planilla y arma una vista previa (altas,
  remitos, pagos y anomalías). No toca la base de datos.
- ``confirmar_importacion``: guarda la vista previa en una sola
  transacción; si algo falla, no queda nada a medias.

La app lee los valores guardados de la planilla, no las fórmulas, así que
una fila con un IVA mal cargado (por ejemplo) se importa tal cual está y
se avisa como anomalía, en vez de corregirse sola.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import openpyxl

from ios.data import clientes as datos_clientes
from ios.data import comprobantes as datos_comprobantes
from ios.data import configuracion as datos_configuracion
from ios.data import formas_pago as datos_formas_pago
from ios.data import recibos as datos_recibos
from ios.data import tipos_comprobante as datos_tipos_comprobante
from ios.domain.calculos import cuantizar
from ios.domain.texto import normalizar

HOJAS_IGNORADAS = {"TOTALES", "COMPRAS"}
PREFIJOS_IGNORADOS = ("VACIO",)

# Columnas de cada hoja de cliente, siempre en el mismo orden aunque el
# texto del encabezado varíe (NUM./COMPROBANTE/NRO, DESC./DESCUENTO, etc.)
COL_FECHA = 2
COL_TIPO = 3
COL_NUMERO = 4
COL_MONTO = 5
COL_DESCUENTO = 6
COL_FINAL = 7
COL_IVA_SI_NO = 8
COL_IVA_MONTO = 9
COL_PAGO_MONTO = 10
COL_RECIBO = 11
COL_FECHA_PAGO = 12
COL_SALDOS = 13
COL_NOMBRE_PARTICULAR = 14

TASA_IVA_HISTORICA = Decimal("21")  # la anomalía se mide contra "final × 21/121", fijo
TOLERANCIA_IVA = Decimal("0.5")

FORMA_PAGO_IMPORTADO = "Importado"

# docs/AJUSTES_V1.1.md, etapa 7: una acción por conflicto, con una
# sugerida; el texto de cada opción es el mismo que ve el usuario en la
# pantalla de importación.
OPCION_REMITO_IMPORTAR_AMBOS = "Importar ambos"
OPCION_REMITO_OMITIR = "Omitir este"

OPCION_IVA_RECALCULADO = "Usar IVA recalculado"
OPCION_IVA_DEL_EXCEL = "Conservar el del Excel"

OPCION_PAGO_SALDO_A_FAVOR = "Registrar como saldo a favor"
OPCION_PAGO_OMITIR = "Omitir"

OPCION_RECIBO_RENUMERAR = "Renumerar el segundo"
OPCION_RECIBO_UNIFICAR = "Unificar en un recibo"

OPCION_TEXTO_AUTOMATICO = "Número automático y el texto como referencia"
OPCION_TEXTO_OMITIR = "Omitir el pago"

OPCION_SUCURSAL_CLIENTE_NUEVO = "Como cliente nuevo"


@dataclass
class RemitoImportado:
    numero_original: str
    tipo_abreviatura: str
    fecha: str
    monto_lista: Decimal
    descuento_pct: Decimal
    monto_final: Decimal
    con_iva: bool
    iva_discriminado: Decimal
    iva_recalculado: Decimal
    nombre_particular: str | None
    fila: int


@dataclass
class ReciboImportado:
    clave: tuple
    numero_original: int | None
    texto_original: str | None
    fecha: str
    aplicaciones: list[tuple[str, Decimal]] = field(default_factory=list)
    filas: list[int] = field(default_factory=list)
    monto_suelto: Decimal = Decimal(0)  # pago sin remito asociado (queda como saldo a favor)


@dataclass
class Anomalia:
    tipo: str
    hoja: str
    descripcion: str
    fila: int | None = None


@dataclass
class Conflicto:
    """Una anomalía que necesita que el usuario decida qué hacer
    (docs/AJUSTES_V1.1.md, etapa 7). ``id`` es estable entre lecturas del
    mismo archivo: se usa como clave en ``decisiones`` al confirmar.
    ``opciones`` son los textos exactos que ve el usuario; ``sugerida`` es
    uno de ellos."""

    id: str
    tipo: str
    hoja: str
    fila: int | None
    descripcion: str
    opciones: list[str]
    sugerida: str
    datos: dict = field(default_factory=dict)


@dataclass
class HojaImportada:
    hoja: str
    nombre_cliente: str
    descuento_default: Decimal
    con_iva_default: bool
    remitos: list[RemitoImportado]
    recibos: list[ReciboImportado]


@dataclass
class VistaPreviaImportacion:
    mes: str
    hojas: list[HojaImportada]
    anomalias: list[Anomalia]
    conflictos: list[Conflicto] = field(default_factory=list)


def _es_hoja_ignorada(nombre: str) -> bool:
    nombre_mayus = nombre.strip().upper()
    if nombre_mayus in HOJAS_IGNORADAS:
        return True
    return any(nombre_mayus.startswith(prefijo) for prefijo in PREFIJOS_IGNORADOS)


def _buscar_fila_encabezado(ws) -> int | None:
    for fila in range(1, 11):
        if ws.cell(row=fila, column=COL_FECHA).value == "FECHA":
            return fila
    return None


def _a_decimal(valor) -> Decimal:
    return Decimal(str(valor))


def _a_fecha_iso(valor) -> str:
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    raise ValueError(f"Fecha inválida en la planilla: {valor!r}")


def leer_archivo(ruta: Path | str, mes: str, decimales: int = 2) -> VistaPreviaImportacion:
    """Lee el archivo .xlsx y arma la vista previa. No escribe nada en la
    base; ``mes`` ('YYYY-MM') solo se usa como fecha de respaldo cuando un
    pago suelto no tiene fecha."""
    libro = openpyxl.load_workbook(str(ruta), data_only=True)

    hojas: list[HojaImportada] = []
    anomalias: list[Anomalia] = []
    conflictos: list[Conflicto] = []
    remitos_vistos_global: dict[str, list[str]] = {}
    recibos_numericos_global: dict[int, list[str]] = {}

    for nombre_hoja in libro.sheetnames:
        if _es_hoja_ignorada(nombre_hoja):
            continue

        ws = libro[nombre_hoja]
        fila_encabezado = _buscar_fila_encabezado(ws)
        if fila_encabezado is None:
            continue

        remitos: list[RemitoImportado] = []
        grupos_recibo: dict[tuple, ReciboImportado] = {}
        apariciones_en_hoja: dict[str, int] = {}

        for fila in range(fila_encabezado + 1, ws.max_row + 1):
            (
                fecha, tipo, numero, monto, descuento, final, iva_si_no, iva_monto,
                pago_monto, recibo, fecha_pago, saldos, nombre_particular,
            ) = (ws.cell(row=fila, column=c).value for c in range(COL_FECHA, COL_NOMBRE_PARTICULAR + 1))

            es_remito = fecha is not None and numero is not None
            numero_original = str(numero).strip() if es_remito else None

            if es_remito:
                apariciones_en_hoja[numero_original] = apariciones_en_hoja.get(numero_original, 0) + 1
                if apariciones_en_hoja[numero_original] > 1:
                    anomalias.append(Anomalia(
                        "remito_repetido", nombre_hoja,
                        f"El remito {numero_original} aparece más de una vez en esta hoja.",
                        fila,
                    ))
                    conflictos.append(Conflicto(
                        id=f"remito_repetido:{nombre_hoja}:{fila}",
                        tipo="remito_repetido",
                        hoja=nombre_hoja,
                        fila=fila,
                        descripcion=f"El remito {numero_original} aparece más de una vez en esta hoja.",
                        opciones=[OPCION_REMITO_IMPORTAR_AMBOS, OPCION_REMITO_OMITIR],
                        sugerida=OPCION_REMITO_IMPORTAR_AMBOS,
                    ))
                remitos_vistos_global.setdefault(numero_original, []).append(nombre_hoja)

                con_iva = iva_si_no == "SI"
                monto_lista_dec = cuantizar(_a_decimal(monto), decimales)
                descuento_dec = _a_decimal(descuento) if descuento is not None else Decimal(0)
                final_dec = cuantizar(_a_decimal(final), decimales)
                iva_dec = cuantizar(_a_decimal(iva_monto) if iva_monto is not None else Decimal(0), decimales)

                esperado = (
                    cuantizar(final_dec * TASA_IVA_HISTORICA / (Decimal(100) + TASA_IVA_HISTORICA), decimales)
                    if con_iva else Decimal(0)
                )
                if abs(iva_dec - esperado) > TOLERANCIA_IVA:
                    anomalias.append(Anomalia(
                        "iva_no_coincide", nombre_hoja,
                        f"El remito {numero_original} tiene IVA {iva_dec} pero final × 21/121 "
                        f"da {esperado}.",
                        fila,
                    ))
                    conflictos.append(Conflicto(
                        id=f"iva_no_coincide:{nombre_hoja}:{fila}",
                        tipo="iva_no_coincide",
                        hoja=nombre_hoja,
                        fila=fila,
                        descripcion=(
                            f"El remito {numero_original} tiene IVA {iva_dec} pero final × "
                            f"21/121 da {esperado}."
                        ),
                        opciones=[OPCION_IVA_RECALCULADO, OPCION_IVA_DEL_EXCEL],
                        sugerida=OPCION_IVA_RECALCULADO,
                    ))

                remitos.append(RemitoImportado(
                    numero_original=numero_original,
                    tipo_abreviatura=str(tipo).strip() if tipo else "RTO",
                    fecha=_a_fecha_iso(fecha),
                    monto_lista=monto_lista_dec,
                    descuento_pct=descuento_dec,
                    monto_final=final_dec,
                    con_iva=con_iva,
                    iva_discriminado=iva_dec,
                    iva_recalculado=esperado,
                    nombre_particular=(str(nombre_particular).strip() if nombre_particular else None),
                    fila=fila,
                ))

            if pago_monto is None:
                continue

            monto_pago_dec = cuantizar(_a_decimal(pago_monto), decimales)

            if not es_remito:
                anomalias.append(Anomalia(
                    "pago_suelto", nombre_hoja,
                    f"Hay un pago de {monto_pago_dec} sin remito asociado en esta fila.",
                    fila,
                ))
                conflictos.append(Conflicto(
                    id=f"pago_suelto:{nombre_hoja}:{fila}",
                    tipo="pago_suelto",
                    hoja=nombre_hoja,
                    fila=fila,
                    descripcion=f"Hay un pago de {monto_pago_dec} sin remito asociado en esta fila.",
                    opciones=[OPCION_PAGO_SALDO_A_FAVOR, OPCION_PAGO_OMITIR],
                    sugerida=OPCION_PAGO_SALDO_A_FAVOR,
                ))
                if fecha_pago is None:
                    anomalias.append(Anomalia(
                        "pago_sin_fecha", nombre_hoja,
                        "El pago suelto no tiene fecha; se usó el primer día del mes.",
                        fila,
                    ))
                # El pago suelto no cubre ningún remito: queda íntegro como
                # saldo a favor del cliente (sin aplicaciones).
                clave = ("fila", nombre_hoja, fila)
                grupos_recibo[clave] = ReciboImportado(
                    clave=clave,
                    numero_original=None,
                    texto_original=None,
                    fecha=_a_fecha_iso(fecha_pago) if fecha_pago is not None else f"{mes}-01",
                    monto_suelto=monto_pago_dec,
                )
                grupos_recibo[clave].filas.append(fila)
                continue

            if isinstance(recibo, (int, float)):
                numero_recibo = int(recibo)
                clave = ("numero", numero_recibo)
                recibos_numericos_global.setdefault(numero_recibo, []).append(nombre_hoja)
                texto_original = None
            elif recibo is None:
                clave = ("fila", nombre_hoja, fila)
                numero_recibo = None
                texto_original = None
                anomalias.append(Anomalia(
                    "pago_sin_numero_de_recibo", nombre_hoja,
                    f"El remito {numero_original} está pagado pero no tiene número de recibo.",
                    fila,
                ))
            else:
                clave = ("fila", nombre_hoja, fila)
                numero_recibo = None
                texto_original = str(recibo).strip()
                anomalias.append(Anomalia(
                    "recibo_con_texto", nombre_hoja,
                    f"El recibo del remito {numero_original} tiene un número no numérico: "
                    f"'{texto_original}'.",
                    fila,
                ))
                conflictos.append(Conflicto(
                    id=f"recibo_con_texto:{nombre_hoja}:{fila}",
                    tipo="recibo_con_texto",
                    hoja=nombre_hoja,
                    fila=fila,
                    descripcion=(
                        f"El recibo del remito {numero_original} tiene un número no numérico: "
                        f"'{texto_original}'."
                    ),
                    opciones=[OPCION_TEXTO_AUTOMATICO, OPCION_TEXTO_OMITIR],
                    sugerida=OPCION_TEXTO_AUTOMATICO,
                ))

            if clave not in grupos_recibo:
                grupos_recibo[clave] = ReciboImportado(
                    clave=clave,
                    numero_original=numero_recibo,
                    texto_original=texto_original,
                    fecha=(
                        _a_fecha_iso(fecha_pago) if fecha_pago is not None else _a_fecha_iso(fecha)
                    ),
                )
            grupos_recibo[clave].aplicaciones.append((numero_original, monto_pago_dec))
            grupos_recibo[clave].filas.append(fila)

        if not remitos and not grupos_recibo:
            continue  # hoja sin movimientos: no crea cliente

        primer_remito = remitos[0] if remitos else None
        nombre_cliente = str(ws.cell(row=1, column=2).value or nombre_hoja).strip()

        hojas.append(HojaImportada(
            hoja=nombre_hoja,
            nombre_cliente=nombre_cliente,
            descuento_default=(primer_remito.descuento_pct if primer_remito else Decimal(0)),
            con_iva_default=(primer_remito.con_iva if primer_remito else False),
            remitos=remitos,
            recibos=list(grupos_recibo.values()),
        ))

    for numero_original, hojas_vistas in remitos_vistos_global.items():
        distintas = sorted(set(hojas_vistas))
        if len(distintas) > 1:
            anomalias.append(Anomalia(
                "remito_repetido_entre_hojas", ", ".join(distintas),
                f"El remito {numero_original} aparece en más de una hoja: {', '.join(distintas)}.",
            ))

    for numero_recibo, hojas_vistas in recibos_numericos_global.items():
        distintas = sorted(set(hojas_vistas))
        if len(distintas) > 1:
            anomalias.append(Anomalia(
                "recibo_compartido_entre_hojas", ", ".join(distintas),
                f"El recibo {numero_recibo} aparece en más de una hoja ({', '.join(distintas)}); "
                f"se importa como un recibo distinto por hoja, ya que un recibo es de un solo cliente.",
            ))
            conflictos.append(Conflicto(
                id=f"recibo_compartido:{numero_recibo}",
                tipo="recibo_compartido",
                hoja=", ".join(distintas),
                fila=None,
                descripcion=(
                    f"El recibo {numero_recibo} aparece en más de una hoja "
                    f"({', '.join(distintas)})."
                ),
                opciones=[OPCION_RECIBO_RENUMERAR, OPCION_RECIBO_UNIFICAR],
                sugerida=OPCION_RECIBO_RENUMERAR,
                datos={"numero_recibo": numero_recibo},
            ))

    conflictos.extend(_detectar_posibles_sucursales(hojas))

    return VistaPreviaImportacion(mes=mes, hojas=hojas, anomalias=anomalias, conflictos=conflictos)


def _detectar_posibles_sucursales(hojas: list[HojaImportada]) -> list[Conflicto]:
    """Una hoja "parece sucursal" de otra cuando su nombre empieza igual,
    como "CROMA FDEZ." frente a "CROMA" (docs/AJUSTES_V1.1.md, etapa 7).
    Solo una sugerencia: no cambia nada hasta que se confirma."""
    conflictos = []
    for hoja in hojas:
        nombre_norm = normalizar(hoja.nombre_cliente)
        mejor_padre: HojaImportada | None = None
        for otra in hojas:
            if otra is hoja:
                continue
            otro_norm = normalizar(otra.nombre_cliente)
            if len(otro_norm) < 3 or otro_norm == nombre_norm:
                continue
            if not nombre_norm.startswith(otro_norm):
                continue
            # Límite de palabra: "CROMADOS" no es sucursal de "CROMA".
            if nombre_norm[len(otro_norm):len(otro_norm) + 1] not in (" ", ".", "-"):
                continue
            if mejor_padre is None or len(otro_norm) > len(normalizar(mejor_padre.nombre_cliente)):
                mejor_padre = otra

        if mejor_padre is None:
            continue

        opcion_sucursal = f"Importar como sucursal de {mejor_padre.hoja}"
        conflictos.append(Conflicto(
            id=f"posible_sucursal:{hoja.hoja}",
            tipo="posible_sucursal",
            hoja=hoja.hoja,
            fila=None,
            descripcion=f"La hoja '{hoja.hoja}' parece una sucursal de '{mejor_padre.hoja}' por el nombre.",
            opciones=[opcion_sucursal, OPCION_SUCURSAL_CLIENTE_NUEVO],
            sugerida=opcion_sucursal,
            datos={"hoja_padre_sugerida": mejor_padre.hoja},
        ))
    return conflictos


def _obtener_o_crear_tipo_comprobante(conexion: sqlite3.Connection, abreviatura: str) -> int:
    fila = conexion.execute(
        "SELECT id FROM tipos_comprobante WHERE abreviatura = ?", (abreviatura,)
    ).fetchone()
    if fila is not None:
        return fila["id"]
    return datos_tipos_comprobante.insertar_tipo_comprobante(conexion, abreviatura, abreviatura)


def _obtener_o_crear_forma_pago_importado(conexion: sqlite3.Connection) -> int:
    fila = datos_formas_pago.obtener_forma_pago_por_nombre(conexion, FORMA_PAGO_IMPORTADO)
    if fila is not None:
        return fila["id"]
    return datos_formas_pago.insertar_forma_pago(conexion, FORMA_PAGO_IMPORTADO, "otro")


def confirmar_importacion(
    conexion: sqlite3.Connection,
    vista_previa: VistaPreviaImportacion,
    asignaciones_sucursal: dict[str, str] | None = None,
    decisiones: dict[str, str] | None = None,
) -> dict:
    """Guarda la vista previa en una sola transacción: si algo falla, no
    queda nada a medias. ``asignaciones_sucursal`` mapea el nombre de una
    hoja a la hoja "padre" de la que pasa a ser sucursal (ej. "CROMA FDEZ."
    -> "CROMA"). ``decisiones`` mapea el ``id`` de cada conflicto a la
    opción elegida (docs/AJUSTES_V1.1.md, etapa 7); un conflicto sin
    decisión explícita usa su opción sugerida, salvo "posible_sucursal"
    (reestructura clientes, así que solo se aplica si se decidió a mano).
    """
    asignaciones_sucursal = dict(asignaciones_sucursal or {})
    decisiones = decisiones or {}

    for conflicto in vista_previa.conflictos:
        if conflicto.tipo != "posible_sucursal" or conflicto.hoja in asignaciones_sucursal:
            continue
        if decisiones.get(conflicto.id) == conflicto.sugerida:
            asignaciones_sucursal[conflicto.hoja] = conflicto.datos["hoja_padre_sugerida"]

    omitir_remitos = {
        (c.hoja, c.fila) for c in vista_previa.conflictos
        if c.tipo == "remito_repetido" and decisiones.get(c.id, c.sugerida) == OPCION_REMITO_OMITIR
    }
    recalcular_iva = {
        (c.hoja, c.fila) for c in vista_previa.conflictos
        if c.tipo == "iva_no_coincide" and decisiones.get(c.id, c.sugerida) == OPCION_IVA_RECALCULADO
    }
    omitir_recibo_claves: set[tuple] = set()
    for c in vista_previa.conflictos:
        if c.tipo == "pago_suelto" and decisiones.get(c.id, c.sugerida) == OPCION_PAGO_OMITIR:
            omitir_recibo_claves.add(("fila", c.hoja, c.fila))
        elif c.tipo == "recibo_con_texto" and decisiones.get(c.id, c.sugerida) == OPCION_TEXTO_OMITIR:
            omitir_recibo_claves.add(("fila", c.hoja, c.fila))
    numeros_a_unificar = {
        c.datos["numero_recibo"] for c in vista_previa.conflictos
        if c.tipo == "recibo_compartido" and decisiones.get(c.id, c.sugerida) == OPCION_RECIBO_UNIFICAR
    }

    try:
        forma_pago_importado_id = _obtener_o_crear_forma_pago_importado(conexion)

        cliente_id_por_hoja: dict[str, int] = {}
        sucursal_id_por_hoja: dict[str, int] = {}
        clientes_creados = 0

        orden = [h for h in vista_previa.hojas if h.hoja not in asignaciones_sucursal]
        orden += [h for h in vista_previa.hojas if h.hoja in asignaciones_sucursal]

        for hoja in orden:
            if hoja.hoja in asignaciones_sucursal:
                hoja_padre = asignaciones_sucursal[hoja.hoja]
                if hoja_padre not in cliente_id_por_hoja:
                    raise ValueError(
                        f"La hoja '{hoja_padre}' (asignada como padre de '{hoja.hoja}') "
                        f"no está en la vista previa."
                    )
                cliente_id = cliente_id_por_hoja[hoja_padre]
                sucursal_existente = datos_clientes.obtener_sucursal_por_nombre(
                    conexion, cliente_id, hoja.nombre_cliente
                )
                sucursal_id = (
                    sucursal_existente["id"] if sucursal_existente is not None
                    else datos_clientes.insertar_sucursal(conexion, cliente_id, hoja.nombre_cliente)
                )
            else:
                existente = datos_clientes.obtener_cliente_por_nombre(conexion, hoja.nombre_cliente)
                if existente is not None:
                    cliente_id = existente["id"]
                    sucursal_id = datos_clientes.listar_sucursales(conexion, cliente_id)[0]["id"]
                else:
                    cliente_id = datos_clientes.insertar_cliente(
                        conexion, hoja.nombre_cliente, None, None, None, None,
                        hoja.descuento_default, hoja.con_iva_default, False,
                    )
                    sucursal_id = datos_clientes.insertar_sucursal(conexion, cliente_id, "Principal")
                    clientes_creados += 1

            cliente_id_por_hoja[hoja.hoja] = cliente_id
            sucursal_id_por_hoja[hoja.hoja] = sucursal_id

        comprobante_id_por_hoja_y_numero: dict[tuple[str, str], int] = {}
        comprobantes_creados = 0

        for hoja in vista_previa.hojas:
            cliente_id = cliente_id_por_hoja[hoja.hoja]
            sucursal_id = sucursal_id_por_hoja[hoja.hoja]

            for remito in hoja.remitos:
                if (hoja.hoja, remito.fila) in omitir_remitos:
                    continue

                iva_a_usar = (
                    remito.iva_recalculado
                    if (hoja.hoja, remito.fila) in recalcular_iva
                    else remito.iva_discriminado
                )
                tipo_comprobante_id = _obtener_o_crear_tipo_comprobante(
                    conexion, remito.tipo_abreviatura
                )
                comprobante_id = datos_comprobantes.insertar_comprobante(
                    conexion,
                    tipo_comprobante_id,
                    remito.numero_original,
                    remito.fecha,
                    cliente_id,
                    sucursal_id,
                    remito.monto_lista,
                    remito.descuento_pct,
                    remito.monto_final,
                    remito.con_iva,
                    iva_a_usar,
                    remito.nombre_particular,
                    None,
                )
                comprobante_id_por_hoja_y_numero[(hoja.hoja, remito.numero_original)] = comprobante_id
                comprobantes_creados += 1

        recibos_por_numero: dict[int, list[tuple[HojaImportada, ReciboImportado]]] = {}
        for hoja in vista_previa.hojas:
            for recibo in hoja.recibos:
                if recibo.numero_original is not None:
                    recibos_por_numero.setdefault(recibo.numero_original, []).append((hoja, recibo))

        def _insertar_recibo_y_aplicaciones(
            cliente_id: int, numero_original, fecha: str, grupo: list[tuple[HojaImportada, ReciboImportado]]
        ) -> None:
            monto_total = sum(
                (sum((m for _, m in r.aplicaciones), r.monto_suelto) for _h, r in grupo), Decimal(0)
            )
            referencia = next((r.texto_original for _h, r in grupo if r.texto_original), None)
            if numero_original is not None and not datos_recibos.existe_numero_recibo(
                conexion, numero_original
            ):
                numero = numero_original
            else:
                # Sin número original válido, o el número ya lo usó otro
                # cliente (un mismo número de recibo repetido entre hojas no
                # puede preservarse: recibos.numero es único en toda la
                # base, no por cliente).
                numero = datos_recibos.siguiente_numero_recibo(conexion)

            recibo_id = datos_recibos.insertar_recibo(
                conexion, numero, fecha, cliente_id, monto_total,
                origen="importado", referencia=referencia,
            )
            datos_recibos.insertar_recibo_pago(
                conexion, recibo_id, forma_pago_importado_id, monto_total, None
            )
            for h, r in grupo:
                for numero_remito, monto in r.aplicaciones:
                    comprobante_id = comprobante_id_por_hoja_y_numero.get((h.hoja, numero_remito))
                    if comprobante_id is None:
                        raise ValueError(
                            f"El recibo de la hoja '{h.hoja}' aplica al remito "
                            f"{numero_remito}, que no está entre los remitos importados."
                        )
                    datos_recibos.insertar_aplicacion_pago(conexion, recibo_id, comprobante_id, monto)

        recibos_creados = 0
        recibos_ya_procesados: set[int] = set()  # id() de ReciboImportado ya insertados vía unificación

        for hoja in vista_previa.hojas:
            cliente_id = cliente_id_por_hoja[hoja.hoja]

            for recibo in hoja.recibos:
                if id(recibo) in recibos_ya_procesados:
                    continue
                if recibo.clave in omitir_recibo_claves:
                    continue

                grupo = [(hoja, recibo)]
                if recibo.numero_original in numeros_a_unificar:
                    candidatos = recibos_por_numero[recibo.numero_original]
                    cliente_ids = {cliente_id_por_hoja[h.hoja] for h, _r in candidatos}
                    if len(cliente_ids) == 1:
                        grupo = candidatos

                _insertar_recibo_y_aplicaciones(cliente_id, recibo.numero_original, recibo.fecha, grupo)
                for _h, r in grupo:
                    recibos_ya_procesados.add(id(r))
                recibos_creados += 1

        conexion.commit()
    except Exception:
        conexion.rollback()
        raise

    return {
        "clientes_creados": clientes_creados,
        "comprobantes_creados": comprobantes_creados,
        "recibos_creados": recibos_creados,
    }
