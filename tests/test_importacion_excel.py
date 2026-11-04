"""Etapa 9: importación opcional desde Excel."""

from datetime import date
from decimal import Decimal
from pathlib import Path

import openpyxl
import pytest

from ios.data import clientes as datos_clientes
from ios.data import comprobantes as datos_comprobantes
from ios.data import recibos as datos_recibos
from ios.data.db import conectar
from ios.services.importacion_excel import (
    FORMA_PAGO_IMPORTADO,
    OPCION_IVA_DEL_EXCEL,
    OPCION_IVA_RECALCULADO,
    OPCION_PAGO_OMITIR,
    OPCION_RECIBO_UNIFICAR,
    OPCION_REMITO_IMPORTAR_AMBOS,
    OPCION_REMITO_OMITIR,
    OPCION_SUCURSAL_CLIENTE_NUEVO,
    OPCION_TEXTO_OMITIR,
    confirmar_importacion,
    leer_archivo,
)

ENCABEZADO = [
    "FECHA", "TIPO", "NUM.", "MONTO", "DESC.", "FINAL", "SI/NO", "$", "MONTO",
    "RECIBO", "FECHA", "SALDOS", None,
]

RUTA_MARZO_2024 = Path(__file__).resolve().parent.parent / "docs" / "MARZO 2024.xlsx"


@pytest.fixture
def conexion(tmp_path: Path):
    conexion = conectar(tmp_path / "ios_test.db")
    try:
        yield conexion
    finally:
        conexion.close()


def _crear_libro(tmp_path: Path, hojas: dict[str, list[tuple]], nombre_archivo: str = "test.xlsx") -> Path:
    """Crea un .xlsx con el mismo layout que la planilla real: título en
    B1, encabezado en la fila 4 (columnas B..N) y datos desde la fila 5."""
    libro = openpyxl.Workbook()
    libro.remove(libro.active)

    for nombre_hoja, filas in hojas.items():
        ws = libro.create_sheet(nombre_hoja)
        ws.cell(row=1, column=2, value=nombre_hoja)
        for col, valor in enumerate(ENCABEZADO, start=2):
            ws.cell(row=4, column=col, value=valor)
        for i, fila in enumerate(filas):
            for col, valor in enumerate(fila, start=2):
                ws.cell(row=5 + i, column=col, value=valor)

    ruta = tmp_path / nombre_archivo
    libro.save(ruta)
    return ruta


def _fila_remito(fecha, numero, monto, descuento, final, con_iva, iva, pago=None, recibo=None,
                  fecha_pago=None, saldo=None, nombre_particular=None):
    return (
        fecha, "RTO", numero, monto, descuento, final, ("SI" if con_iva else None), iva,
        pago, recibo, fecha_pago, (saldo if saldo is not None else final - (pago or 0)),
        nombre_particular,
    )


def _fila_pago_suelto(pago, fecha_pago=None):
    return (None, None, None, None, None, 0, None, 0, pago, None, fecha_pago, -pago, None)


def test_hoja_sin_movimientos_no_crea_cliente(tmp_path):
    ruta = _crear_libro(tmp_path, {"VACIA": []})
    vista = leer_archivo(ruta, "2024-03")
    assert vista.hojas == []


def test_remito_duplicado_dentro_de_una_hoja_se_detecta(tmp_path):
    ruta = _crear_libro(tmp_path, {
        "LA OPTICA": [
            _fila_remito(date(2024, 3, 1), 45126, 1000, 20, 800, False, 0),
            _fila_remito(date(2024, 3, 2), 45126, 2000, 20, 1600, False, 0),
        ]
    })
    vista = leer_archivo(ruta, "2024-03")
    tipos = {a.tipo for a in vista.anomalias}
    assert "remito_repetido" in tipos


def test_iva_distinto_de_la_formula_se_detecta(tmp_path):
    ruta = _crear_libro(tmp_path, {
        "KORAL": [
            _fila_remito(date(2024, 3, 8), 45150, 7502, 20, 6001.6, True, 7502, pago=6001.6,
                         recibo=70192, fecha_pago=date(2024, 3, 8), saldo=0),
        ]
    })
    vista = leer_archivo(ruta, "2024-03")
    tipos = {a.tipo for a in vista.anomalias}
    assert "iva_no_coincide" in tipos


