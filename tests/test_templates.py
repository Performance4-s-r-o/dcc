"""Každá šablona v templates/ se vyplní příkladovými daty a zvaliduje.

Příklady: tests/examples/_common.json (sdílené hodnoty) a volitelně
tests/examples/<cesta k šabloně>.json (podsložky se zrcadlí) (hodnoty specifické pro šablonu, mají přednost).
Nová šablona se tím validuje automaticky - stačí ji přidat do templates/.
"""
from pathlib import Path

import pytest

from utilities.dcc_template import (LEGACY_RULES, PLACEHOLDER, drop_legacy_errors, load_values, placeholders, render,
                                    repeat_placeholders, validate_text)

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "tests" / "examples"
COMMON = EXAMPLES / "_common.json"

# Dvojice, které jsou záměrně shodné (rozdíl je jen v počtu bodů, ne ve struktuře).
KNOWN_DUPLICATES = {frozenset({"váha-neuautomatická-pm-5-bodů.xml", "váha-neuautomatická-pm-11-bodů.xml"})}
TEMPLATES_DIR = ROOT / "templates"
TEMPLATES = sorted(TEMPLATES_DIR.rglob("*.xml"))


def read(template: Path) -> str:
    return template.read_text(encoding="utf-8")


def example_for(template: Path) -> Path:
    """templates/a/b.xml -> tests/examples/a/b.json (struktura složek se zrcadlí)."""
    return EXAMPLES / template.relative_to(TEMPLATES_DIR).with_suffix(".json")


def values_for(template: Path) -> dict[str, str]:
    return load_values(COMMON, example_for(template))


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.relative_to(TEMPLATES_DIR).as_posix())
def test_template_validates_with_example_data(template: Path):
    text = read(template)
    values = values_for(template)

    missing = placeholders(text) - values.keys()
    assert not missing, f"chybí příkladová data pro: {sorted(missing)}"
    for block, names in repeat_placeholders(text).items():
        rows = values.get("_repeat", {}).get(block)
        assert rows, f"chybí řádky opakovaného bloku '{block}' (klíč _repeat)"
        for i, row in enumerate(rows, 1):
            assert not names - row.keys(), f"blok '{block}', řádek {i}: chybí {sorted(names - row.keys())}"

    filled = render(text, values)
    assert not PLACEHOLDER.search(filled), "po vyplnění zůstal nevyplněný placeholder"

    errors = validate_text(filled)
    errors = drop_legacy_errors(errors, template.name)
    assert not errors, "\n".join(errors)


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.relative_to(TEMPLATES_DIR).as_posix())
def test_validation_rejects_bad_data(template: Path):
    """Kontrola, že validace není prázdná: rozbitá data musí vyvolat chybu."""
    text = read(template)
    values = values_for(template)
    victims = [k for k in ("issue_date", "reference_values", "measurement_si_unit") if k in placeholders(text)]
    assert victims, "šablona nemá žádný z klíčů použitelných pro negativní test"
    for key in victims:
        broken = {**values, key: "rozbito"}
        assert validate_text(render(text, broken)), f"validace nechytila rozbitou hodnotu {key}"


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.relative_to(TEMPLATES_DIR).as_posix())
def test_template_specific_example_has_no_stale_keys(template: Path):
    """Klíč ve specifickém JSON, který šablona nepoužívá, značí překlep nebo zastaralá data."""
    specific = example_for(template)
    if not specific.exists():
        return
    data = load_values(specific)
    text = read(template)
    stale = data.keys() - placeholders(text) - {"_repeat"}
    assert not stale, f"nepoužité klíče: {sorted(stale)}"
    blocks = repeat_placeholders(text)
    for block, rows in data.get("_repeat", {}).items():
        assert block in blocks, f"šablona nemá opakovaný blok '{block}'"
        for i, row in enumerate(rows, 1):
            assert not row.keys() - blocks[block], f"blok '{block}', řádek {i}: nepoužité klíče {sorted(row.keys() - blocks[block])}"


def test_common_example_has_no_stale_keys():
    """Každý klíč v _common.json musí používat aspoň jedna šablona."""
    used = set().union(*(placeholders(read(t)) for t in TEMPLATES))
    stale = load_values(COMMON).keys() - used
    assert not stale, f"nepoužité klíče v _common.json: {sorted(stale)}"


GAUGE_BLOCKS = TEMPLATES_DIR / "koncové-měrky-ISO-3650.xml"


@pytest.mark.parametrize("count", [1, 3, 7])
def test_repeat_block_expands_one_item_and_result_per_row(count):
    """Opakovaný blok: každý řádek dat = jedna podpoložka Item_i a jeden výsledek s refId na ni."""
    import re

    values = values_for(GAUGE_BLOCKS)
    row = values["_repeat"]["gauge_block"][0]
    values = {**values, "_repeat": {"gauge_block": [row] * count}}
    xml = render(read(GAUGE_BLOCKS), values)
    assert re.findall(r'<dcc:item id="(Item_\d+)"', xml) == [f"Item_{i}" for i in range(1, count + 1)]
    assert re.findall(r'<dcc:result refId="(Item_\d+)"', xml) == [f"Item_{i}" for i in range(1, count + 1)]
    assert not validate_text(xml)


def test_dangling_refid_is_reported():
    """XSD neexistující odkaz refId nehlídá – hlídá ho practice_errors."""
    xml = render(read(GAUGE_BLOCKS), values_for(GAUGE_BLOCKS)).replace('refId="Item_1"', 'refId="Item_99"')
    assert any("Item_99" in e for e in validate_text(xml))


def test_repeat_block_without_rows_fails():
    values = {k: v for k, v in values_for(GAUGE_BLOCKS).items() if k != "_repeat"}
    with pytest.raises(KeyError):
        render(read(GAUGE_BLOCKS), values)


def test_every_template_has_placeholders():
    """Soubor bez {{placeholderů}} není šablona, ale vyplněný certifikát (např. staré manometrTP*, mikrometr*)."""
    for template in TEMPLATES:
        text = read(template)
        assert placeholders(text) or repeat_placeholders(text), f"{template.name}: žádný placeholder – není to šablona"


def test_no_unexpected_duplicate_templates():
    """Dvě stejné šablony = zbytečná údržba; výjimky jsou v KNOWN_DUPLICATES."""
    import re

    seen: dict[str, str] = {}
    for template in TEMPLATES:
        key = re.sub(r"\s+", "", read(template))
        if key in seen and frozenset({seen[key], template.name}) not in KNOWN_DUPLICATES:
            pytest.fail(f"{template.name} je shodná s {seen[key]}")
        seen.setdefault(key, template.name)


def test_legacy_list_has_no_fixed_templates():
    """Až se legacy šablona opraví, musí se vyřadit ze seznamu LEGACY_RULES (jinak se pravidla obcházejí zbytečně)."""
    for name in LEGACY_RULES:
        template = TEMPLATES_DIR / name
        text = read(template)
        values = values_for(template)
        errors = validate_text(render(text, values))
        assert any(e.startswith("refType bez předpony") or "bez atributu lang" in e for e in errors), \
            f"{name} už pravidla splňuje – odeber ho z LEGACY_RULES"
