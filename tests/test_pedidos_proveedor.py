"""Pedidos a proveedor: cabecera + líneas de reposición y especiales, los
tres estados del pedido (en carga / realizado / recibido), y el arrastre de
lo pendiente al marcarlo recibido (plan de detalle de comprobantes,
etapa 4)."""

from decimal import Decimal
from pathlib import Path

import pytest

from ios.data.db import conectar
from ios.services import clientes as servicio_clientes
from ios.services import comprobantes as servicio_comprobantes
from ios.services import proveedores as servicio_proveedores
from ios.services.comprobantes import RenglonDetalle
from ios.services.pedidos_proveedor import (
    ItemEntrega,
    agregar_linea_especial,
    alta_pedido,
    generar_entrega,
    generar_lineas_reposicion,
    lineas_listas_para_entregar,
    listar_lineas_pedido,
    listar_pedidos,
    marcar_linea_cancelada,
    marcar_linea_pendiente,
    marcar_linea_recibida,
    marcar_pedido_realizado,
    marcar_pedido_recibido,
    pedido_listo_para_cerrar,
)
from ios.services.tipos_cristal import alta_tipo_cristal


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "ios_test.db")
    try:
        yield conexion
    finally:
        conexion.close()


@pytest.fixture
def rto_id(conexion) -> int:
    return conexion.execute(
        "SELECT id FROM tipos_comprobante WHERE abreviatura = 'RTO'"
    ).fetchone()["id"]


@pytest.fixture
def proveedor_id(conexion) -> int:
    return servicio_proveedores.alta_proveedor(conexion, nombre="Essilor", cuit=None)


@pytest.fixture
def croma(conexion):
    cliente_id = servicio_clientes.alta_cliente(
        conexion, nombre="Croma", descuento_default=Decimal("0"),
        con_iva_default=False, sucursales=["Croma"],
    )
    sucursal_id = conexion.execute(
        "SELECT id FROM sucursales WHERE cliente_id = ? AND nombre = 'Croma'", (cliente_id,)
    ).fetchone()["id"]
    return cliente_id, sucursal_id


