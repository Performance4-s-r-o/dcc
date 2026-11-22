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

## Excel: list Logic (načtení šablony z GitHubu a vyplnění)
Každý sešit s KL dostane list **Logic**: `I3` = odkaz na šablonu v repu (`blob/main/templates/…`, diakritika v URL
musí být procentově zakódovaná), `I1` ji načte přes `WEBSERVICE`, tabulka `TableHandledVars` (sloupce VarNames, Values,
XmlValue) mapuje každý `{{placeholder}}` na buňky sešitu, `I2` je skládá (`REDUCE`/`SUBSTITUTE`), `I16` je výsledné XML,
`I15` stav („Připraveno“). Makra (`utilities/vba/dcc_export_logic.bas`) čtou právě tuto strukturu.
- Hotový builder listu: `utilities/excel_logic.py` (`build_logic`); mapování je slovník `placeholder → vzorec`,
  skript odmítne běh, pokud se jeho klíče liší od placeholderů šablony.
- Nová šablona se musí nejdřív **pushnout na GitHub main**, jinak `I1` hlásí `#VALUE!`.
- Čísla do XML převádět `SUBSTITUTE(x&"",",",".")`, data `YEAR()&"-"&TEXT(MONTH(),"00")&…` (ne `TEXT(x,"yyyy-mm-dd")` –
  v české verzi je `rrrr`), seznamy `TEXTJOIN(" ",TRUE,rozsah)`, čísla z textu `NUMBERVALUE(text,".")`.
- Přes COM: tabulku plnit s vypnutým `AutoCorrect.AutoFillFormulasInLists` (jinak se vzorec z posledního řádku roztáhne
  do celého sloupce); do cizího sešitu přidávat list s **manuálním výpočtem** a `CalculateBeforeSave=False`, jinak se
  přepočtou UDF/`CELL("filename")` a změní se uložené hodnoty původních listů.

### Povinná kontrola po každé úpravě Excelu (skripty se vždy ověřují)
Skript, který sešit generuje nebo mění, je kód jako každý jiný: **nikdy ho nepovažuj za hotový, dokud neprošly všechny body**.
Výsledek ověřuj z **uloženého souboru**, ne z živého Excelu (ten může ukazovat jiný stav než disk).
1. **Před úpravou**: zazálohuj aktuální soubor (uživatel ho mohl mezitím znovu uložit/pushnout – vždy vycházej z aktuální verze,
   ne ze své starší zálohy) a zkontroluj, že sešit není otevřený v Excelu; chráněné zobrazení: `ProtectedViewWindows(1).Edit()`.
2. **Mapování**: `build_logic` selže, pokud se klíče mapování liší od placeholderů šablony – nepřeskakovat.
3. **Logic funguje**: všechny řádky ✔, žádná hodnota `#…`/prázdná, `I15` = „Připraveno“; před pushem šablony ji do `I1`
   dočasně vlož lokálně, po testu **vrať vzorec `WEBSERVICE`**.
4. **XML validní**: XML z `I16` projde `validate_text` (XSD + pravidla praxe) – nestačí, že Excel hlásí „Připraveno“.
5. **Makra**: modul v sešitu musí být shodný s `.bas` z repa; makro otestuj bez dialogů přes dočasnou funkci
   (vložit celý kód + wrapper, spustit, pak modul **celý přepsat zpět** – `AddFromString` do neprázdného modulu vkládá kód
   na začátek, mazání podle čísel řádků pak smaže jiný kód). Nepoužívat `VBComponents.Remove` na modul s kódem.
   `CAL_SHEET_NAME` nastavit, pokud list s KL není „Kalibrační list“.
6. **Cizí sešit**: přidávat list s manuálním výpočtem, po uložení vrátit `calcPr` (bez `calcCompleted`/`calcOnSave`/`calcMode`).
7. **Vzhled**: export listu KL do PDF a prohlédnout stránky (počet stran, zlomy, oříznutí).
8. **Nezávislá kontrola uloženého souboru**:
   `uv run --with openpyxl python utilities/verify_excel_dcc.py SESIT.xlsm templates/<šablona>.xml --macros [--original ZALOHA.xlsm]`
   (tabulka proměnných, složení + validace XML z uložených hodnot, makra, `calcPr`, a že se na ostatních listech nezměnila
   žádná hodnota). Návratový kód musí být 0.