def test_pago_suelto_sin_remito_queda_como_saldo_a_favor(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "CRISOL": [
            _fila_remito(date(2024, 3, 4), 45103, 4416.4, 20, 3533.12, True, 613.19, pago=3533.12,
                         recibo=70152, fecha_pago=date(2024, 3, 4), saldo=0),
            _fila_pago_suelto(2),
        ]
    })
    vista = leer_archivo(ruta, "2024-03")
    assert any(a.tipo == "pago_suelto" for a in vista.anomalias)
    assert any(a.tipo == "pago_sin_fecha" for a in vista.anomalias)

    confirmar_importacion(conexion, vista)

    cliente = datos_clientes.obtener_cliente_por_nombre(conexion, "CRISOL")
    recibos = datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente["id"])
    monto_total = sum((r["monto_total"] for r in recibos), Decimal(0))
    aplicado_total = sum(
        (datos_recibos.total_aplicado_de_recibo(conexion, r["id"]) for r in recibos), Decimal(0)
    )
    # El pago suelto de 2 entra como recibo sin aplicaciones: queda como
    # saldo a favor (recibido 2 de más, sin remito que cubra).
    assert monto_total - aplicado_total == Decimal("2.00")


def test_recibo_con_texto_se_renumera_automaticamente_al_confirmar(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "KORAL": [
            _fila_remito(date(2024, 3, 1), 45093, 2208.2, 20, 1766.56, True, 306.59, pago=1766.56,
                         recibo="S/N", fecha_pago=date(2024, 3, 1), saldo=0),
        ]
    })
    vista = leer_archivo(ruta, "2024-03")
    assert any(a.tipo == "recibo_con_texto" for a in vista.anomalias)

    confirmar_importacion(conexion, vista)

    cliente = datos_clientes.obtener_cliente_por_nombre(conexion, "KORAL")
    recibos = datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente["id"])
    assert len(recibos) == 1
    assert isinstance(recibos[0]["numero"], int)  # se le asignó un número válido


def test_recibo_que_cubre_varios_remitos_se_agrupa_como_del_pilar(tmp_path, conexion):
    fecha_pago = date(2024, 3, 11)
    ruta = _crear_libro(tmp_path, {
        "DEL PILAR": [
            _fila_remito(date(2024, 3, 4), 45109, 16334.8, 20, 13067.84, False, 0, pago=13067.84,
                         recibo=70011, fecha_pago=fecha_pago, saldo=0),
            _fila_remito(date(2024, 3, 5), 45120, 37630.8, 20, 30104.64, False, 0, pago=30104.64,
                         recibo=70011, fecha_pago=fecha_pago, saldo=0),
            _fila_remito(date(2024, 3, 6), 45129, 28555.7, 20, 22844.56, False, 0, pago=22844.56,
                         recibo=70011, fecha_pago=fecha_pago, saldo=0),
        ]
    })
    vista = leer_archivo(ruta, "2024-03")
    hoja = vista.hojas[0]
    assert len(hoja.recibos) == 1
    assert hoja.recibos[0].numero_original == 70011
    assert len(hoja.recibos[0].aplicaciones) == 3

    confirmar_importacion(conexion, vista)
    cliente = datos_clientes.obtener_cliente_por_nombre(conexion, "DEL PILAR")
    recibos = datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente["id"])
    assert len(recibos) == 1
    assert recibos[0]["numero"] == 70011
    assert recibos[0]["monto_total"] == Decimal("66017.04")


