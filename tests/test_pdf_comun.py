"""Carpeta fija de PDF y apertura automática con el lector del sistema
(pedido del usuario: ningún PDF del sistema debería preguntar dónde
guardar)."""

from pathlib import Path

from ios.reports import pdf_comun


def test_ruta_pdf_automatica_usa_la_carpeta_fija(monkeypatch, tmp_path):
    monkeypatch.setattr(pdf_comun, "CARPETA_PDF_POR_DEFECTO", tmp_path / "IOS")

    ruta = pdf_comun.ruta_pdf_automatica("Recibo 1.pdf")

    assert ruta == tmp_path / "IOS" / "Recibo 1.pdf"
    assert ruta.parent.exists()  # la carpeta se crea si no existía


def test_ruta_pdf_automatica_usa_una_subcarpeta_por_tipo_de_reporte(monkeypatch, tmp_path):
    monkeypatch.setattr(pdf_comun, "CARPETA_PDF_POR_DEFECTO", tmp_path / "IOS")

    ruta = pdf_comun.ruta_pdf_automatica("Recibo 1.pdf", subcarpeta="Recibos")

    assert ruta == tmp_path / "IOS" / "Recibos" / "Recibo 1.pdf"
    assert ruta.parent.exists()


def test_ruta_pdf_automatica_admite_subcarpeta_anidada(monkeypatch, tmp_path):
    monkeypatch.setattr(pdf_comun, "CARPETA_PDF_POR_DEFECTO", tmp_path / "IOS")

    ruta = pdf_comun.ruta_pdf_automatica("Estado de cuenta.pdf", subcarpeta="Cuenta corriente/Croma")

    assert ruta == tmp_path / "IOS" / "Cuenta corriente" / "Croma" / "Estado de cuenta.pdf"
    assert ruta.parent.exists()


def test_abrir_pdf_usa_el_mecanismo_del_sistema_operativo(monkeypatch, tmp_path):
    ruta = tmp_path / "recibo.pdf"
    ruta.write_bytes(b"%PDF-1.4")

    llamadas = []
    monkeypatch.setattr(pdf_comun.sys, "platform", "win32")
    monkeypatch.setattr(pdf_comun.os, "startfile", lambda ruta: llamadas.append(ruta), raising=False)

    pdf_comun.abrir_pdf(ruta)

    assert llamadas == [str(ruta)]
