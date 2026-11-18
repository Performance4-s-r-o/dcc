---
name: dcc-template
description: Vytvoří nebo upraví univerzální DCC (Digital Calibration Certificate, PTB) šablonu s {{placeholdery}} z existujícího kalibračního listu (PDF/Excel) pro daný typ měřidla a zvaliduje ji pytestem proti XSD. Použij při "vytvoř šablonu", "nová šablona DCC", "převeď KL do DCC", "zvaliduj šablony".
---

# DCC šablona z kalibračního listu

Cíl: jedna šablona na **typ měřidla + postup** (ne na zákazníka). Vše, co se mezi
certifikáty liší, je `{{placeholder}}`; vše, co určuje typ měřidla/metody, je napevno.
Šablonu vyplňuje Excel (makro) – proto jen prosté textové dosazení, žádná logika v XML.

## Zdroje pravdy
- XSD: stahuje se automaticky z ptb.de podle `schemaVersion` šablony (včetně SI a xmldsig) do uživatelské cache (`%LOCALAPPDATA%\dcc-schemas`, jinde `~/.cache/dcc-schemas`, přepsat jde `DCC_SCHEMA_CACHE`). Čerstvé stažení = smazat cache. Verze šablon: **3.2.1**
  (nejnovější je 3.3.0, GP příklady PTB jsou na 3.3.0; 3.0.0 je zastaralá). Jiná verze =
  změň `schemaVersion` + `schemaLocation` v šabloně, nic dalšího netřeba.
- Good Practice: https://wiki.dcc.ptb.de/en/gp_home – hotové referenční DCC (teplota:
  gitlab.com/ptb/dcc/dcc-goodpractice/temperature, délka DKD-E 4-3, váhy DKD-E 7-3, vlhkost).
  **Před novým typem měřidla se vždy podívej, jestli GP příklad existuje, a převezmi jeho refTypy a strukturu.**
- refType slovník (`basic_*`, `math_*`, `temperature_*`…): TemaTres DKD
  https://digilab.ptb.de/dkd/refType/vocab/index.php?tema=2 – XSD refType nekontroluje, hlídá se ručně.

## Postup
1. **Rozeber KL na 3 druhy údajů** (tabulka v odpovědi uživateli, než začneš psát XML):
   - *napevno* (typ měřidla/postup): norma, postup, metoda, názvy veličin, jednotky, refTypy, struktura tabulek,
   - *placeholder skalár*: zákazník, identifikace měřidla, data, osoby, podmínky prostředí, texty prohlášení,
   - *placeholder seznam* (tabulky výsledků): jeden `{{..._values}}` = hodnoty oddělené mezerou (`si:realListXMLList`).
2. **Najdi nejbližší existující šablonu** v `templates/` a GP příklad; kopíruj, nepiš od nuly.
3. **Namapuj sekce KL na DCC:**

   | KL | DCC |
   |---|---|
   | Laboratoř, akreditace, pracoviště | `calibrationLaboratory` (+ `calibrationLaboratoryCode`) |
   | Číslo KL, datum vystavení, datum kalibrace, místo | `coreData` (`uniqueIdentifier`, `identifications`, `issueDate`, `beginPerformanceDate`/`endPerformanceDate`, `performanceLocation` – enum: laboratory/customer/…) |
   | Zákazník | `customer` |
   | Měřidlo, výrobce, typ, výr. č., popis, rozsah | `items/item` (`manufacturer`, `model`, `identifications` refType `serialNumber`, `itemQuantities` s `basic_rangeLower/Upper`, `basic_resolution`) |
   | Kalibroval / Schválil | `respPersons` |
   | Návaznost, nejistota (k, p), rozhodovací pravidlo, seřízení, poznámky, závěr | `statements` (`traceable`, `conformity`) |
   | Postup, norma | `measurementResults/usedMethods` |
   | Použité etalony | `measuringEquipments` |
   | Podmínky prostředí/kalibrace (teplota, tlak, vlhkost, proud, ponor…) | `influenceConditions` (refType `basic_temperature`…, jinak `gp_*`) |
   | Tabulka výsledků, nejistota | `results/result/data/list/quantity` + `expandedUncXMLList` |
   | Koeficienty, interpolační rovnice | `result refType="temperature_callendarVanDusenCoefficientsSimple"` apod. |
   | Podpis, razítko | `ds:Signature` (xmldsig, přidává se až při podpisu – v šabloně ne) |