def test_recibo_importado_no_genera_movimiento_de_caja(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "CROMA": [
            _fila_remito(date(2024, 3, 1), 31063, 104544, 25, 78408, True, 13608, pago=78408,
                         recibo=1001, fecha_pago=date(2024, 3, 1), saldo=0),
        ]
    })
    vista = leer_archivo(ruta, "2024-03")
    confirmar_importacion(conexion, vista)

    movimientos = conexion.execute("SELECT * FROM movimientos_caja").fetchall()
    assert movimientos == []

    forma_importado = conexion.execute(
        "SELECT * FROM formas_pago WHERE nombre = ?", (FORMA_PAGO_IMPORTADO,)
    ).fetchone()
    assert forma_importado is not None


def test_asignar_hoja_como_sucursal_de_otro_cliente(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "CROMA": [
            _fila_remito(date(2024, 3, 1), 1, 1000, 25, 750, False, 0),
        ],
        "CROMA FDEZ.": [
            _fila_remito(date(2024, 3, 1), 2, 2000, 25, 1500, False, 0),
        ],
    })
    vista = leer_archivo(ruta, "2024-03")

    confirmar_importacion(conexion, vista, asignaciones_sucursal={"CROMA FDEZ.": "CROMA"})

    croma = datos_clientes.obtener_cliente_por_nombre(conexion, "CROMA")
    assert croma is not None
    assert datos_clientes.obtener_cliente_por_nombre(conexion, "CROMA FDEZ.") is None

    sucursales = {s["nombre"] for s in datos_clientes.listar_sucursales(conexion, croma["id"])}
    assert sucursales == {"Principal", "CROMA FDEZ."}

    comprobantes = datos_comprobantes.listar_comprobantes(conexion, cliente_id=croma["id"])
    assert len(comprobantes) == 2


def test_particulares_reutiliza_el_cliente_existente(tmp_path, conexion):
    particulares_antes = datos_clientes.obtener_cliente_por_nombre(conexion, "Particulares")
    ruta = _crear_libro(tmp_path, {
        "PARTICULARES": [
            _fila_remito(date(2024, 3, 1), 1, 1000, 20, 800, False, 0, nombre_particular="BEBIS"),
        ],
    })
    vista = leer_archivo(ruta, "2024-03")
    resultado = confirmar_importacion(conexion, vista)

    assert resultado["clientes_creados"] == 0
    particulares_despues = datos_clientes.obtener_cliente_por_nombre(conexion, "Particulares")
    assert particulares_despues["id"] == particulares_antes["id"]

    comprobantes = datos_comprobantes.listar_comprobantes(
        conexion, cliente_id=particulares_antes["id"]
    )
    assert comprobantes[0]["nombre_particular"] == "BEBIS"


def test_confirmar_importacion_es_atomica_si_algo_falla(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "CROMA": [
            _fila_remito(date(2024, 3, 1), 1, 1000, 25, 750, False, 0),
        ],
    })
    vista = leer_archivo(ruta, "2024-03")
    # Una asignación de sucursal con una hoja padre inexistente hace que
    # confirmar_importacion falle a mitad de camino.
    with pytest.raises(ValueError):
        confirmar_importacion(conexion, vista, asignaciones_sucursal={"CROMA": "NO EXISTE"})

    assert datos_clientes.obtener_cliente_por_nombre(conexion, "CROMA") is None
    assert conexion.execute("SELECT * FROM comprobantes").fetchall() == []


