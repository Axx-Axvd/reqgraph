"""Build exporters/templates/reference.docx: the Word styles of the exported documents (T-401).

pandoc's own sample of styles is patched, nothing is laid out by hand (ADR-016): A4 portrait with
margins after GOST 7.32 (left 30 mm, right 15 mm, top and bottom 20 mm), Times New Roman 12 pt,
Russian language, black headings. Run again after changing the constants:

    uv run python scripts/make_reference_docx.py
"""

import io
import re
import subprocess
import zipfile
from pathlib import Path

import pypandoc

OUT = (
    Path(__file__).resolve().parents[1]
    / "packages/core/src/reqgraph/exporters/templates/reference.docx"
)
FONT = "Times New Roman"
SIZE = 24  # half-points: 12 pt
TWIPS_PER_MM = 56.7
PAGE = (11906, 16838)  # A4 in twips
MARGINS = {"top": 20, "right": 15, "bottom": 20, "left": 30}  # mm
SECT_PR = (
    "<w:sectPr>"
    f'<w:pgSz w:w="{PAGE[0]}" w:h="{PAGE[1]}" />'
    "<w:pgMar "
    + " ".join(f'w:{k}="{round(v * TWIPS_PER_MM)}"' for k, v in MARGINS.items())
    + ' w:header="709" w:footer="709" w:gutter="0" />'
    '<w:footnotePr><w:numRestart w:val="eachSect" /></w:footnotePr>'
    "</w:sectPr>"
)


def default_reference() -> bytes:
    pandoc = pypandoc.get_pandoc_path()
    result = subprocess.run(
        [pandoc, "--print-default-data-file", "reference.docx"], capture_output=True, check=True
    )
    return result.stdout


def patch_styles(xml: str) -> str:
    fonts = f'<w:rFonts w:ascii="{FONT}" w:hAnsi="{FONT}" w:eastAsia="{FONT}" w:cs="{FONT}" />'
    xml = re.sub(r"<w:rFonts [^>]*/>", fonts, xml, count=1)  # docDefaults
    xml = re.sub(r'<w:sz w:val="\d+" />', f'<w:sz w:val="{SIZE}" />', xml, count=1)
    xml = re.sub(r'<w:szCs w:val="\d+" />', f'<w:szCs w:val="{SIZE}" />', xml, count=1)
    xml = re.sub(r'<w:lang w:val="[^"]*"', '<w:lang w:val="ru-RU"', xml, count=1)
    xml = re.sub(r"<w:rFonts w:asciiTheme=\"majorHAnsi\"[^>]*/>", fonts, xml)  # headings
    xml = re.sub(r'<w:color w:val="[0-9A-Fa-f]{6}"[^>]*/>', '<w:color w:val="000000" />', xml)
    return xml


def patch_document(xml: str) -> str:
    return re.sub(r"<w:sectPr>.*?</w:sectPr>", SECT_PR, xml, count=1, flags=re.S)


def build(source: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/styles.xml":
                data = patch_styles(data.decode("utf-8")).encode("utf-8")
            elif item.filename == "word/document.xml":
                data = patch_document(data.decode("utf-8")).encode("utf-8")
            info = zipfile.ZipInfo(item.filename, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zout.writestr(info, data)
    return out.getvalue()


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(build(default_reference()))
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