def test_alta_pedido(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")

    pedidos = listar_pedidos(conexion, proveedor_id=proveedor_id)
    assert len(pedidos) == 1
    assert pedidos[0]["estado"] == "en_carga"


def test_alta_pedido_no_duplica_el_pedido_en_carga(conexion, proveedor_id):
    primero_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    segundo_id = alta_pedido(conexion, proveedor_id, "2026-03-11")

    assert primero_id == segundo_id
    assert len(listar_pedidos(conexion, proveedor_id=proveedor_id)) == 1


def test_alta_pedido_crea_uno_nuevo_si_el_anterior_ya_no_esta_en_carga(conexion, proveedor_id):
    primero_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    marcar_pedido_realizado(conexion, primero_id)

    segundo_id = alta_pedido(conexion, proveedor_id, "2026-03-11")

    assert segundo_id != primero_id


def test_generar_lineas_reposicion_trae_lo_vendido(conexion, rto_id, croma, proveedor_id):
    cliente_id, sucursal_id = croma
    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    servicio_comprobantes.alta_comprobante_con_detalle(
        conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
        renglones=[RenglonDetalle(graduacion="Neutro", cantidad=2, tipo_cristal_id=organico)],
    )
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")

    resultado = generar_lineas_reposicion(conexion, pedido_id, "2026-03-01", "2026-03-31")

    assert resultado.lineas_agregadas == 1
    assert resultado.ajustes == []
    lineas = listar_lineas_pedido(conexion, pedido_id)
    assert len(lineas) == 1
    assert lineas[0]["origen"] == "reposicion"
    assert lineas[0]["cantidad"] == 2
    assert lineas[0]["tipo_cristal_nombre"] == "Orgánico blanco"
    assert lineas[0]["graduacion_solicitada"] == "Neutro"
    assert lineas[0]["estado"] == "pedido"


def test_generar_lineas_reposicion_pedido_inexistente_falla(conexion):
    with pytest.raises(ValueError):
        generar_lineas_reposicion(conexion, 999, "2026-03-01", "2026-03-31")


def test_generar_lineas_reposicion_no_pide_dos_veces_con_rangos_superpuestos(
    conexion, rto_id, croma, proveedor_id
):
    cliente_id, sucursal_id = croma
    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    servicio_comprobantes.alta_comprobante_con_detalle(
        conexion, rto_id, "1001", "2026-03-01", cliente_id, sucursal_id,
        renglones=[RenglonDetalle(graduacion="Neutro", cantidad=2, tipo_cristal_id=organico)],
    )
    servicio_comprobantes.alta_comprobante_con_detalle(
        conexion, rto_id, "1002", "2026-03-03", cliente_id, sucursal_id,
        renglones=[RenglonDetalle(graduacion="Neutro", cantidad=1, tipo_cristal_id=organico)],
    )
    primer_pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-01")
    generar_lineas_reposicion(conexion, primer_pedido_id, "2026-03-01", "2026-03-01")
    marcar_pedido_realizado(conexion, primer_pedido_id)

    segundo_pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-04")
    resultado = generar_lineas_reposicion(conexion, segundo_pedido_id, "2026-03-01", "2026-03-03")

    assert resultado.lineas_agregadas == 1
    lineas = listar_lineas_pedido(conexion, segundo_pedido_id)
    assert len(lineas) == 1
    assert lineas[0]["cantidad"] == 1  # solo lo del día 3 — lo del día 1 ya se pidió


def test_generar_lineas_reposicion_descuenta_una_compensacion_pendiente(
    conexion, rto_id, croma, proveedor_id
):
    """Si un cliente devolvió un cristal de stock que ya se había vuelto a
    pedir al proveedor, la próxima reposición de esa combinación no debe
    pedirlo de nuevo completo."""
    from ios.data import compensaciones_reposicion as datos_compensaciones

    cliente_id, sucursal_id = croma
    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    servicio_comprobantes.alta_comprobante_con_detalle(
        conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
        renglones=[RenglonDetalle(graduacion="Neutro", cantidad=5, tipo_cristal_id=organico)],
    )
    datos_compensaciones.incrementar_compensacion(conexion, organico, "Neutro", 2)
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")

    resultado = generar_lineas_reposicion(conexion, pedido_id, "2026-03-01", "2026-03-31")

    assert resultado.lineas_agregadas == 1
    assert len(resultado.ajustes) == 1
    assert resultado.ajustes[0].cantidad_descontada == 2
    lineas = listar_lineas_pedido(conexion, pedido_id)
    assert lineas[0]["cantidad"] == 3  # 5 vendidas - 2 ya repuestas de antes
    assert datos_compensaciones.obtener_cantidad_compensada(conexion, organico, "Neutro") == 0


def test_generar_lineas_reposicion_compensacion_mayor_a_lo_vendido_no_pide_nada(
    conexion, rto_id, croma, proveedor_id
):
    from ios.data import compensaciones_reposicion as datos_compensaciones

    cliente_id, sucursal_id = croma
    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    servicio_comprobantes.alta_comprobante_con_detalle(
        conexion, rto_id, "1001", "2026-03-05", cliente_id, sucursal_id,
        renglones=[RenglonDetalle(graduacion="Neutro", cantidad=2, tipo_cristal_id=organico)],
    )
    datos_compensaciones.incrementar_compensacion(conexion, organico, "Neutro", 5)
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")

    resultado = generar_lineas_reposicion(conexion, pedido_id, "2026-03-01", "2026-03-31")

    assert resultado.lineas_agregadas == 0
    assert resultado.ajustes[0].cantidad_descontada == 2
    assert listar_lineas_pedido(conexion, pedido_id) == []
    # queda un resto de 3 unidades compensadas para la próxima vez
    assert datos_compensaciones.obtener_cantidad_compensada(conexion, organico, "Neutro") == 3


def test_agregar_linea_especial_con_cliente_y_graduacion(conexion, proveedor_id, croma):
    cliente_id, _ = croma
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")

    linea_id = agregar_linea_especial(
        conexion, pedido_id, cantidad=1, descripcion="Ultravex 1.74", cliente_id=cliente_id,
        graduacion_solicitada="ESF -8.00 CIL -1.50",
    )

    linea = listar_lineas_pedido(conexion, pedido_id)[0]
    assert linea["id"] == linea_id
    assert linea["origen"] == "especial"
    assert linea["cliente_nombre"] == "Croma"
    assert linea["graduacion_solicitada"] == "ESF -8.00 CIL -1.50"


def test_agregar_linea_especial_sin_tipo_ni_descripcion_falla(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    with pytest.raises(ValueError):
        agregar_linea_especial(conexion, pedido_id, cantidad=1)


def test_agregar_linea_especial_cantidad_invalida_falla(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    with pytest.raises(ValueError):
        agregar_linea_especial(conexion, pedido_id, cantidad=0, descripcion="Cristal")


def test_marcar_linea_recibida_guarda_la_graduacion_recibida(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    linea_id = agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Cristal")

    marcar_linea_recibida(conexion, linea_id, graduacion_recibida="ESF -8.25")

    linea = listar_lineas_pedido(conexion, pedido_id)[0]
    assert linea["estado"] == "recibido"
    assert linea["graduacion_recibida"] == "ESF -8.25"


def test_marcar_pedido_realizado(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")

    marcar_pedido_realizado(conexion, pedido_id)

    pedidos = {p["id"]: p["estado"] for p in listar_pedidos(conexion, proveedor_id=proveedor_id)}
    assert pedidos[pedido_id] == "realizado"


def test_marcar_pedido_realizado_dos_veces_falla(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    marcar_pedido_realizado(conexion, pedido_id)

    with pytest.raises(ValueError):
        marcar_pedido_realizado(conexion, pedido_id)


def test_marcar_pedido_realizado_inexistente_falla(conexion):
    with pytest.raises(ValueError):
        marcar_pedido_realizado(conexion, 999)


def test_marcar_pedido_recibido_sin_marcar_realizado_falla(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    with pytest.raises(ValueError):
        marcar_pedido_recibido(conexion, pedido_id, "2026-03-20")


def test_marcar_pedido_recibido_sin_pendientes_no_crea_uno_nuevo(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    linea_id = agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Cristal")
    marcar_linea_recibida(conexion, linea_id)
    marcar_pedido_realizado(conexion, pedido_id)

    pedido_nuevo_id = marcar_pedido_recibido(conexion, pedido_id, "2026-03-20")

    assert pedido_nuevo_id is None
    assert listar_pedidos(conexion, proveedor_id=proveedor_id, estado="en_carga") == []


def test_marcar_pedido_recibido_arrastra_lo_pendiente_a_uno_nuevo(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    recibida_id = agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Llegó")
    marcar_linea_recibida(conexion, recibida_id)
    no_llego_id = agregar_linea_especial(conexion, pedido_id, cantidad=2, descripcion="No llegó")
    marcar_linea_pendiente(conexion, no_llego_id)
    marcar_pedido_realizado(conexion, pedido_id)

    pedido_nuevo_id = marcar_pedido_recibido(conexion, pedido_id, "2026-03-20")

    assert pedido_nuevo_id is not None
    lineas_nuevas = listar_lineas_pedido(conexion, pedido_nuevo_id)
    assert len(lineas_nuevas) == 1
    assert lineas_nuevas[0]["descripcion"] == "No llegó"
    assert lineas_nuevas[0]["cantidad"] == 2
    assert lineas_nuevas[0]["estado"] == "pedido"

    pedido_viejo = [p for p in listar_pedidos(conexion, proveedor_id=proveedor_id) if p["id"] == pedido_id][0]
    assert pedido_viejo["estado"] == "recibido"

    pedido_nuevo = [p for p in listar_pedidos(conexion, proveedor_id=proveedor_id) if p["id"] == pedido_nuevo_id][0]
    assert pedido_nuevo["estado"] == "en_carga"


def test_marcar_pedido_recibido_no_arrastra_lo_cancelado(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    cancelada_id = agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Ya no lo quiere")
    marcar_linea_cancelada(conexion, cancelada_id)
    marcar_pedido_realizado(conexion, pedido_id)

    pedido_nuevo_id = marcar_pedido_recibido(conexion, pedido_id, "2026-03-20")

    assert pedido_nuevo_id is None
    linea = listar_lineas_pedido(conexion, pedido_id)[0]
    assert linea["estado"] == "cancelado"


def test_marcar_pedido_recibido_inexistente_falla(conexion):
    with pytest.raises(ValueError):
        marcar_pedido_recibido(conexion, 999, "2026-03-20")


def test_marcar_pedido_recibido_usa_el_pedido_en_carga_existente(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    no_llego_id = agregar_linea_especial(conexion, pedido_id, cantidad=2, descripcion="No llegó")
    marcar_linea_pendiente(conexion, no_llego_id)
    marcar_pedido_realizado(conexion, pedido_id)
    # ya se empezó a armar el próximo pedido antes de que llegue este
    pedido_en_carga_id = alta_pedido(conexion, proveedor_id, "2026-03-15")
    agregar_linea_especial(conexion, pedido_en_carga_id, cantidad=1, descripcion="Ya cargado")

    pedido_destino_id = marcar_pedido_recibido(conexion, pedido_id, "2026-03-20")

    assert pedido_destino_id == pedido_en_carga_id
    lineas = listar_lineas_pedido(conexion, pedido_en_carga_id)
    assert len(lineas) == 2
    assert {l["descripcion"] for l in lineas} == {"Ya cargado", "No llegó"}
    # no se creó un tercer pedido
    assert len(listar_pedidos(conexion, proveedor_id=proveedor_id)) == 2


def test_marcar_pedido_recibido_sin_pendientes_no_requiere_fecha(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    marcar_pedido_realizado(conexion, pedido_id)

    assert marcar_pedido_recibido(conexion, pedido_id) is None


def test_marcar_pedido_recibido_con_pendientes_sin_pedido_en_carga_ni_fecha_falla(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    no_llego_id = agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="No llegó")
    marcar_linea_pendiente(conexion, no_llego_id)
    marcar_pedido_realizado(conexion, pedido_id)

    with pytest.raises(ValueError):
        marcar_pedido_recibido(conexion, pedido_id)


def test_marcar_pedido_recibido_con_lineas_sin_resolver_falla(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Sin decidir todavía")
    marcar_pedido_realizado(conexion, pedido_id)

    with pytest.raises(ValueError):
        marcar_pedido_recibido(conexion, pedido_id, "2026-03-20")


def test_pedido_listo_para_cerrar(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    linea_id = agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Cristal")

    assert pedido_listo_para_cerrar(conexion, pedido_id) is False

    marcar_linea_cancelada(conexion, linea_id)

    assert pedido_listo_para_cerrar(conexion, pedido_id) is True


def test_listar_pedidos_filtra_por_rango_de_fechas(conexion, proveedor_id):
    primero_id = alta_pedido(conexion, proveedor_id, "2026-02-10")
    marcar_pedido_realizado(conexion, primero_id)
    segundo_id = alta_pedido(conexion, proveedor_id, "2026-03-10")

    pedidos = listar_pedidos(conexion, proveedor_id=proveedor_id, fecha_desde="2026-03-01")

    assert {p["id"] for p in pedidos} == {segundo_id}


def test_listar_pedidos_filtra_por_numero(conexion, proveedor_id):
    primero_id = alta_pedido(conexion, proveedor_id, "2026-02-10")
    marcar_pedido_realizado(conexion, primero_id)
    alta_pedido(conexion, proveedor_id, "2026-03-10")

    pedidos = listar_pedidos(conexion, numero=primero_id)

    assert [p["id"] for p in pedidos] == [primero_id]


def test_pdf_pedido_proveedor_se_genera(conexion, proveedor_id, tmp_path):
    from ios.reports.pedido_proveedor import generar_pdf_pedido_proveedor

    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Ultravex 1.74")

    ruta = generar_pdf_pedido_proveedor(conexion, pedido_id, tmp_path / "pedido.pdf")

    assert ruta.exists()
    assert ruta.stat().st_size > 0


def test_pdf_pedido_proveedor_inexistente_falla(conexion, tmp_path):
    from ios.reports.pedido_proveedor import generar_pdf_pedido_proveedor

    with pytest.raises(ValueError):
        generar_pdf_pedido_proveedor(conexion, 999, tmp_path / "pedido.pdf")


# --- ciclo de vida del pedido especial y entrega (etapa 5) ---


def test_marcar_linea_recibida_con_graduacion_igual_queda_lista_para_entregar(
    conexion, proveedor_id, croma
):
    cliente_id, _ = croma
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    linea_id = agregar_linea_especial(
        conexion, pedido_id, cantidad=1, descripcion="Cristal", cliente_id=cliente_id,
        graduacion_solicitada="-2.00",
    )

    marcar_linea_recibida(conexion, linea_id, graduacion_recibida="-2.00")

    assert lineas_listas_para_entregar(conexion, cliente_id)[0]["id"] == linea_id


def test_marcar_linea_recibida_con_graduacion_distinta_queda_lista_igual(
    conexion, proveedor_id, croma
):
    """Si se recibió es porque el cliente lo aceptó así — no hace falta
    ningún paso de aprobación aparte, la línea queda lista para entregar
    igual; "recibido_con_diferencia" es solo para que se note en la tabla y
    el PDF cuál llegó distinto."""
    cliente_id, _ = croma
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    linea_id = agregar_linea_especial(
        conexion, pedido_id, cantidad=1, descripcion="Cristal", cliente_id=cliente_id,
        graduacion_solicitada="-2.00",
    )

    estado = marcar_linea_recibida(conexion, linea_id, graduacion_recibida="-2.25")

    assert estado == "recibido_con_diferencia"
    linea = listar_lineas_pedido(conexion, pedido_id)[0]
    assert linea["estado"] == "recibido_con_diferencia"
    assert linea["graduacion_recibida"] == "-2.25"
    assert lineas_listas_para_entregar(conexion, cliente_id)[0]["id"] == linea_id


def test_marcar_linea_pendiente_y_cancelada(conexion, proveedor_id):
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    pendiente_id = agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Pendiente")
    cancelada_id = agregar_linea_especial(conexion, pedido_id, cantidad=1, descripcion="Cancelada")

    marcar_linea_pendiente(conexion, pendiente_id)
    marcar_linea_cancelada(conexion, cancelada_id)

    lineas = {l["id"]: l["estado"] for l in listar_lineas_pedido(conexion, pedido_id)}
    assert lineas[pendiente_id] == "pendiente"
    assert lineas[cancelada_id] == "cancelado"


def test_generar_entrega_crea_un_comprobante_con_un_renglon_por_linea(
    conexion, proveedor_id, croma, rto_id
):
    cliente_id, sucursal_id = croma
    organico = alta_tipo_cristal(conexion, "Orgánico blanco", Decimal("4770"))
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    linea_1 = agregar_linea_especial(
        conexion, pedido_id, cantidad=1, tipo_cristal_id=organico, cliente_id=cliente_id,
        graduacion_solicitada="-2.00",
    )
    linea_2 = agregar_linea_especial(
        conexion, pedido_id, cantidad=1, descripcion="Ultravex 1.74", cliente_id=cliente_id,
        graduacion_solicitada="-3.00",
    )
    marcar_linea_recibida(conexion, linea_1, graduacion_recibida="-2.00")
    marcar_linea_recibida(conexion, linea_2, graduacion_recibida="-3.00")

    comprobante_id = generar_entrega(
        conexion, cliente_id,
        items=[ItemEntrega(linea_1), ItemEntrega(linea_2, precio_unitario=Decimal("5000"))],
        tipo_comprobante_id=rto_id, numero="2001", fecha="2026-03-20", sucursal_id=sucursal_id,
    )

    detalle = servicio_comprobantes.listar_detalle_comprobante(conexion, comprobante_id)
    assert len(detalle) == 2
    assert {d["pedido_especial_linea_id"] for d in detalle} == {linea_1, linea_2}
    lineas = {l["id"]: l["estado"] for l in listar_lineas_pedido(conexion, pedido_id)}
    assert lineas[linea_1] == "entregado"
    assert lineas[linea_2] == "entregado"


def test_generar_entrega_sin_items_falla(conexion, proveedor_id, croma):
    cliente_id, sucursal_id = croma
    with pytest.raises(ValueError):
        generar_entrega(
            conexion, cliente_id, items=[], tipo_comprobante_id=1, numero="1",
            fecha="2026-03-20", sucursal_id=sucursal_id,
        )


def test_generar_entrega_linea_no_lista_falla(conexion, proveedor_id, croma, rto_id):
    cliente_id, sucursal_id = croma
    pedido_id = alta_pedido(conexion, proveedor_id, "2026-03-10")
    linea_id = agregar_linea_especial(
        conexion, pedido_id, cantidad=1, descripcion="Cristal", cliente_id=cliente_id,
    )

    with pytest.raises(ValueError):
        generar_entrega(
            conexion, cliente_id, items=[ItemEntrega(linea_id, precio_unitario=Decimal("5000"))],
            tipo_comprobante_id=rto_id, numero="2001", fecha="2026-03-20", sucursal_id=sucursal_id,
        )