@pytest.mark.skipif(not RUTA_MARZO_2024.exists(), reason="No está docs/MARZO 2024.xlsx")
def test_importar_marzo_2024_reproduce_los_totales_esperados(conexion):
    """Caso de aceptación de la etapa.

    TOTALES, en la planilla real, tiene un bug propio: su fórmula de suma
    no incluye la hoja CRISOL (se puede confirmar sumando el "Total Venta"
    de cada hoja por separado). Por eso el total que reproduce esta
    importación es el de TOTALES más el de CRISOL, no el valor crudo de
    TOTALES.
    """
    from ios.services.resumen_mensual import resumen_del_mes

    vista = leer_archivo(RUTA_MARZO_2024, "2024-03")
    confirmar_importacion(conexion, vista, asignaciones_sucursal={"CROMA FDEZ.": "CROMA"})

    resumen = resumen_del_mes(conexion, "2024-03")

    total_venta_esperado = Decimal("2848734.135") + Decimal("40738.24")
    total_pagos_esperado = Decimal("1038852.72") + Decimal("20134.08")
    total_saldos_esperado = Decimal("1809881.415") + Decimal("20604.16")

    assert abs(resumen.total_venta - total_venta_esperado) < Decimal("0.10")
    assert abs(resumen.total_pagos - total_pagos_esperado) < Decimal("0.10")
    assert abs(resumen.total_saldos - total_saldos_esperado) < Decimal("0.10")

    # Anomalías documentadas en docs/PLAN.md, todas deben detectarse.
    tipos = {a.tipo for a in vista.anomalias}
    assert "remito_repetido" in tipos  # La Óptica, remito 45126
    assert "remito_repetido_entre_hojas" in tipos  # Crisol / Mirage, 45142
    assert "iva_no_coincide" in tipos  # Koral, remito 45150
    assert "pago_suelto" in tipos  # Crisol, pago de 2
    assert "recibo_con_texto" in tipos  # TRANSF, S/R, S/N

    cliente_del_pilar = datos_clientes.obtener_cliente_por_nombre(conexion, "DEL PILAR")
    recibo_70011 = next(
        r for r in datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente_del_pilar["id"])
        if r["numero"] == 70011
    )
    aplicaciones = datos_recibos.listar_aplicaciones_de_recibo(conexion, recibo_70011["id"])
    assert len(aplicaciones) == 5


# --- etapa 7: resolución de conflictos ---


def test_remito_repetido_genera_un_conflicto_con_opciones(tmp_path):
    ruta = _crear_libro(tmp_path, {
        "LA OPTICA": [
            _fila_remito(date(2024, 3, 1), 45126, 1000, 20, 800, False, 0),
            _fila_remito(date(2024, 3, 2), 45126, 2000, 20, 1600, False, 0),
        ]
    })
    vista = leer_archivo(ruta, "2024-03")

    conflicto = next(c for c in vista.conflictos if c.tipo == "remito_repetido")
    assert conflicto.opciones == [OPCION_REMITO_IMPORTAR_AMBOS, OPCION_REMITO_OMITIR]
    assert conflicto.sugerida == OPCION_REMITO_IMPORTAR_AMBOS


def test_omitir_remito_repetido_no_lo_importa(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "LA OPTICA": [
            _fila_remito(date(2024, 3, 1), 45126, 1000, 20, 800, False, 0),
            _fila_remito(date(2024, 3, 2), 45126, 2000, 20, 1600, False, 0),
        ]
    })
    vista = leer_archivo(ruta, "2024-03")
    conflicto = next(c for c in vista.conflictos if c.tipo == "remito_repetido")

    confirmar_importacion(conexion, vista, decisiones={conflicto.id: OPCION_REMITO_OMITIR})

    cliente = datos_clientes.obtener_cliente_por_nombre(conexion, "LA OPTICA")
    comprobantes = datos_comprobantes.listar_comprobantes(conexion, cliente_id=cliente["id"])
    assert len(comprobantes) == 1
    assert comprobantes[0]["monto_lista"] == Decimal("1000")


def test_sin_decidir_el_iva_no_coincide_se_recalcula_por_defecto(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "KORAL": [
            _fila_remito(date(2024, 3, 8), 45150, 7502, 20, 6001.6, True, 7502, pago=6001.6,
                         recibo=70192, fecha_pago=date(2024, 3, 8), saldo=0),
        ]
    })
    vista = leer_archivo(ruta, "2024-03")

    confirmar_importacion(conexion, vista)  # sin decisiones: usa la sugerida

    cliente = datos_clientes.obtener_cliente_por_nombre(conexion, "KORAL")
    comprobante = datos_comprobantes.listar_comprobantes(conexion, cliente_id=cliente["id"])[0]
    remito = vista.hojas[0].remitos[0]
    assert comprobante["iva_discriminado"] == remito.iva_recalculado
    assert comprobante["iva_discriminado"] != remito.iva_discriminado


