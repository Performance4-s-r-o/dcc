"""Nezávislá kontrola sešitu s listem Logic – čte ULOŽENÝ soubor (ne živý Excel).

Použití:
    uv run --with openpyxl python utilities/verify_excel_dcc.py SESIT.xlsm templates/sablona.xml [--original ZALOHA.xlsm]

Kontroluje:
  1. všechny placeholdery šablony mají řádek v tabulce Logic a hodnotu bez chyby (#NAME?, #VALUE!, prázdné),
  2. z uložených hodnot (sloupec XmlValue) se složí XML a zvaliduje se proti XSD + pravidlům dobré praxe,
  3. makra: jsou v souboru a tlačítka na ně ukazují (jen pokud sešit makra má mít – přepínač --macros),
  4. calcPr v souboru není ve stavu „manual“ / „calcCompleted=0“,
  5. s --original: na ostatních listech se nezměnila žádná uložená hodnota (přidání Logic nesmí nic přepsat).
Návratový kód 0 = vše v pořádku, 1 = nalezen problém.
"""
import argparse
import re
import sys
import warnings
import zipfile
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utilities.dcc_template import PLACEHOLDER, drop_legacy_errors, validate_text  # noqa: E402

warnings.simplefilter("ignore")
problems: list[str] = []


def fail(msg: str):
    problems.append(msg)
    print("  ✘", msg)


def ok(msg: str):
    print("  ✔", msg)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("workbook")
    ap.add_argument("template")
    ap.add_argument("--original", help="záloha původního sešitu pro porovnání ostatních listů")
    ap.add_argument("--macros", action="store_true", help="sešit musí obsahovat makro DccExport a tlačítka")
    a = ap.parse_args()
    wb_path, tpl_path = Path(a.workbook), Path(a.template)

    print(f"Sešit: {wb_path.name}\nŠablona: {tpl_path.name}")
    wb = openpyxl.load_workbook(wb_path, data_only=True, keep_vba=True)
    if "Logic" not in wb.sheetnames:
        fail("v sešitu chybí list Logic")
        return 1
    ws = wb["Logic"]

    print("1) tabulka proměnných")
    tpl_text = tpl_path.read_text(encoding="utf-8")
    tpl_names = set(PLACEHOLDER.findall(tpl_text))
    rows = {}
    r = 8
    while ws.cell(r, 3).value:
        rows[str(ws.cell(r, 3).value)] = (ws.cell(r, 4).value, ws.cell(r, 5).value)
        r += 1
    if tpl_names - rows.keys():
        fail(f"v tabulce chybí: {sorted(tpl_names - rows.keys())}")
    if rows.keys() - tpl_names:
        fail(f"v tabulce přebývá (není v šabloně): {sorted(rows.keys() - tpl_names)}")
    for name, (val, xmlv) in rows.items():
        if val is None or str(val).strip() == "" or str(val).startswith("#") or xmlv is None or str(xmlv).startswith("#"):
            fail(f"{name}: hodnota je prázdná nebo chybová ({val!r})")
    # roztažený vzorec: Excel při psaní do tabulky přes COM může zkopírovat vzorec jednoho řádku do celého sloupce
    wbf = openpyxl.load_workbook(wb_path, keep_vba=True)
    wsf = wbf["Logic"]
    forms: dict[str, list[str]] = {}
    for r2 in range(8, 8 + len(rows)):
        f = wsf.cell(r2, 4).value
        forms.setdefault(str(f), []).append(str(wsf.cell(r2, 3).value))
    for f, names in forms.items():
        if len(names) >= 4:
            fail(f"{len(names)} proměnných má shodný vzorec ({f[:60]}…) – pravděpodobně roztažený vzorec: {names[:4]}")
    todo = [n for n, (v, _) in rows.items() if str(v).strip().upper() == "DOPLNIT"]
    if todo:
        print("  !", f"ruční hodnota „DOPLNIT“ u: {todo}")
    if not [p for p in problems if "tabulce" in p or "hodnota" in p]:
        ok(f"{len(rows)} proměnných, všechny mají hodnotu")

    print("2) XML složené z uložených hodnot")
    xml = tpl_text
    for name, (_, xmlv) in rows.items():
        xml = xml.replace("{{" + name + "}}", "" if xmlv is None else str(xmlv))
    left = PLACEHOLDER.findall(xml)
    if left:
        fail(f"po vyplnění zůstaly placeholdery: {sorted(set(left))}")
    errs = drop_legacy_errors(validate_text(xml), tpl_path.name)
    if errs:
        for e in errs[:8]:
            fail("validace: " + e[:200])
    else:
        ok("XSD + pravidla dobré praxe bez chyb")
    cached = ws["I16"].value
    if isinstance(cached, str) and cached.startswith("<?xml"):
        ok("v souboru je uložené i XML z listu Logic (I16)")
    else:
        print("  !", f"I16 není uložené XML ({str(cached)[:40]!r}) – normální, dokud šablona není na GitHubu main")

    with zipfile.ZipFile(wb_path) as z:
        names = z.namelist()
        wbxml = z.read("xl/workbook.xml").decode("utf-8")
        has_macro_bin = "xl/vbaProject.bin" in names
        blob = b"".join(z.read(n) for n in names if n.startswith("xl/drawings/") or n.startswith("xl/worksheets/"))
    print("3) makra")
    if a.macros:
        if not has_macro_bin:
            fail("v souboru není vbaProject.bin (uloženo jako .xlsx?)")
        elif b"ValidovatAUlozitDCC" not in blob:
            fail("tlačítka na listu Logic nejsou navázaná na makro ValidovatAUlozitDCC")
        else:
            ok("makro a tlačítka jsou v souboru")
    else:
        print("  – kontrola maker vypnuta (--macros)")

    print("4) nastavení výpočtu")
    calc = re.findall(r"<calcPr[^>]*>", wbxml)
    if any('calcMode="manual"' in c or 'calcCompleted="0"' in c for c in calc):
        fail(f"calcPr je v nežádoucím stavu: {calc}")
    else:
        ok(f"calcPr v pořádku: {calc}")

    if a.original:
        print("5) původní listy beze změny")
        orig = openpyxl.load_workbook(a.original, data_only=True, keep_vba=True)
        total = diff = 0
        examples = []
        for name in orig.sheetnames:
            if name == "Logic":          # list Logic se smí měnit (to je účel úpravy)
                continue
            if name not in wb.sheetnames:
                fail(f"list {name} z originálu v sešitu chybí")
                continue
            for row in orig[name].iter_rows():
                for c in row:
                    if c.value is None:
                        continue
                    total += 1
                    v2 = wb[name][c.coordinate].value
                    same = v2 == c.value or (isinstance(c.value, (int, float)) and isinstance(v2, (int, float))
                                             and abs(v2 - c.value) <= 1e-9 * max(1, abs(c.value)))
                    if not same:
                        diff += 1
                        if len(examples) < 8:
                            examples.append((name, c.coordinate, str(c.value)[:40], str(v2)[:40]))
        if diff:
            fail(f"změněno {diff} z {total} uložených hodnot na původních listech, např. {examples}")
        else:
            ok(f"všech {total} hodnot na původních listech je beze změny")

    print("\nVÝSLEDEK:", "VŠE V POŘÁDKU" if not problems else f"{len(problems)} problémů")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
