import struct

from aria import voz


def wav(amplitud: int, n: int = 16000) -> bytes:
    return b"\0" * 44 + struct.pack(f"<{n}h", *([amplitud, -amplitud] * (n // 2)))


def test_muletillas_de_whisper_se_descartan():
    for t in ("Gracias.", "¡Gracias!", "Subtítulos realizados por la comunidad de Amara.org", "  ", "Suscríbete"):
        assert voz.es_alucinacion(t, wav(3000)), t


def test_frase_corta_con_audio_casi_mudo_se_descarta_pero_no_con_voz():
    assert voz.es_alucinacion("Vale.", wav(20))
    assert not voz.es_alucinacion("Vale.", wav(3000))
    assert not voz.es_alucinacion("¿Qué tiempo hará mañana en Madrid?", wav(20))   # frase larga: se respeta