def test_conservar_iva_del_excel_cuando_se_decide_asi(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "KORAL": [
            _fila_remito(date(2024, 3, 8), 45150, 7502, 20, 6001.6, True, 7502, pago=6001.6,
                         recibo=70192, fecha_pago=date(2024, 3, 8), saldo=0),
        ]
    })
    vista = leer_archivo(ruta, "2024-03")
    conflicto = next(c for c in vista.conflictos if c.tipo == "iva_no_coincide")

    confirmar_importacion(conexion, vista, decisiones={conflicto.id: OPCION_IVA_DEL_EXCEL})

    cliente = datos_clientes.obtener_cliente_por_nombre(conexion, "KORAL")
    comprobante = datos_comprobantes.listar_comprobantes(conexion, cliente_id=cliente["id"])[0]
    assert comprobante["iva_discriminado"] == Decimal("7502.00")


def test_omitir_pago_suelto_no_crea_saldo_a_favor(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "CRISOL": [
            _fila_remito(date(2024, 3, 4), 45103, 4416.4, 20, 3533.12, True, 613.19, pago=3533.12,
                         recibo=70152, fecha_pago=date(2024, 3, 4), saldo=0),
            _fila_pago_suelto(2),
        ]
    })
    vista = leer_archivo(ruta, "2024-03")
    conflicto = next(c for c in vista.conflictos if c.tipo == "pago_suelto")

    confirmar_importacion(conexion, vista, decisiones={conflicto.id: OPCION_PAGO_OMITIR})

    cliente = datos_clientes.obtener_cliente_por_nombre(conexion, "CRISOL")
    recibos = datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente["id"])
    monto_total = sum((r["monto_total"] for r in recibos), Decimal(0))
    aplicado_total = sum(
        (datos_recibos.total_aplicado_de_recibo(conexion, r["id"]) for r in recibos), Decimal(0)
    )
    assert monto_total - aplicado_total == Decimal("0")


def test_recibo_con_texto_guarda_la_referencia_por_defecto(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "KORAL": [
            _fila_remito(date(2024, 3, 1), 45093, 2208.2, 20, 1766.56, True, 306.59, pago=1766.56,
                         recibo="S/N", fecha_pago=date(2024, 3, 1), saldo=0),
        ]
    })
    vista = leer_archivo(ruta, "2024-03")

    confirmar_importacion(conexion, vista)  # sin decisiones: usa la sugerida

    cliente = datos_clientes.obtener_cliente_por_nombre(conexion, "KORAL")
    recibos = datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente["id"])
    assert recibos[0]["referencia"] == "S/N"


def test_omitir_pago_de_recibo_con_texto_no_lo_importa(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "KORAL": [
            _fila_remito(date(2024, 3, 1), 45093, 2208.2, 20, 1766.56, True, 306.59, pago=1766.56,
                         recibo="S/N", fecha_pago=date(2024, 3, 1), saldo=0),
        ]
    })
    vista = leer_archivo(ruta, "2024-03")
    conflicto = next(c for c in vista.conflictos if c.tipo == "recibo_con_texto")

    confirmar_importacion(conexion, vista, decisiones={conflicto.id: OPCION_TEXTO_OMITIR})

    cliente = datos_clientes.obtener_cliente_por_nombre(conexion, "KORAL")
    recibos = datos_recibos.listar_recibos_vigentes_cliente(conexion, cliente["id"])
    assert recibos == []
    comprobantes = datos_comprobantes.listar_comprobantes(conexion, cliente_id=cliente["id"])
    assert len(comprobantes) == 1  # el remito se importa igual, solo se omite el pago