4. **Konvence repa:**
   - placeholder `{{snake_case_anglicky}}`, jednou za význam; stejné jméno = stejná hodnota v celé šabloně,
   - seznamy: `si:valueXMLList` / `si:unitXMLList` / `si:uncertaintyXMLList`, vždy **stejný počet bodů** v jednom `dcc:list`; počet bodů šablonu nemění (5 i 11 bodů = stejná šablona),
   - jednotky **D-SI** (`\percent`, `\degreecelsius`, `\hecto\pascal`, `\mega\pascal`, `\ohm`, `\metre`), nikdy `%`, `°C`, `mm`,
   - jednotka měřené veličiny = `{{measurement_si_unit}}` (jedna šablona pro bar/MPa/kPa),
   - `dcc:content` s `lang=` pro každý jazyk z `usedLangCodeISO639_1` (`mandatoryLang` musí být mezi nimi),
   - `performanceLocation`, `conformity`, `countryCode` jsou enumy/ISO – placeholder musí dostat přesně platnou hodnotu,
   - kdo zákaznicky závisí (např. logo, adresa lab) = placeholder; norma a postup = napevno.
5. **Příklady a test** (povinné, jinak šablona není hotová):
   - sdílené hodnoty jsou v `tests/examples/_common.json`; nové placeholdery přidej tam,
   - hodnoty specifické pro typ do `tests/examples/<název-šablony>.json` (přepisují common),
   - backslash v JSON zdvojit: `"\\gram"`,
   - spuštění: `uv run --with lxml --with pytest pytest -q` (nebo `uv run pytest`).
   Test vyplní placeholdery, zvaliduje XSD + pravidla dobré praxe (`utilities/dcc_template.py`),
   selže při chybějícím příkladu, nevyplněném `{{}}` i zbytečném klíči v JSON.
6. Reálné nové pravidlo, které XSD nechytá, přidej do `practice_errors()` – ne do šablony „ručně“.

## Co XSD ani test nechytí (kontroluj sám)
- význam refTypů (vyhledat v TemaTres), správnost fyziky (znaménko chyby, MPE, k),
- zda číselná pole v Excelu mají tečku jako desetinný oddělovač (`xs:double`!),
- podpis (`ds:Signature`) a PDF/A čitelná verze.

## Pokrytí KL → DCC: příklad Pt100 (ČMI 1033-KL-20089-26)
Pokryto 1:1: laboratoř, č. KL, data, zákazník, měřidlo (výrobce, typ, výr. č., popis), postup `133-MP-C002`, místo,
teplota prostředí (23 ± 3) °C (`basic_temperature` + tolerance), návaznost, nejistota k=2/95 % (EA-4/02),
tabulka t90 [°C] / Rm [Ω] / U [°C] (`basic_referenceValue`, `basic_measuredValue`, `expandedUncXMLList` – **pozor:
nejistota je v °C, měřená hodnota v Ω → jiná jednotka než u sloupce Rm**), kalibroval/schválil.
Pokryto přes GP rozšíření (`gp_*`, převzít z `dcc_gp_temperatur_resistance.xml`): měřicí proud 1 mA / 75 Hz (`gp_current`),
ponor 250 mm (`gp_immersionDepth`), R0/A/B a rovnice `Rt = R0(1 + A·t + B·t²)` (`temperature_callendarVanDusenCoefficientsSimple`, vzorec jako `dcc:formula/dcc:latex`).
Nepokryto strukturou DCC (jde do `statements`/`description` jako text nebo se řeší mimo): „Měřidlo bylo označeno kalibrační značkou“,
logo/ILAC/razítko, „List 1 ze 2“ (nahrazuje DCC jako celek), zákaz rozmnožování (jen text).
Závěr: pro tento typ KL DCC dostačuje; chybí jen typově specifické `gp_*` refTypy, které je potřeba převzít z GP, ne vymýšlet.
