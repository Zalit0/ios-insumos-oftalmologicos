"""Casos de uso de compras (facturas de proveedores con IVA).

docs/AJUSTES_V1.1.md, etapa 5 (D2, D3): el monto cargado es el total con
IVA incluido, igual que en los remitos; el IVA se calcula solo con la
misma fórmula (ios/domain/calculos.py) a partir de la tasa (21% por
defecto, o 10,5%/0% por factura). Si se corrige el IVA a mano, la compra
queda marcada "IVA manual".
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from ios.data import compras as datos
from ios.data import configuracion as datos_configuracion
from ios.data import proveedores as datos_proveedores
from ios.domain.calculos import calcular_iva_discriminado


def alta_compra(
    conexion: sqlite3.Connection,
    proveedor_id: int,
    fecha: str,
    numero_factura: str,
    monto: Decimal,
    tasa_iva: Decimal | None = None,
    iva: Decimal | None = None,
    pedido_id: int | None = None,
) -> int:
    """``tasa_iva`` por defecto es la de configuración (21%). ``iva`` por
    defecto es el calculado a partir de ``monto`` y ``tasa_iva``; si se pasa
    un valor distinto del calculado, la compra queda marcada "IVA manual".
    ``pedido_id`` vincula esta factura con el pedido a proveedor que la
    generó (plan de detalle de comprobantes, etapa 5.3: al marcar un pedido
    recibido, se carga de una la factura asociada)."""
    if datos_proveedores.obtener_proveedor(conexion, proveedor_id) is None:
        raise ValueError(f"No existe el proveedor {proveedor_id}.")

    numero_factura = str(numero_factura).strip()
    if not numero_factura:
        raise ValueError("El número de factura es obligatorio.")

    config = datos_configuracion.obtener_configuracion(conexion)
    if tasa_iva is None:
        tasa_iva = config["iva_pct"]

    iva_calculado = calcular_iva_discriminado(monto, True, tasa_iva, config["redondeo_decimales"])
    if iva is None:
        iva_final = iva_calculado
        iva_manual = False
    else:
        iva_final = iva
        iva_manual = iva != iva_calculado

    compra_id = datos.insertar_compra(
        conexion, proveedor_id, fecha, numero_factura, monto, iva_final, tasa_iva, iva_manual,
        pedido_id=pedido_id,
    )
    conexion.commit()
    return compra_id


def listar_compras(
    conexion: sqlite3.Connection, proveedor_id: int | None = None, mes: str | None = None
) -> list[sqlite3.Row]:
    return datos.listar_compras(conexion, proveedor_id=proveedor_id, mes=mes)