def test_recibo_compartido_entre_hojas_se_renumera_por_defecto(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "CROMA": [
            _fila_remito(date(2024, 3, 1), 1, 1000, 25, 750, False, 0, pago=750, recibo=500,
                         fecha_pago=date(2024, 3, 1), saldo=0),
        ],
        "CROMA FDEZ.": [
            _fila_remito(date(2024, 3, 1), 2, 2000, 25, 1500, False, 0, pago=1500, recibo=500,
                         fecha_pago=date(2024, 3, 1), saldo=0),
        ],
    })
    vista = leer_archivo(ruta, "2024-03")
    conflicto = next(c for c in vista.conflictos if c.tipo == "recibo_compartido")
    assert conflicto.datos["numero_recibo"] == 500

    confirmar_importacion(conexion, vista, asignaciones_sucursal={"CROMA FDEZ.": "CROMA"})

    croma = datos_clientes.obtener_cliente_por_nombre(conexion, "CROMA")
    recibos = datos_recibos.listar_recibos_vigentes_cliente(conexion, croma["id"])
    assert len(recibos) == 2  # uno se renumeró, no se unificaron
    numeros = {r["numero"] for r in recibos}
    assert 500 in numeros


def test_unificar_recibo_compartido_cuando_son_la_misma_cuenta(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "CROMA": [
            _fila_remito(date(2024, 3, 1), 1, 1000, 25, 750, False, 0, pago=750, recibo=500,
                         fecha_pago=date(2024, 3, 1), saldo=0),
        ],
        "CROMA FDEZ.": [
            _fila_remito(date(2024, 3, 1), 2, 2000, 25, 1500, False, 0, pago=1500, recibo=500,
                         fecha_pago=date(2024, 3, 1), saldo=0),
        ],
    })
    vista = leer_archivo(ruta, "2024-03")
    conflicto = next(c for c in vista.conflictos if c.tipo == "recibo_compartido")

    confirmar_importacion(
        conexion, vista,
        asignaciones_sucursal={"CROMA FDEZ.": "CROMA"},
        decisiones={conflicto.id: OPCION_RECIBO_UNIFICAR},
    )

    croma = datos_clientes.obtener_cliente_por_nombre(conexion, "CROMA")
    recibos = datos_recibos.listar_recibos_vigentes_cliente(conexion, croma["id"])
    assert len(recibos) == 1
    assert recibos[0]["numero"] == 500
    assert recibos[0]["monto_total"] == Decimal("2250")
    aplicaciones = datos_recibos.listar_aplicaciones_de_recibo(conexion, recibos[0]["id"])
    assert len(aplicaciones) == 2


def test_hoja_que_parece_sucursal_se_detecta(tmp_path):
    ruta = _crear_libro(tmp_path, {
        "CROMA": [
            _fila_remito(date(2024, 3, 1), 1, 1000, 25, 750, False, 0),
        ],
        "CROMA FDEZ.": [
            _fila_remito(date(2024, 3, 1), 2, 2000, 25, 1500, False, 0),
        ],
    })
    vista = leer_archivo(ruta, "2024-03")

    conflicto = next(c for c in vista.conflictos if c.tipo == "posible_sucursal")
    assert conflicto.hoja == "CROMA FDEZ."
    assert conflicto.datos["hoja_padre_sugerida"] == "CROMA"
    assert conflicto.sugerida == "Importar como sucursal de CROMA"


def test_posible_sucursal_no_se_aplica_sin_decision_explicita(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "CROMA": [
            _fila_remito(date(2024, 3, 1), 1, 1000, 25, 750, False, 0),
        ],
        "CROMA FDEZ.": [
            _fila_remito(date(2024, 3, 1), 2, 2000, 25, 1500, False, 0),
        ],
    })
    vista = leer_archivo(ruta, "2024-03")

    confirmar_importacion(conexion, vista)  # sin decisiones ni asignaciones

    assert datos_clientes.obtener_cliente_por_nombre(conexion, "CROMA FDEZ.") is not None


def test_posible_sucursal_se_aplica_si_se_confirma_la_sugerida(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "CROMA": [
            _fila_remito(date(2024, 3, 1), 1, 1000, 25, 750, False, 0),
        ],
        "CROMA FDEZ.": [
            _fila_remito(date(2024, 3, 1), 2, 2000, 25, 1500, False, 0),
        ],
    })
    vista = leer_archivo(ruta, "2024-03")
    conflicto = next(c for c in vista.conflictos if c.tipo == "posible_sucursal")

    confirmar_importacion(conexion, vista, decisiones={conflicto.id: conflicto.sugerida})

    assert datos_clientes.obtener_cliente_por_nombre(conexion, "CROMA FDEZ.") is None
    croma = datos_clientes.obtener_cliente_por_nombre(conexion, "CROMA")
    sucursales = {s["nombre"] for s in datos_clientes.listar_sucursales(conexion, croma["id"])}
    assert "CROMA FDEZ." in sucursales


