"""Los widgets de Android solo pueden usar clases que admite RemoteViews: con otra (p. ej. un <View>), Android
enseña «No se puede cargar el widget» y no hay ningún error en la app que lo delate."""
import xml.etree.ElementTree as ET
from pathlib import Path

LAYOUTS = Path(__file__).resolve().parents[2] / "movil" / "aria" / "android" / "app" / "src" / "main" / "res" / "layout"
PERMITIDAS = {"FrameLayout", "LinearLayout", "RelativeLayout", "GridLayout", "TextView", "ImageView", "ImageButton",
              "Button", "ProgressBar", "TextClock", "AnalogClock", "Chronometer", "ListView", "GridView", "StackView",
              "ViewFlipper", "AdapterViewFlipper"}


def test_layouts_de_widgets_solo_usan_vistas_permitidas():
    archivos = sorted(LAYOUTS.glob("aria_widget*.xml"))
    assert len(archivos) >= 4
    for archivo in archivos:
        for nodo in ET.parse(archivo).iter():
            assert nodo.tag in PERMITIDAS, f"{archivo.name}: <{nodo.tag}> no se puede usar en un widget"
