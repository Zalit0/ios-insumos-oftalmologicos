"""Casos de uso de pedidos a proveedor (plan de detalle de comprobantes,
etapa 4): cabecera + líneas de reposición (se generan solas desde el
reporte de ventas de stock) y especiales (cargadas a mano). Nunca hay más
de un pedido "en carga" por proveedor a la vez: cargar (esta pantalla),
recibir (Recepción de pedidos) y consultar (Ver pedidos) son tres módulos
separados."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from ios.data import compensaciones_reposicion as datos_compensaciones
from ios.data import pedidos_proveedor as datos
from ios.services.comprobantes import RenglonDetalle, alta_comprobante_con_detalle
from ios.services.reposicion import marcar_reposicion_generada, reporte_reposicion

ORIGENES_VALIDOS = {"reposicion", "especial"}


@dataclass
class AjusteCompensacion:
    """Un tipo de cristal/graduación al que se le descontó cantidad del
    pedido de reposición por una devolución ya repuesta anteriormente
    (plan de detalle de comprobantes, etapa 5.1)."""

    tipo_cristal_nombre: str
    graduacion: str
    cantidad_descontada: int


@dataclass
class ResultadoReposicion:
    lineas_agregadas: int
    ajustes: list[AjusteCompensacion]


def alta_pedido(conexion: sqlite3.Connection, proveedor_id: int, fecha: str) -> int:
    """Nunca hay dos pedidos "en carga" del mismo proveedor a la vez: si ya
    existe uno, se devuelve ese en vez de crear otro."""
    existente = datos.obtener_pedido_en_carga(conexion, proveedor_id)
    if existente is not None:
        return existente["id"]

    pedido_id = datos.insertar_pedido(conexion, proveedor_id, fecha)
    conexion.commit()
    return pedido_id


def pedido_en_carga(conexion: sqlite3.Connection, proveedor_id: int) -> sqlite3.Row | None:
    return datos.obtener_pedido_en_carga(conexion, proveedor_id)


def generar_lineas_reposicion(
    conexion: sqlite3.Connection, pedido_id: int, fecha_desde: str, fecha_hasta: str
) -> ResultadoReposicion:
    """Agrega al pedido una línea de reposición por cada combinación de tipo
    de cristal y graduación vendida de stock en el rango, con la cantidad
    vendida — la graduación queda en ``graduacion_solicitada`` para poder
    cargar el pedido real al proveedor (no alcanza con saber el total por
    tipo, hace falta saber qué potencia pedir de cada uno).

    Si alguna combinación tiene una compensación pendiente (una devolución
    de un cliente que ya se había vuelto a pedir al proveedor antes de
    devolverse), se descuenta de la cantidad a pedir en vez de pedir de más
    — y la compensación usada se da por resuelta.

    Cada venta que entra en este pedido queda marcada como ya repuesta, así
    que si más tarde se genera otra reposición con un rango de fechas que
    se superpone con este, esa venta no se vuelve a pedir."""
    if datos.obtener_pedido(conexion, pedido_id) is None:
        raise ValueError(f"No existe el pedido {pedido_id}.")

    items = reporte_reposicion(conexion, fecha_desde, fecha_hasta)
    lineas_agregadas = 0
    ajustes = []
    for item in items:
        cantidad_a_pedir = item.cantidad_vendida
        compensada = datos_compensaciones.obtener_cantidad_compensada(
            conexion, item.tipo_cristal_id, item.graduacion
        )
        if compensada > 0:
            a_descontar = min(compensada, item.cantidad_vendida)
            cantidad_a_pedir -= a_descontar
            datos_compensaciones.descontar_compensacion(
                conexion, item.tipo_cristal_id, item.graduacion, a_descontar
            )
            ajustes.append(AjusteCompensacion(item.nombre, item.graduacion, a_descontar))

        if cantidad_a_pedir > 0:
            datos.insertar_linea(
                conexion, pedido_id, item.tipo_cristal_id, None, cantidad_a_pedir,
                origen="reposicion", graduacion_solicitada=item.graduacion,
            )
            lineas_agregadas += 1
        marcar_reposicion_generada(conexion, item)
    conexion.commit()
    return ResultadoReposicion(lineas_agregadas, ajustes)


def agregar_linea_especial(
    conexion: sqlite3.Connection,
    pedido_id: int,
    cantidad: int,
    tipo_cristal_id: int | None = None,
    descripcion: str | None = None,
    cliente_id: int | None = None,
    graduacion_solicitada: str | None = None,
) -> int:
    if datos.obtener_pedido(conexion, pedido_id) is None:
        raise ValueError(f"No existe el pedido {pedido_id}.")
    if cantidad <= 0:
        raise ValueError("La cantidad tiene que ser mayor a cero.")
    descripcion = (descripcion or "").strip() or None
    if tipo_cristal_id is None and descripcion is None:
        raise ValueError("La línea necesita un tipo de cristal o una descripción.")

    linea_id = datos.insertar_linea(
        conexion, pedido_id, tipo_cristal_id, descripcion, cantidad, origen="especial",
        cliente_id=cliente_id, graduacion_solicitada=(graduacion_solicitada or "").strip() or None,
    )
    conexion.commit()
    return linea_id


ESTADOS_SIN_RESOLVER = {"pedido"}
ESTADOS_LISTOS_PARA_ENTREGAR = ["recibido", "recibido_con_diferencia"]


def marcar_linea_recibida(
    conexion: sqlite3.Connection, linea_id: int, graduacion_recibida: str | None = None
) -> str:
    """Resuelve la línea como llegada y lista para entregar. Si es especial
    y llegó con una graduación distinta de la pedida, queda en
    "recibido_con_diferencia" en vez de "recibido" — no bloquea nada (si se
    recibió es porque el cliente la aceptó), es solo para que se note en la
    tabla y en el PDF cuál llegó distinto. Devuelve el estado final."""
    linea = datos.obtener_linea(conexion, linea_id)
    if linea is None:
        raise ValueError(f"No existe la línea {linea_id}.")

    graduacion_recibida = (graduacion_recibida or "").strip() or None
    solicitada = (linea["graduacion_solicitada"] or "").strip() or None
    difiere = (
        linea["origen"] == "especial"
        and graduacion_recibida is not None
        and solicitada is not None
        and graduacion_recibida != solicitada
    )
    estado = "recibido_con_diferencia" if difiere else "recibido"

    campos = {"estado": estado}
    if graduacion_recibida is not None:
        campos["graduacion_recibida"] = graduacion_recibida
    datos.actualizar_linea(conexion, linea_id, campos)
    conexion.commit()
    return estado


def marcar_linea_pendiente(conexion: sqlite3.Connection, linea_id: int) -> None:
    """Resuelve la línea como "todavía no llegó, pedila de nuevo": al
    marcar el pedido recibido se arrastra como línea nueva al próximo
    pedido de ese proveedor."""
    if datos.obtener_linea(conexion, linea_id) is None:
        raise ValueError(f"No existe la línea {linea_id}.")
    datos.actualizar_linea(conexion, linea_id, {"estado": "pendiente"})
    conexion.commit()


def marcar_linea_cancelada(conexion: sqlite3.Connection, linea_id: int) -> None:
    """Resuelve la línea como "no llegó y no hace falta volver a pedirla"
    (p. ej. el cliente ya no la quiere) — a diferencia de "pendiente", no
    se arrastra a ningún pedido nuevo."""
    if datos.obtener_linea(conexion, linea_id) is None:
        raise ValueError(f"No existe la línea {linea_id}.")
    datos.actualizar_linea(conexion, linea_id, {"estado": "cancelado"})
    conexion.commit()


def lineas_listas_para_entregar(
    conexion: sqlite3.Connection, cliente_id: int | None = None
) -> list[sqlite3.Row]:
    return datos.lineas_especiales_por_estado(conexion, ESTADOS_LISTOS_PARA_ENTREGAR, cliente_id)


@dataclass
class ItemEntrega:
    """Una línea especial a entregar y, si no sale sola del catálogo (p. ej.
    una descripción libre sin tipo de cristal), el precio unitario a
    usar."""

    linea_id: int
    precio_unitario: Decimal | None = None


def generar_entrega(
    conexion: sqlite3.Connection,
    cliente_id: int,
    items: list[ItemEntrega],
    tipo_comprobante_id: int,
    numero: str,
    fecha: str,
    sucursal_id: int,
    descuento_pct: Decimal | None = None,
    con_iva: bool | None = None,
    nombre_particular: str | None = None,
    notas: str | None = None,
    forzar_numero_repetido: bool = False,
) -> int:
    """Genera un único comprobante con un renglón por cada línea especial
    tildada — pueden ser de pedidos distintos, siempre que lleguen juntas y
    sean del mismo cliente (plan de detalle de comprobantes, etapa 5). Cada
    línea queda marcada "entregada" y enlazada a su renglón vía
    ``pedido_especial_linea_id``."""
    if not items:
        raise ValueError("Elegí al menos una línea para entregar.")

    renglones = []
    for item in items:
        linea = datos.obtener_linea(conexion, item.linea_id)
        if linea is None:
            raise ValueError(f"No existe la línea {item.linea_id}.")
        if linea["origen"] != "especial":
            raise ValueError("Solo se pueden entregar líneas especiales.")
        if linea["cliente_id"] != cliente_id:
            raise ValueError("La línea no pertenece a este cliente.")
        if linea["estado"] not in ESTADOS_LISTOS_PARA_ENTREGAR:
            raise ValueError("La línea todavía no está lista para entregar.")

        graduacion = linea["graduacion_recibida"] or linea["graduacion_solicitada"] or ""
        renglones.append(RenglonDetalle(
            graduacion=graduacion,
            cantidad=linea["cantidad"],
            tipo_cristal_id=linea["tipo_cristal_id"],
            descripcion=linea["descripcion"],
            precio_unitario=item.precio_unitario,
            pedido_especial_linea_id=linea["id"],
        ))

    comprobante_id = alta_comprobante_con_detalle(
        conexion, tipo_comprobante_id, numero, fecha, cliente_id, sucursal_id, renglones,
        descuento_pct=descuento_pct, con_iva=con_iva, nombre_particular=nombre_particular,
        notas=notas, forzar_numero_repetido=forzar_numero_repetido,
    )
    for item in items:
        datos.actualizar_linea(conexion, item.linea_id, {"estado": "entregado"})
    conexion.commit()
    return comprobante_id


def listar_lineas_pedido(conexion: sqlite3.Connection, pedido_id: int) -> list[sqlite3.Row]:
    return datos.listar_lineas_pedido(conexion, pedido_id)


def listar_pedidos(
    conexion: sqlite3.Connection,
    proveedor_id: int | None = None,
    estado: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
    numero: int | None = None,
) -> list[sqlite3.Row]:
    return datos.listar_pedidos(
        conexion, proveedor_id=proveedor_id, estado=estado,
        fecha_desde=fecha_desde, fecha_hasta=fecha_hasta, numero=numero,
    )


def marcar_pedido_realizado(conexion: sqlite3.Connection, pedido_id: int) -> None:
    """El pedido ya se armó y se le mandó al proveedor: deja de estar "en
    carga". A partir de acá no tiene sentido seguir agregando líneas."""
    pedido = datos.obtener_pedido(conexion, pedido_id)
    if pedido is None:
        raise ValueError(f"No existe el pedido {pedido_id}.")
    if pedido["estado"] != "en_carga":
        raise ValueError('Solo se puede marcar "realizado" un pedido que está en carga.')

    datos.marcar_estado_pedido(conexion, pedido_id, "realizado")
    conexion.commit()


