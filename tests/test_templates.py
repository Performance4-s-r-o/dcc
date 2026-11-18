"""Každá šablona v templates/ se vyplní příkladovými daty a zvaliduje.

Příklady: tests/examples/_common.json (sdílené hodnoty) a volitelně
tests/examples/<cesta k šabloně>.json (podsložky se zrcadlí) (hodnoty specifické pro šablonu, mají přednost).
Nová šablona se tím validuje automaticky - stačí ji přidat do templates/.
"""
from pathlib import Path

import pytest

from utilities.dcc_template import PLACEHOLDER, fill, load_values, placeholders, validate_text

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "tests" / "examples"
COMMON = EXAMPLES / "_common.json"
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

    filled = fill(text, values)
    assert not PLACEHOLDER.search(filled), "po vyplnění zůstal nevyplněný placeholder"

    errors = validate_text(filled)
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
        assert validate_text(fill(text, broken)), f"validace nechytila rozbitou hodnotu {key}"


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.relative_to(TEMPLATES_DIR).as_posix())
def test_template_specific_example_has_no_stale_keys(template: Path):
    """Klíč ve specifickém JSON, který šablona nepoužívá, značí překlep nebo zastaralá data."""
    specific = example_for(template)
    if not specific.exists():
        return
    stale = load_values(specific).keys() - placeholders(read(template))
    assert not stale, f"nepoužité klíče: {sorted(stale)}"


def test_common_example_has_no_stale_keys():
    """Každý klíč v _common.json musí používat aspoň jedna šablona."""
    used = set().union(*(placeholders(read(t)) for t in TEMPLATES))
    stale = load_values(COMMON).keys() - used
    assert not stale, f"nepoužité klíče v _common.json: {sorted(stale)}"
