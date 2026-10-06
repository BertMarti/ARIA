import pytest

from aria import vpn


@pytest.mark.parametrize("n", ["movil-ana", "Mi portatil", "a", "x.y_z-1", "a" * 32, "Móvil de Lucía", "ñandú", "Tele del salón"])
def test_nombres_validos(n):
    assert vpn.nombre_valido(n)


@pytest.mark.parametrize("n", ["", "   ", "a" * 33, "../etc", "a;b", "<script>", "a/b", "móvil😀", "x\ny", None, 5])
def test_nombres_invalidos(n):
    assert not vpn.nombre_valido(n)


def test_limpiar_cliente_no_filtra_claves():
    crudo = {"id": 3, "name": "m", "enabled": True, "ipv4Address": "10.8.0.2", "latestHandshakeAt": None,
             "transferRx": 5, "transferTx": 7, "createdAt": "x", "expiresAt": None,
             "privateKey": "SECRETO", "preSharedKey": "SECRETO2", "publicKey": "PUB"}
    out = vpn.limpiar_cliente(crudo)
    assert "SECRETO" not in str(out) and "SECRETO2" not in str(out) and "PUB" not in str(out)
    assert out["nombre"] == "m" and out["conectado"] is False and out["recibido"] == 5


def test_conectado_por_handshake():
    from datetime import datetime, timedelta, timezone
    ahora = datetime.now(timezone.utc)
    assert vpn._conectado((ahora - timedelta(seconds=30)).isoformat())
    assert not vpn._conectado((ahora - timedelta(minutes=10)).isoformat())
    assert not vpn._conectado(None) and not vpn._conectado("basura")
