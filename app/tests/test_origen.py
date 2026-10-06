from aria.origen import origen_permitido as ok

H = "192.168.1.50"


def test_origen_coincide():
    assert ok("https://" + H, H, "same-origin", None)
    assert ok(None, H, None, None)


def test_origen_distinto():
    assert not ok("https://evil.example", H, "same-origin", None)
    assert not ok("https://evil.example", H, None, None)


def test_null_same_origin():
    assert ok("null", H, "same-origin", None)


def test_null_cross_site_o_desconocido():
    assert not ok("null", H, "cross-site", None)
    assert not ok("null", H, "none", None)
    assert not ok("null", H, None, None)


def test_null_sin_fetch_metadata_usa_referer():
    assert ok("null", H, None, "https://" + H + "/login")
    assert not ok("null", H, None, "https://evil.example/")


def test_cross_site_siempre_rechazado():
    assert not ok("https://" + H, H, "cross-site", None)
