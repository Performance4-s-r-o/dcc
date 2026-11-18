"""Vyplnění {{placeholderů}} v DCC šabloně příkladovými daty a validace.

Validace má tři vrstvy:
  1. XSD (DCC + D-SI + xmldsig, stahuje se z ptb.de do uživatelské cache, dál offline),
  2. kontroly dobré praxe, které XSD nepokrývá (D-SI jednotky, délky XMLList, jazyky),
  3. kontrola, že v šabloně nezůstal nevyplněný placeholder a v datech nic navíc.
"""
import json
import os
import re
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
NS = {
    "dcc": "https://ptb.de/dcc",
    "si": "https://ptb.de/si",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
}
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")

# D-SI: sekvence \prefix\jednotka\tothe{n}, nebo \one; % a "°C" tam nepatří
DSI_UNIT = re.compile(r"^(\\[a-zA-Z]+(\\tothe\{-?\d+(\.\d+)?\})?)+$")


def placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def load_values(common: Path, *specific: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in (common, *specific):
        if path.exists():
            values.update(json.loads(path.read_text(encoding="utf-8")))
    return values


def fill(text: str, values: dict[str, str]) -> str:
    """Dosadí hodnoty (XML-escapované). Neznámý placeholder vyhodí KeyError."""
    return PLACEHOLDER.sub(lambda m: escape(str(values[m.group(1)])), text)


def _cache_dir() -> Path:
    """Uživatelská cache schémat (přežije mezi běhy i repy); jde přepsat DCC_SCHEMA_CACHE."""
    if env := os.environ.get("DCC_SCHEMA_CACHE"):
        return Path(env)
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "dcc-schemas"


def _download(url: str, cache: Path) -> Path:
    """Stáhne XSD (pokud není v cache) včetně importů a přepíše jejich schemaLocation na lokální soubory."""
    target = cache / re.sub(r"[^A-Za-z0-9._-]", "_", url.split("://", 1)[-1])
    if target.exists():
        return target
    with urllib.request.urlopen(url, timeout=30) as resp:
        tree = etree.fromstring(resp.read())
    for node in tree.iter("{http://www.w3.org/2001/XMLSchema}import", "{http://www.w3.org/2001/XMLSchema}include"):
        loc = node.get("schemaLocation", "")
        if loc.startswith("http"):
            node.set("schemaLocation", _download(loc, cache).name)
    cache.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    tmp.write_bytes(etree.tostring(tree, xml_declaration=True, encoding="UTF-8"))
    tmp.replace(target)  # atomicky, aby přerušené stažení nezůstalo v cache
    return target


def schema_for(version: str) -> etree.XMLSchema:
    xsd = _download(f"https://ptb.de/dcc/v{version}/dcc.xsd", _cache_dir())
    return etree.XMLSchema(etree.parse(str(xsd)))


def schema_version(doc: etree._ElementTree) -> str:
    return doc.getroot().get("schemaVersion")


def xsd_errors(doc: etree._ElementTree) -> list[str]:
    schema = schema_for(schema_version(doc))
    schema.validate(doc)
    return [f"řádek {e.line}: {e.message}" for e in schema.error_log]


def practice_errors(doc: etree._ElementTree) -> list[str]:
    """Pravidla dobré praxe nad rámec XSD."""
    errors: list[str] = []
    root = doc.getroot()

    # schemaVersion musí odpovídat xsi:schemaLocation
    loc = root.get(f"{{{NS['xsi']}}}schemaLocation", "")
    if f"/v{root.get('schemaVersion')}/" not in loc:
        errors.append(f"schemaVersion={root.get('schemaVersion')} nesedí s xsi:schemaLocation '{loc}'")

    # jednotky v D-SI
    for unit in root.iter(f"{{{NS['si']}}}unit", f"{{{NS['si']}}}unitXMLList"):
        for u in (unit.text or "").split():
            if not DSI_UNIT.match(u):
                errors.append(rf"řádek {unit.sourceline}: jednotka '{u}' není D-SI (např. \percent, \metre, \kilo\gram)")

    # mandatoryLang musí být v usedLang
    used = {e.text for e in root.iterfind(".//dcc:usedLangCodeISO639_1", NS)}
    mandatory = {e.text for e in root.iterfind(".//dcc:mandatoryLangCodeISO639_1", NS)}
    if not mandatory <= used:
        errors.append(f"mandatoryLangCode {mandatory} není v usedLangCode {used}")

    # v jednom dcc:list / dcc:data musí mít všechny XMLList stejný počet bodů
    for container in root.iter(f"{{{NS['dcc']}}}list", f"{{{NS['dcc']}}}data"):
        counts = {}
        for q in container.iterfind("dcc:quantity", NS):
            v = q.find(".//si:valueXMLList", NS)
            if v is not None:
                counts[q.findtext("dcc:name/dcc:content", namespaces=NS)] = len((v.text or "").split())
        if len(set(counts.values())) > 1:
            errors.append(f"řádek {container.sourceline}: různý počet bodů v listu: {counts}")

    # neprázdné povinné texty
    for tag in ("calibrationLaboratoryCode", "uniqueIdentifier", "issueDate"):
        for e in root.iterfind(f".//dcc:{tag}", NS):
            if not (e.text or "").strip():
                errors.append(f"řádek {e.sourceline}: prázdné dcc:{tag}")
    return errors


def validate_text(xml_text: str) -> list[str]:
    try:
        doc = etree.ElementTree(etree.fromstring(xml_text.encode("utf-8")))
    except etree.XMLSyntaxError as e:
        return [f"XML není well-formed: {e}"]
    return xsd_errors(doc) + practice_errors(doc)