def pedido_listo_para_cerrar(conexion: sqlite3.Connection, pedido_id: int) -> bool:
    """Todavía no se puede marcar un pedido "recibido" mientras le queden
    líneas sin resolver — cada cristal tiene que quedar en uno de los
    cuatro estados finales (recibido, recibido con diferencia, pendiente o
    cancelado) antes de poder cerrarlo."""
    lineas = datos.listar_lineas_pedido(conexion, pedido_id)
    return all(linea["estado"] not in ESTADOS_SIN_RESOLVER for linea in lineas)


def marcar_pedido_recibido(
    conexion: sqlite3.Connection, pedido_id: int, fecha_nuevo_pedido: str | None = None
) -> int | None:
    """El proveedor ya mandó lo que iba a mandar, y cada línea ya se
    resolvió a mano (ver ``pedido_listo_para_cerrar``). Lo que quedó
    "pendiente" (no llegó, pero se vuelve a pedir) se agrega al pedido "en
    carga" de este proveedor si ya hay uno (seguramente el que se está
    armando para el próximo pedido); si no hay ninguno, se crea uno nuevo
    con ``fecha_nuevo_pedido`` (obligatoria en ese caso) y se le arrastran
    esas líneas ahí. Lo "cancelado" se queda como está, no se vuelve a
    pedir. Devuelve el id del pedido destino, o ``None`` si no había nada
    pendiente."""
    pedido = datos.obtener_pedido(conexion, pedido_id)
    if pedido is None:
        raise ValueError(f"No existe el pedido {pedido_id}.")
    if pedido["estado"] != "realizado":
        raise ValueError('Solo se puede marcar "recibido" un pedido ya realizado.')
    if not pedido_listo_para_cerrar(conexion, pedido_id):
        raise ValueError(
            "Todavía hay líneas sin resolver: marcá cada cristal como recibido, pendiente o "
            "cancelado antes de cerrar el pedido."
        )

    pendientes = [
        linea for linea in datos.listar_lineas_pedido(conexion, pedido_id)
        if linea["estado"] == "pendiente"
    ]

    datos.marcar_estado_pedido(conexion, pedido_id, "recibido")

    pedido_destino_id = None
    if pendientes:
        pedido_en_carga = datos.obtener_pedido_en_carga(conexion, pedido["proveedor_id"])
        if pedido_en_carga is not None:
            pedido_destino_id = pedido_en_carga["id"]
        else:
            if not fecha_nuevo_pedido:
                raise ValueError(
                    "No hay un pedido en carga para este proveedor: hace falta una fecha "
                    "para crear uno nuevo y arrastrar ahí lo que no llegó."
                )
            pedido_destino_id = datos.insertar_pedido(conexion, pedido["proveedor_id"], fecha_nuevo_pedido)
        for linea in pendientes:
            datos.insertar_linea(
                conexion, pedido_destino_id, linea["tipo_cristal_id"], linea["descripcion"],
                linea["cantidad"], origen=linea["origen"], cliente_id=linea["cliente_id"],
                graduacion_solicitada=linea["graduacion_solicitada"],
            )

    conexion.commit()
    return pedido_destino_id
