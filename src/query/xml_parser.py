"""
ECG XML analysis result → structured query.

Assumed XML schema (vendor-agnostic minimal structure):

<ECGReport>
  <Measurements>
    <HeartRate unit="bpm">75</HeartRate>
    <PRInterval unit="ms">160</PRInterval>
    <QRSDuration unit="ms">88</QRSDuration>
    <QTcInterval unit="ms">420</QTcInterval>
  </Measurements>
  <Interpretations>
    <Finding>Normal sinus rhythm</Finding>
  </Interpretations>
  <Diagnoses>
    <Diagnosis>Atrial Fibrillation</Diagnosis>
  </Diagnoses>
</ECGReport>

Fields are parsed leniently — missing elements are silently skipped.
PatientInfo elements are intentionally ignored to avoid handling PHI.
"""

from dataclasses import dataclass, field
from lxml import etree


_NORMAL_RANGES = {
    "HeartRate":   (60, 100),
    "PRInterval":  (120, 200),
    "QRSDuration": (70, 110),
    "QTcInterval": (350, 450),
}


@dataclass
class ECGQueryContext:
    diagnoses: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)
    abnormal_params: list[str] = field(default_factory=list)
    natural_query: str = ""


def parse_xml(xml_source: str | bytes) -> ECGQueryContext:
    """
    Parse ECG XML and return an ECGQueryContext for RAG retrieval.
    xml_source can be raw XML string/bytes or a file path string.
    """
    ctx = ECGQueryContext()

    try:
        if isinstance(xml_source, bytes) or (
            isinstance(xml_source, str) and xml_source.strip().startswith("<")
        ):
            raw = xml_source if isinstance(xml_source, bytes) else xml_source.encode()
            root = etree.fromstring(raw)
        else:
            root = etree.parse(str(xml_source)).getroot()
    except etree.XMLSyntaxError as e:
        raise ValueError(f"Invalid ECG XML: {e}") from e

    for el in root.iter("Diagnosis"):
        if el.text and el.text.strip():
            ctx.diagnoses.append(el.text.strip())

    for el in root.iter("Finding"):
        if el.text and el.text.strip():
            ctx.findings.append(el.text.strip())

    for param, (lo, hi) in _NORMAL_RANGES.items():
        el = root.find(f".//{param}")
        if el is None or not el.text:
            continue
        try:
            val = float(el.text.strip())
        except ValueError:
            continue
        unit = el.get("unit", "")
        label = f"{param} {val:.0f}{unit}"
        if val < lo:
            ctx.abnormal_params.append(f"{label} (low)")
        elif val > hi:
            ctx.abnormal_params.append(f"{label} (high)")

    ctx.natural_query = _build_query(ctx)
    return ctx


def _build_query(ctx: ECGQueryContext) -> str:
    parts = []
    if ctx.diagnoses:
        parts.append(" ".join(ctx.diagnoses))
    if ctx.findings:
        parts.append(" ".join(ctx.findings))
    if ctx.abnormal_params:
        parts.append(" ".join(ctx.abnormal_params))
    parts.append("ECG diagnosis criteria clinical significance")
    return " ".join(parts)