def test_posible_sucursal_cliente_nuevo_no_lo_asigna(tmp_path, conexion):
    ruta = _crear_libro(tmp_path, {
        "CROMA": [
            _fila_remito(date(2024, 3, 1), 1, 1000, 25, 750, False, 0),
        ],
        "CROMA FDEZ.": [
            _fila_remito(date(2024, 3, 1), 2, 2000, 25, 1500, False, 0),
        ],
    })
    vista = leer_archivo(ruta, "2024-03")
    conflicto = next(c for c in vista.conflictos if c.tipo == "posible_sucursal")

    confirmar_importacion(
        conexion, vista, decisiones={conflicto.id: OPCION_SUCURSAL_CLIENTE_NUEVO}
    )

    assert datos_clientes.obtener_cliente_por_nombre(conexion, "CROMA FDEZ.") is not None


def test_reimportar_otro_mes_no_duplica_la_sucursal_ya_asignada(tmp_path, conexion):
    """Caso reportado: al importar un mes nuevo, la misma hoja vuelve a
    detectarse como posible sucursal del mismo cliente; si se vuelve a
    confirmar, no debe intentar crear la sucursal de nuevo (violaría la
    restricción única de sucursales) sino reusar la que ya existe."""
    marzo = _crear_libro(tmp_path, {
        "CROMA": [
            _fila_remito(date(2024, 3, 1), 1, 1000, 25, 750, False, 0),
        ],
        "CROMA FDEZ.": [
            _fila_remito(date(2024, 3, 1), 2, 2000, 25, 1500, False, 0),
        ],
    }, nombre_archivo="marzo.xlsx")
    vista_marzo = leer_archivo(marzo, "2024-03")
    conflicto_marzo = next(c for c in vista_marzo.conflictos if c.tipo == "posible_sucursal")
    confirmar_importacion(conexion, vista_marzo, decisiones={conflicto_marzo.id: conflicto_marzo.sugerida})

    octubre = _crear_libro(tmp_path, {
        "CROMA": [
            _fila_remito(date(2024, 10, 1), 3, 1000, 25, 750, False, 0),
        ],
        "CROMA FDEZ.": [
            _fila_remito(date(2024, 10, 1), 4, 2000, 25, 1500, False, 0),
        ],
    }, nombre_archivo="octubre.xlsx")
    vista_octubre = leer_archivo(octubre, "2024-10")
    conflicto_octubre = next(c for c in vista_octubre.conflictos if c.tipo == "posible_sucursal")

    resultado = confirmar_importacion(
        conexion, vista_octubre, decisiones={conflicto_octubre.id: conflicto_octubre.sugerida}
    )

    assert resultado["clientes_creados"] == 0
    croma = datos_clientes.obtener_cliente_por_nombre(conexion, "CROMA")
    sucursales = datos_clientes.listar_sucursales(conexion, croma["id"])
    assert sorted(s["nombre"] for s in sucursales) == ["CROMA FDEZ.", "Principal"]
    comprobantes = datos_comprobantes.listar_comprobantes(conexion, cliente_id=croma["id"])
    assert len(comprobantes) == 4


def test_no_sugiere_sucursal_por_coincidencia_parcial_sin_limite_de_palabra(tmp_path):
    ruta = _crear_libro(tmp_path, {
        "CROMA": [
            _fila_remito(date(2024, 3, 1), 1, 1000, 25, 750, False, 0),
        ],
        "CROMADOS SA": [
            _fila_remito(date(2024, 3, 1), 2, 2000, 25, 1500, False, 0),
        ],
    })
    vista = leer_archivo(ruta, "2024-03")

    assert not any(c.tipo == "posible_sucursal" for c in vista.conflictos)
