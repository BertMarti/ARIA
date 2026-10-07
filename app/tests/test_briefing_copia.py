import json
from datetime import datetime, timedelta, timezone

from aria import briefing, config


def test_ultima_copia_desde_archivo_de_estado(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "COPIAS_REPO", str(tmp_path / "no-existe"))
    assert briefing.ultima_copia() == {"disponible": False}
    t = datetime.now(timezone.utc) - timedelta(hours=3)
    (tmp_path / "ultima-copia.json").write_text(json.dumps({"fecha": t.isoformat(), "archivo": "x.gpg"}))
    r = briefing.ultima_copia()
    assert r["disponible"] and not r["antigua"] and "3 h" in r["hace"]
    (tmp_path / "ultima-copia.json").write_text("{roto")
    assert briefing.ultima_copia() == {"disponible": False}
