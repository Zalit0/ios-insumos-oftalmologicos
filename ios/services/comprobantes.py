"""Casos de uso de comprobantes (docs/PLAN.md, etapa 3;
docs/AJUSTES_V1.1.md, etapa 2: números repetidos permitidos, D1).

La pantalla manda monto de lista, cliente, sucursal, tipo, número y fecha;
descuento e IVA son opcionales y si no se mandan se toman del cliente. El
cálculo de monto final e IVA discriminado vive en ios/domain/calculos.py.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from decimal import Decimal

from ios.data import clientes as datos_clientes
from ios.data import compensaciones_reposicion as datos_compensaciones
from ios.data import comprobantes as datos
from ios.data import configuracion as datos_configuracion
from ios.data import detalle_comprobante as datos_detalle
from ios.data import recibos as datos_recibos
from ios.data import tipos_cristal as datos_tipos_cristal
from ios.domain.calculos import calcular_iva_discriminado, calcular_monto_final, cuantizar
from ios.services.tipos_cristal import precio_unitario as _precio_unitario_tipo_cristal


class NumeroDuplicadoError(ValueError):
    """Ya existe un comprobante vigente con ese tipo y número, del mismo
    cliente (docs/AJUSTES_V1.1.md, D1: entre clientes distintos nunca
    bloquea, solo avisa)."""


@dataclass
class CoincidenciaNumero:
    comprobante_id: int
    cliente_id: int
    cliente_nombre: str
    fecha: str
    monto_final: Decimal


@dataclass
class RenglonDetalle:
    """Un renglón de detalle a cargar (plan de detalle de comprobantes,
    etapa 2). ``cantidad`` siempre en unidades (lentes sueltos: medio par =
    1). Si no se manda ``precio_unitario``, sale del catálogo
    (``tipo_cristal_id`` obligatorio en ese caso)."""

    graduacion: str
    cantidad: int
    tipo_cristal_id: int | None = None
    descripcion: str | None = None
    precio_unitario: Decimal | None = None
    pedido_especial_linea_id: int | None = None


def _calcular_montos(
    conexion: sqlite3.Connection,
    monto_lista: Decimal,
    descuento_pct: Decimal,
    con_iva: bool,
) -> tuple[Decimal, Decimal]:
    config = datos_configuracion.obtener_configuracion(conexion)
    decimales = config["redondeo_decimales"]
    tasa_iva = config["iva_pct"]

    monto_final = calcular_monto_final(monto_lista, descuento_pct, decimales)
    iva_discriminado = calcular_iva_discriminado(monto_final, con_iva, tasa_iva, decimales)
    return monto_final, iva_discriminado


def buscar_coincidencias_numero(
    conexion: sqlite3.Connection,
    tipo_comprobante_id: int,
    numero: str,
    excluir_comprobante_id: int | None = None,
) -> list[CoincidenciaNumero]:
    """Comprobantes vigentes con ese tipo y número, en cualquier cliente.
    Se usa tanto para pedir confirmación (mismo cliente) como para el
    aviso informativo (otro cliente); nunca bloquea por sí sola."""
    filas = datos.buscar_vigentes_por_tipo_numero(conexion, tipo_comprobante_id, str(numero).strip())
    return [
        CoincidenciaNumero(
            comprobante_id=fila["id"],
            cliente_id=fila["cliente_id"],
            cliente_nombre=fila["cliente_nombre"],
            fecha=fila["fecha"],
            monto_final=fila["monto_final"],
        )
        for fila in filas
        if fila["id"] != excluir_comprobante_id
    ]


def tiene_pagos_aplicados(conexion: sqlite3.Connection, comprobante_id: int) -> bool:
    return datos_recibos.total_aplicado_a_comprobante(conexion, comprobante_id) > 0


def _validar_numero_y_cliente(
    conexion: sqlite3.Connection,
    tipo_comprobante_id: int,
    numero: str,
    cliente_id: int,
    forzar_numero_repetido: bool,
) -> tuple[str, sqlite3.Row]:
    numero = str(numero).strip()
    if not numero:
        raise ValueError("El número de comprobante es obligatorio.")

    coincidencias = buscar_coincidencias_numero(conexion, tipo_comprobante_id, numero)
    coincidencia_mismo_cliente = next(
        (c for c in coincidencias if c.cliente_id == cliente_id), None
    )
    if coincidencia_mismo_cliente is not None and not forzar_numero_repetido:
        raise NumeroDuplicadoError(
            f"Ya existe el comprobante {numero} de este cliente, del "
            f"{coincidencia_mismo_cliente.fecha} por {coincidencia_mismo_cliente.monto_final}."
        )
    # Un número repetido en OTRO cliente nunca bloquea (D1): se guarda
    # igual. Queda a cargo de quien llama mostrar el aviso informativo con
    # las coincidencias ya calculadas arriba.

    cliente = datos_clientes.obtener_cliente(conexion, cliente_id)
    if cliente is None:
        raise ValueError(f"No existe el cliente {cliente_id}.")

    return numero, cliente


def siguiente_numero_comprobante(conexion: sqlite3.Connection, tipo_comprobante_id: int) -> str:
    """Próximo número libre para un comprobante de ese tipo cargado directo
    en el sistema (plan de detalle de comprobantes, etapa 2): el inmediato
    posterior al mayor número ya usado, así nunca coincide con un remito
    manual ya cargado con ese mismo número (mismo criterio que
    ``datos_recibos.siguiente_numero_recibo``)."""
    maximo = datos.maximo_numero_comprobante(conexion, tipo_comprobante_id)
    return str((maximo or 0) + 1)


def alta_comprobante(
    conexion: sqlite3.Connection,
    tipo_comprobante_id: int,
    numero: str,
    fecha: str,
    cliente_id: int,
    sucursal_id: int,
    monto_lista: Decimal,
    descuento_pct: Decimal | None = None,
    con_iva: bool | None = None,
    nombre_particular: str | None = None,
    notas: str | None = None,
    forzar_numero_repetido: bool = False,
) -> int:
    numero, cliente = _validar_numero_y_cliente(
        conexion, tipo_comprobante_id, numero, cliente_id, forzar_numero_repetido
    )

    if descuento_pct is None:
        descuento_pct = cliente["descuento_default"]
    if con_iva is None:
        con_iva = bool(cliente["con_iva_default"])

    monto_final, iva_discriminado = _calcular_montos(conexion, monto_lista, descuento_pct, con_iva)

    comprobante_id = datos.insertar_comprobante(
        conexion,
        tipo_comprobante_id,
        numero,
        fecha,
        cliente_id,
        sucursal_id,
        monto_lista,
        descuento_pct,
        monto_final,
        con_iva,
        iva_discriminado,
        nombre_particular,
        notas,
    )
    conexion.commit()
    return comprobante_id


def alta_comprobante_con_detalle(
    conexion: sqlite3.Connection,
    tipo_comprobante_id: int,
    numero: str,
    fecha: str,
    cliente_id: int,
    sucursal_id: int,
    renglones: list[RenglonDetalle],
    descuento_pct: Decimal | None = None,
    con_iva: bool | None = None,
    nombre_particular: str | None = None,
    notas: str | None = None,
    forzar_numero_repetido: bool = False,
) -> int:
    """Como ``alta_comprobante``, pero el monto de lista sale de sumar los
    renglones en vez de tipearse (plan de detalle de comprobantes, etapa 2).
    Comprobante y detalle se guardan en una sola transacción."""
    if not renglones:
        raise ValueError("El comprobante necesita al menos un renglón de detalle.")

    numero, cliente = _validar_numero_y_cliente(
        conexion, tipo_comprobante_id, numero, cliente_id, forzar_numero_repetido
    )

    if descuento_pct is None:
        descuento_pct = cliente["descuento_default"]
    if con_iva is None:
        con_iva = bool(cliente["con_iva_default"])

    decimales = datos_configuracion.obtener_configuracion(conexion)["redondeo_decimales"]

    renglones_a_guardar = []
    monto_lista = Decimal(0)
    for renglon in renglones:
        if renglon.cantidad <= 0:
            raise ValueError("La cantidad de cada renglón tiene que ser mayor a cero.")
        descripcion = (renglon.descripcion or "").strip() or None
        if renglon.tipo_cristal_id is None and descripcion is None:
            raise ValueError("Cada renglón necesita un tipo de cristal o una descripción.")

        tipo_cristal = None
        if renglon.tipo_cristal_id is not None:
            tipo_cristal = datos_tipos_cristal.obtener_tipo_cristal(conexion, renglon.tipo_cristal_id)
            if tipo_cristal is None:
                raise ValueError(f"No existe el tipo de cristal {renglon.tipo_cristal_id}.")

        # Sin tipo de cristal (descripción libre) se asume que es un
        # cristal y la graduación es obligatoria igual (acordado con el
        # usuario: "neutro" tiene que ser un valor explícito, nunca vacío).
        requiere_graduacion = (
            bool(tipo_cristal["requiere_graduacion"]) if tipo_cristal is not None else True
        )
        graduacion = (renglon.graduacion or "").strip()
        if requiere_graduacion and not graduacion:
            raise ValueError(
                "La graduación es obligatoria en cada renglón de cristal "
                "(usá 'Neutro' si corresponde)."
            )

        if renglon.precio_unitario is not None:
            precio_unitario = renglon.precio_unitario
        elif tipo_cristal is not None:
            precio_unitario = _precio_unitario_tipo_cristal(tipo_cristal)
        else:
            raise ValueError("Falta el precio unitario del renglón.")
        if precio_unitario < 0:
            raise ValueError("El precio unitario no puede ser negativo.")

        subtotal = cuantizar(precio_unitario * renglon.cantidad, decimales)
        monto_lista += subtotal
        renglones_a_guardar.append(
            (renglon.tipo_cristal_id, descripcion, graduacion, renglon.cantidad,
             precio_unitario, subtotal, renglon.pedido_especial_linea_id)
        )

    monto_final, iva_discriminado = _calcular_montos(conexion, monto_lista, descuento_pct, con_iva)

    comprobante_id = datos.insertar_comprobante(
        conexion, tipo_comprobante_id, numero, fecha, cliente_id, sucursal_id,
        monto_lista, descuento_pct, monto_final, con_iva, iva_discriminado,
        nombre_particular, notas,
    )
    for (tipo_cristal_id, descripcion, graduacion, cantidad, precio_unitario, subtotal,
         pedido_especial_linea_id) in renglones_a_guardar:
        datos_detalle.insertar_detalle(
            conexion, comprobante_id, tipo_cristal_id, descripcion, graduacion,
            cantidad, precio_unitario, subtotal, pedido_especial_linea_id,
        )
    conexion.commit()
    return comprobante_id


def listar_detalle_comprobante(conexion: sqlite3.Connection, comprobante_id: int) -> list[sqlite3.Row]:
    return datos_detalle.listar_detalle_por_comprobante(conexion, comprobante_id)


def editar_comprobante(
    conexion: sqlite3.Connection,
    comprobante_id: int,
    forzar_numero_repetido: bool = False,
    **campos,
) -> None:
    """Edita un comprobante vigente. Si cambia monto_lista, descuento_pct o
    con_iva, recalcula monto_final e iva_discriminado — salvo que ya tenga
    pagos aplicados: ahí esos tres campos no se pueden tocar (se ofrece
    anularlo); número y fecha sí se pueden corregir siempre
    (docs/AJUSTES_V1.1.md, etapa 2.1). Si se corrige el número a uno que ya
    usa este mismo cliente, pide confirmar igual que al cargar (D1)."""
    comprobante = datos.obtener_comprobante(conexion, comprobante_id)
    if comprobante is None:
        raise ValueError(f"No existe el comprobante {comprobante_id}.")
    if comprobante["estado"] != "vigente":
        raise ValueError("No se puede editar un comprobante anulado.")

    if "numero" in campos:
        numero_nuevo = str(campos["numero"]).strip()
        if not numero_nuevo:
            raise ValueError("El número de comprobante es obligatorio.")
        campos["numero"] = numero_nuevo

        coincidencias = buscar_coincidencias_numero(
            conexion, comprobante["tipo_comprobante_id"], numero_nuevo,
            excluir_comprobante_id=comprobante_id,
        )
        coincidencia_mismo_cliente = next(
            (c for c in coincidencias if c.cliente_id == comprobante["cliente_id"]), None
        )
        if coincidencia_mismo_cliente is not None and not forzar_numero_repetido:
            raise NumeroDuplicadoError(
                f"Ya existe el comprobante {numero_nuevo} de este cliente, del "
                f"{coincidencia_mismo_cliente.fecha} por {coincidencia_mismo_cliente.monto_final}."
            )

    recalcula = {"monto_lista", "descuento_pct", "con_iva"} & campos.keys()
    if recalcula and tiene_pagos_aplicados(conexion, comprobante_id):
        raise ValueError(
            "Este comprobante ya tiene pagos aplicados: no se puede cambiar el "
            "monto, el descuento ni el IVA. Para corregirlo, anulalo y cargalo de nuevo."
        )

    if recalcula:
        monto_lista = campos.get("monto_lista", comprobante["monto_lista"])
        descuento_pct = campos.get("descuento_pct", comprobante["descuento_pct"])
        con_iva = campos.get("con_iva", bool(comprobante["con_iva"]))

        monto_final, iva_discriminado = _calcular_montos(
            conexion, monto_lista, descuento_pct, bool(con_iva)
        )
        campos["monto_final"] = monto_final
        campos["iva_discriminado"] = iva_discriminado
        if "con_iva" in campos:
            campos["con_iva"] = int(con_iva)

    datos.actualizar_comprobante(conexion, comprobante_id, campos)
    conexion.commit()


def anular_comprobante(conexion: sqlite3.Connection, comprobante_id: int) -> None:
    comprobante = datos.obtener_comprobante(conexion, comprobante_id)
    if comprobante is None:
        raise ValueError(f"No existe el comprobante {comprobante_id}.")

    datos.marcar_estado(conexion, comprobante_id, "anulado")
    conexion.commit()


def registrar_devolucion(
    conexion: sqlite3.Connection, comprobante_id: int, ya_repuesto: bool = False
) -> None:
    """Devolución de un comprobante ya entregado (plan de detalle de
    comprobantes, etapa 5.1): por ahora el único efecto es anularlo, no se
    cobra (todavía no se maneja stock real). Si lo que se devuelve es de
    stock (no de un pedido especial) y ``ya_repuesto`` es True — ese
    cristal y esa graduación ya se habían vuelto a pedir al proveedor antes
    de la devolución —, queda una compensación para no pedirlo de más la
    próxima vez que se genere la reposición."""
    anular_comprobante(conexion, comprobante_id)
    if ya_repuesto:
        for renglon in datos_detalle.listar_detalle_por_comprobante(conexion, comprobante_id):
            if renglon["tipo_cristal_id"] is not None and renglon["pedido_especial_linea_id"] is None:
                datos_compensaciones.incrementar_compensacion(
                    conexion, renglon["tipo_cristal_id"], renglon["graduacion"], renglon["cantidad"],
                )
        conexion.commit()


def listar_comprobantes(
    conexion: sqlite3.Connection,
    cliente_id: int | None = None,
    sucursal_id: int | None = None,
    mes: str | None = None,
    estado: str | None = None,
    tipo_comprobante_id: int | None = None,
    numero: str | None = None,
    fecha_desde: str | None = None,
    fecha_hasta: str | None = None,
) -> list[sqlite3.Row]:
    return datos.listar_comprobantes(
        conexion,
        cliente_id=cliente_id,
        sucursal_id=sucursal_id,
        mes=mes,
        estado=estado,
        tipo_comprobante_id=tipo_comprobante_id,
        numero=numero,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )
