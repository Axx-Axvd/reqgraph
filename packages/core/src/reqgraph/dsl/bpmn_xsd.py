"""Validation of BPMN XML against the official OMG XSD BPMN 2.0 (files in xsd/, base of SCH-001)."""

from functools import cache
from pathlib import Path

from lxml import etree

XSD_DIR = Path(__file__).resolve().parent / "xsd"


@cache
def _schema() -> etree.XMLSchema:
    # parsing from the file keeps its location: imports of BPMNDI, DC and DI resolve next to it
    return etree.XMLSchema(etree.parse(str(XSD_DIR / "BPMN20.xsd")))


def validate_bpmn(xml: str | bytes) -> list[str]:
    """Errors as «строка N: причина»; an empty list means the document is valid."""
    data = xml.encode("utf-8") if isinstance(xml, str) else xml
    try:
        document = etree.fromstring(data)
    except etree.XMLSyntaxError as exc:
        return [f"строка {exc.lineno}: XML не разобран: {exc.msg}"]
    schema = _schema()
    if schema.validate(document):
        return []
    return [f"строка {e.line}: {e.message}" for e in schema.error_log]
