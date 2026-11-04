from ios.domain.validaciones import cuit_valido


def test_cuit_valido_con_guiones():
    assert cuit_valido("20-12345678-6")


def test_cuit_valido_sin_guiones():
    assert cuit_valido("20123456786")


def test_cuit_digito_verificador_incorrecto():
    assert not cuit_valido("20-12345678-9")


def test_cuit_longitud_incorrecta():
    assert not cuit_valido("20-1234-6")


def test_cuit_con_letras():
    assert not cuit_valido("20-1234567X-6")


def test_cuit_vacio():
    assert not cuit_valido("")
