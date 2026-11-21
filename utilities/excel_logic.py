"""Společné pomůcky pro tvorbu sešitů DCC přes COM: styly a list Logic (bez Pythonu v Excelu)."""
import re
from pathlib import Path
from urllib.parse import quote

BLUE, YELLOW, HDR, GRAY, GREEN_F, GREEN_B = 16711680, 13431551, 15917529, 15921906, 3960832, 14348258
GITHUB_TEMPLATES = "https://github.com/Performance4-s-r-o/dcc/blob/main/templates/"
REPO_VBA = Path(r"C:\Users\micha\p4\ocml\dcc\utilities\vba\dcc_export_logic.bas")


def style(rng, size=9, bold=False, color=0, fill=None, wrap=False, halign=None, italic=False, valign=-4108):
    rng.Font.Name = "Arial"
    rng.Font.Size = size
    rng.Font.Bold = bold
    rng.Font.Italic = italic
    rng.Font.Color = color
    if fill is not None:
        rng.Interior.Color = fill
    rng.WrapText = wrap
    rng.VerticalAlignment = valign
    if halign:
        rng.HorizontalAlignment = halign


def template_names(path: Path):
    return sorted(set(re.findall(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}", path.read_text(encoding="utf-8"))))


def template_url(path: Path):
    return GITHUB_TEMPLATES + quote(path.name)


def macro_code(cal_sheet=None):
    """Kód modulu DccExport z repa; cal_sheet = název listu s KL (jinak se hledá 'Kalibrační list' podle vzoru)."""
    code = REPO_VBA.read_bytes().decode("ascii").replace("\r\n", "\n")
    code = "\n".join(l for l in code.split("\n") if not l.startswith("Attribute VB_"))
    if cal_sheet:
        old = 'Private Const CAL_SHEET_NAME As String = ""'
        assert old in code
        code = code.replace(old, f'Private Const CAL_SHEET_NAME As String = "{cal_sheet}"')
    return code


def add_macro(wb, ws, button_row, cal_sheet=None):
    """Vloží modul DccExport do (prázdného) modulu a pod tabulku dvě tlačítka. Nepřepočítává sešit."""
    vbp = wb.VBProject
    for c in vbp.VBComponents:
        if c.Name == "DccExport":
            raise SystemExit("Modul DccExport už v sešitu je – nejdřív ho odstraňte ručně.")
    mod = vbp.VBComponents.Add(1)
    mod.Name = "DccExport"
    mod.CodeModule.AddFromString(macro_code(cal_sheet))
    top = ws.Range(f"A{button_row}").Top
    for i, (cap, macro) in enumerate([("Validovat a uložit XML", "ValidovatAUlozitDCC"),
                                      ("Uložit XML s PDF KL", "ExportovatXMLsPDF")]):
        b = ws.Buttons().Add(ws.Range("A1").Left + 5 + i * 190, top, 180, 24)
        b.Name = f"btnDcc{i + 1}"
        b.Caption = cap
        b.OnAction = macro


def build_logic(xl, wb, template: Path, mapping_fn, title, extras=(), with_macro=False, after=None, cal_sheet=None):
    """Vytvoří list Logic. mapping_fn(X) -> {placeholder: vzorec}; X[klíč] = adresa doplňujícího vstupu."""
    names = template_names(template)
    ws = wb.Worksheets.Add()
    ws.Name = "Logic"
    ws.Move(None, wb.Worksheets(after) if after else wb.Worksheets(wb.Worksheets.Count))
    xl.ScreenUpdating = False
    xl.AutoCorrect.AutoFillFormulasInLists = False   # jinak Excel roztáhne vzorec z posledního řádku do celého sloupce tabulky
    n = len(names)
    last = 7 + n

    # doplňující ruční vstupy (hodnoty, které sešit nezná)
    X = {}
    erow = 19
    for key, label, value in extras:
        X[key] = f"$I${erow}"
        erow += 1
    mapping = mapping_fn(X)
    missing = [k for k in names if k not in mapping]
    extra = [k for k in mapping if k not in names]
    if missing or extra:
        raise SystemExit(f"Mapování nesedí se šablonou. CHYBÍ: {missing} NAVÍC: {extra}")

    ws.Cells.Font.Name = "Arial"
    ws.Cells.Font.Size = 10
    for col, wd in zip("ABCDEFGHI", [34, 12, 40, 44, 44, 30, 3, 34, 70]):
        ws.Columns(col).ColumnWidth = wd
    ws.Range("A1").Value = title
    ws.Range("A1").Font.Bold = True
    ws.Range("A1").Font.Size = 14
    ws.Range("A2").Value = "1. Odkaz na šablonu je v I3 (GitHub); šablona se načte do I1 sama."
    ws.Range("A3").Value = "2. Zkontrolujte sloupec F – vše musí být ✔ (ruční vstupy jsou žluté v I19 a níž)."
    ws.Range("A4").Value = "3. Když I15 hlásí „Připraveno“, zkopírujte XML z I16" + (" nebo použijte tlačítka pod tabulkou." if with_macro else ".")

    ws.Range("H1").Value = "Šablona XML:"
    ws.Range("H2").Value = "Mezivýpočet (doplnění):"
    ws.Range("H3").Value = "Odkaz na šablonu:"
    ws.Range("H4").Value = "Šablona načtena:"
    ws.Range("I3").Value = template_url(template)
    ws.Range("I1").Formula2 = ('=WEBSERVICE(SUBSTITUTE(SUBSTITUTE(I3,"https://github.com/",'
                               '"https://raw.githubusercontent.com/"),"/blob/","/"))')
    ws.Range("I4").Formula2 = '=IF(ISERROR(I1),"CHYBA – šablona nenačtena","šablona načtena ("&COUNTIF(A8:A200,"?*")&" proměnných)")'
    for a in ("H1", "H2", "H3", "H4", "H15", "H16"):
        ws.Range(a).Font.Bold = True
    style(ws.Range("I3"), 10, False, BLUE, YELLOW)
    ws.Range("I1:I2").Interior.Color = GRAY
    ws.Range("I1:I4").WrapText = False
    ws.Range("I1:I4").VerticalAlignment = -4160
    ws.Range("I1:I4").HorizontalAlignment = -4131

    # tabulka proměnných
    ws.Range("A6").Value = "① Proměnné v šabloně"
    ws.Range("C6").Value = "② Hodnoty proměnných (TableHandledVars)"
    for a in ("A6", "C6"):
        ws.Range(a).Font.Bold = True
    ws.Range("A7").Value = "VarNames"
    ws.Range("B7").Value = "Má hodnotu?"
    ws.Range("C7").Value = "VarNames"
    ws.Range("D7").Value = "Values"
    ws.Range("E7").Value = "XmlValue"
    ws.Range("F7").Value = "Stav v šabloně"
    ws.Range("A8").Formula2 = '=LET(p,TEXTSPLIT(I1,"{{"),n,TEXTBEFORE(DROP(p,0,1),"}}"),SORT(UNIQUE(TOCOL(n))))'
    lo = ws.ListObjects.Add(1, ws.Range(f"C7:E{last}"), None, 1)
    lo.Name = "TableHandledVars"
    lo.TableStyle = "TableStyleLight1"
    for i, nm in enumerate(names):
        r = 8 + i
        ws.Range(f"C{r}").Value = nm
        d = ws.Range(f"D{r}")
        d.NumberFormat = "General"
        d.Formula2 = mapping[nm]
        d.Font.Color = GREEN_F
        d.Interior.Color = GREEN_B
        ws.Range(f"E{r}").Formula = (f'=IF(D{r}="","",SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(IF(ISNUMBER(D{r}),'
                                     f'SUBSTITUTE(D{r}&"",",","."),D{r}&""),"&","&amp;"),"<","&lt;"),">","&gt;"))')
        ws.Range(f"F{r}").Formula = (f'=IF(C{r}="","",IF(COUNTIF($A$8:$A$200,C{r})=0,"– nepotřeba (není v šabloně)",'
                                     f'IF(TRIM(D{r}&"")="","✘ chybí hodnota","✔")))')
    for r in range(8, 8 + max(n, 70)):
        ws.Range(f"B{r}").Formula = f'=IF(A{r}="","",IF(COUNTIF(TableHandledVars[VarNames],A{r})>0,"✔","✘ chybí"))'
    ws.Range("I2").Formula2 = ('=IF(ISERROR(I1),"",REDUCE(I1,SEQUENCE(ROWS(TableHandledVars[VarNames])),'
                               'LAMBDA(a,i,SUBSTITUTE(a,"{{"&INDEX(TableHandledVars[VarNames],i)&"}}",INDEX(TableHandledVars[XmlValue],i)))))')
    ws.Range("A7:F7").Font.Bold = True
    ws.Range("A7:B7").Interior.Color = HDR
    ws.Range("F7").Interior.Color = HDR

    ws.Range("H15").Value = "Stav:"
    ws.Range("H16").Value = "Výsledné XML (zkopírujte):"
    ws.Range("I15").Formula2 = ('=IF(ISERROR(I1),"CHYBA: šablona se nenačetla z GitHubu (odkaz v I3, internet)",'
                                'IF(ISNUMBER(SEARCH("{{",I2)),"CHYBA: proměnná ze šablony chybí v tabulce",'
                                'IF(SUMPRODUCT(--(TableHandledVars[XmlValue]=""))>0,'
                                '"Nejsou vyplněna všechna pole: "&SUMPRODUCT(--(TableHandledVars[XmlValue]=""))&" ×","Připraveno")))')
    ws.Range("I16").Formula2 = "=I2"
    ws.Range("I15:I16").WrapText = False
    ws.Range("I15:I16").VerticalAlignment = -4160
    ws.Range("I15:I16").HorizontalAlignment = -4131

    ws.Range("H18").Value = "Doplňující vstupy (ručně) – hodnoty, které sešit neobsahuje"
    ws.Range("H18").Font.Bold = True
    for i, (key, label, value) in enumerate(extras):
        r = 19 + i
        ws.Range(f"H{r}").Value = label
        c = ws.Range(f"I{r}")
        c.Value = value
        style(c, 10, False, BLUE, YELLOW, halign=-4131)

    if with_macro:
        add_macro(wb, ws, last + 3, cal_sheet)
    xl.AutoCorrect.AutoFillFormulasInLists = True
    xl.ScreenUpdating = True
    return ws, names