9. **Úklid**: zavřít jen sešity/instance, které jsem otevřel já (nikdy „zavřít všechny“), bez zbytků `~$…` a dočasných souborů v repu.
10. **Nahlásit**: co je ověřeno, co ne (např. makro s dialogy, nepushnutá šablona) a co zůstává ručně doplnit („DOPLNIT“).

## Opakované bloky (REPEAT) – když GP chce prvek na každý objekt (např. koncová měrka)
Když GP vyžaduje samostatný prvek na každý kus (sada koncových měrek: `dcc:item` + `dcc:subItems`, výsledky po měrce přes
`refId`), počet kusů se mezi certifikáty mění, takže jej nejde vyjádřit seznamem placeholderů. Šablona proto obsahuje
**opakovaný blok**:
```xml
<!-- REPEAT gauge_block -->
<dcc:item id="Item_{{block_no}}" refType="length_gaugeBlock"> … {{nominal_length_mm}} … </dcc:item>
<!-- /REPEAT gauge_block -->
```
- stejný název bloku může být v šabloně víckrát (položky v `administrativeData` i výsledky v `measurementResults`) – rozbalí se
  stejnými řádky; `{{block_no}}` doplní rozbalení samo (1, 2, …), ostatní placeholdery bloku bere z řádku,
- příklad: `"_repeat": {"gauge_block": [ {řádek}, {řádek}, … ]}` v `tests/examples/<šablona>.json`; test hlídá, že každý
  řádek má všechny placeholdery bloku a žádný navíc,
- rozbalení dělá `utilities/dcc_template.py` (`render`/`expand`); **list Logic v Excelu ho zatím neumí** – pro takovou šablonu
  je potřeba druhá tabulka (řádek = měrka) a rozbalení fragmentu vzorcem; do té doby ji Excel naplnit nedokáže,
- ID a odkazy musí být jednoznačné a existující: duplicitní `id` zachytí XSD, **neexistující `refId` zachytí až naše pravidlo
  v `practice_errors()`** (libxml2 odkazy IDREFS nekontroluje),
- schéma: `subItems` a metadata podle GP vyžadují **3.3.0** (`schemaVersion="3.3.0"`, SI 2.2.1 – nejistota
  `si:measurementUncertaintyUnivariate/si:expandedMU`, ne `si:expandedUnc` z 3.2.1); stáhne se samo.
- popisky (`dcc:content lang="cs"`) musí být v jazyce, který `lang` uvádí – pevné popisky v nových šablonách jsou česky.

## Co hlídá kód (a co zůstává na tobě)
Každé opakované selhání dostalo kontrolu v kódu, ne jen zápis v textu. Tohle už **vynucují testy** (`uv run pytest`):
- jednotky D-SI (ne `%`, `°C`), stejný počet bodů v seznamech, `schemaVersion` = `schemaLocation`, `mandatoryLang` v `usedLang`,
- každý `refId` odkazuje na existující `id` (XSD to nehlídá), žádné duplicitní `id`,
- **každý `refType` má předponu slovníku** (`basic_…`, `length_…`, `gp_…`) a **každé `dcc:content` má `lang`**,
- soubor bez `{{placeholderů}}` není šablona (vyplněná instance neprojde), dvě shodné šablony neprojdou (výjimky `KNOWN_DUPLICATES`),
- kontrola, že validace není prázdná (rozbitá data musí selhat), a že každý příklad má všechny placeholdery i opakované bloky.

`LEGACY_RULES` (v `utilities/dcc_template.py`) = šablony starší než pravidla refType/lang; ty jsou z těchto dvou pravidel
vyňaty, **nová šablona tam nesmí přibýt**. Po opravě šablony řádek odeber (test `test_legacy_list_has_no_fixed_templates`
selže, dokud tam zůstane opravená šablona).

Excel: `utilities/verify_excel_dcc.py` navíc hlídá roztažený vzorec v tabulce Logic (4 a více proměnných se stejným vzorcem),
nezměněné původní listy, makra a `calcPr`.

**Nelze automatizovat – kontroluj sám:** že popisek je opravdu v jazyce z `lang` (anglický text s `lang="cs"` projde),
význam refTypů a existence termínu v TemaTres mimo větev `basic` (`basic_resolution`, `basic_rangeLower/Upper` jsou neověřené),
věcnou správnost fyziky a příkladových čísel, a to, že GP příklad pro daný obor existuje.
