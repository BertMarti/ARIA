"""Extractor mínimo para PDF ejecutado en un proceso con límites."""
import json
import sys

from pypdf import PdfReader


def main() -> None:
    if len(sys.argv) != 2:
        raise ValueError("Falta el archivo PDF")
    reader = PdfReader(sys.argv[1], strict=False)
    paginas = []
    for numero, pagina in enumerate(reader.pages, 1):
        paginas.append({"pagina": numero, "texto": pagina.extract_text() or ""})
    sys.stdout.write(json.dumps(paginas, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"error": str(exc)[:200]}, ensure_ascii=False))
        raise
