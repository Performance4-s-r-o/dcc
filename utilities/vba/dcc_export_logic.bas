Attribute VB_Name = "DccExport"
Option Explicit

' =====================================================================
'  DCC export - list Logic
' =====================================================================
Private Const SHEET_NAME As String = "Logic"
Private Const XML_CELL As String = "I16"
Private Const TABLE_NAME As String = "TableHandledVars"
Private Const DCC_NS As String = "https://ptb.de/dcc"
Private Const XSD_PATH As String = ""     ' prazdne = schema z xsi:schemaLocation (stahne se do %TEMP%\dcc_xsd)
                                          ' nebo lokalni cesta, napr. "C:\DCC\xsd\dcc.xsd"
Private Const CAL_SHEET_NAME As String = ""   ' nazev listu s kalibracnim listem; prazdne = najde se 'Kalibracni list' podle vzoru

' =====================================================================
'  TLACITKO 1: validace + ulozeni XML
' =====================================================================
Public Sub ValidovatAUlozitDCC()
    Dim ws As Worksheet, xmlText As String, f As Variant
    Set ws = ThisWorkbook.Worksheets(SHEET_NAME)
    If Not GetValidXml(ws, xmlText) Then Exit Sub

    f = Application.GetSaveAsFilename(InitialFileName:=ThisWorkbook.path & "\" & DefaultBaseName(ws) & ".xml", _
                                      FileFilter:="XML soubory (*.xml), *.xml", Title:="Ulozit DCC XML")
    If VarType(f) = vbBoolean Then Exit Sub

    WriteBytes CStr(f), Utf8Bytes(xmlText)
    MsgBox "XML je validni a bylo ulozeno:" & vbLf & f, vbInformation, "DCC"
End Sub

' =====================================================================
'  TLACITKO 2: XML s vlozenym PDF kalibracniho listu (dcc:document)
' =====================================================================
Public Sub ExportovatXMLsPDF()
    Dim ws As Worksheet, wsCal As Worksheet, xmlText As String
    Dim f As Variant, pdfPath As String, pdfName As String
    Dim b64 As String, frag As String, p As Long, errs As String, xsdUrl As String, doc As Object

    Set ws = ThisWorkbook.Worksheets(SHEET_NAME)
    If Not GetValidXml(ws, xmlText) Then Exit Sub

    If InStr(xmlText, "<dcc:document") > 0 Then
        MsgBox "XML uz obsahuje prvek dcc:document.", vbExclamation, "DCC"
        Exit Sub
    End If

    Set wsCal = FindCalSheet()
    If wsCal Is Nothing Then
        MsgBox "List 'Kalibracni list' nebyl nalezen.", vbCritical, "DCC"
        Exit Sub
    End If

    f = Application.GetSaveAsFilename(InitialFileName:=ThisWorkbook.path & "\" & DefaultBaseName(ws) & ".xml", _
                                      FileFilter:="XML soubory (*.xml), *.xml", Title:="Ulozit DCC XML s PDF")
    If VarType(f) = vbBoolean Then Exit Sub

    ' 1) PDF kalibracniho listu (ulozi se vedle XML)
    pdfPath = Left$(CStr(f), InStrRev(CStr(f), ".") - 1) & ".pdf"
    pdfName = Mid$(pdfPath, InStrRev(pdfPath, "\") + 1)
    wsCal.ExportAsFixedFormat Type:=xlTypePDF, Filename:=pdfPath, Quality:=xlQualityStandard, _
                              IncludeDocProperties:=True, IgnorePrintAreas:=False, OpenAfterPublish:=False

    ' 2) PDF -> base64 -> dcc:document (pred uzaviraci znacku)
    b64 = Base64Encode(ReadBytes(pdfPath))
    frag = "    <dcc:document>" & vbLf & _
           "        <dcc:fileName>" & XmlEsc(pdfName) & "</dcc:fileName>" & vbLf & _
           "        <dcc:mimeType>application/pdf</dcc:mimeType>" & vbLf & _
           "        <dcc:dataBase64>" & b64 & "</dcc:dataBase64>" & vbLf & _
           "    </dcc:document>" & vbLf

    p = InStrRev(xmlText, "</dcc:digitalCalibrationCertificate>")
    If p = 0 Then
        MsgBox "V XML chybi uzaviraci znacka certifikatu.", vbCritical, "DCC"
        Exit Sub
    End If
    xmlText = Left$(xmlText, p - 1) & frag & Mid$(xmlText, p)

    ' 3) Vysledne XML znovu proti schematu
    Set doc = LoadDoc(xmlText)
    If doc Is Nothing Then
        MsgBox "Vysledne XML neni well-formed.", vbCritical, "DCC"
        Exit Sub
    End If
    xsdUrl = ResolveXsd(doc)
    errs = XsdValidate(xmlText, DCC_NS, xsdUrl)
    If Len(errs) > 0 Then
        MsgBox "XML s vlozenym PDF NEODPOVIDA SCHEMATU:" & vbLf & vbLf & errs, vbCritical, "DCC - validace"
        Exit Sub
    End If

    ' 4) Ulozeni
    WriteBytes CStr(f), Utf8Bytes(xmlText)
    MsgBox "Ulozeno:" & vbLf & f & vbLf & "(PDF vlozeno do XML, kopie: " & pdfName & ")", vbInformation, "DCC"
End Sub

' =====================================================================
'  Spolecna validace
' =====================================================================
Private Function GetValidXml(ws As Worksheet, ByRef xmlText As String) As Boolean
    Dim missing As String, p As Long, doc As Object, xsdUrl As String, errs As String

    Application.CalculateFull

    ' 0) vyplnene hodnoty
    missing = MissingVars(ws)
    If Len(missing) > 0 Then
        MsgBox "Nejsou vyplneny tyto promenne:" & vbLf & missing, vbExclamation, "DCC"
        Exit Function
    End If

    xmlText = CStr(ws.Range(XML_CELL).Value)
    If Len(Trim$(xmlText)) = 0 Or Left$(xmlText, 1) = "#" Then
        MsgBox "Bunka " & XML_CELL & " neobsahuje XML (" & Left$(xmlText, 50) & ").", vbCritical, "DCC"
        Exit Function
    End If
    p = InStr(xmlText, "{{")
    If p > 0 Then
        MsgBox "XML obsahuje nenahrazenou promennou:" & vbLf & Mid$(xmlText, p, 60), vbCritical, "DCC"
        Exit Function
    End If

    ' 1) well-formed
    Set doc = CreateObject("MSXML2.DOMDocument.6.0")
    doc.async = False: doc.validateOnParse = False: doc.resolveExternals = False
    doc.SetProperty "ProhibitDTD", True
    If Not doc.LoadXML(xmlText) Then
        With doc.parseError
            MsgBox "XML NENI WELL-FORMED" & vbLf & vbLf & "Chyba: " & .reason & vbLf & _
                   "Radek: " & .Line & ", pozice: " & .linepos, vbCritical, "DCC - validace"
        End With
        Exit Function
    End If

    ' 2) XSD (jako VS Code / Red Hat XML)
    xsdUrl = ResolveXsd(doc)
    If Len(xsdUrl) = 0 Then
        MsgBox "V XML chybi xsi:schemaLocation pro " & DCC_NS & ".", vbCritical, "DCC - validace"
        Exit Function
    End If
    errs = XsdValidate(xmlText, DCC_NS, xsdUrl)
    If Len(errs) > 0 Then
        MsgBox "XML NEODPOVIDA SCHEMATU DCC" & vbLf & "(" & xsdUrl & ")" & vbLf & vbLf & errs, _
               vbCritical, "DCC - validace"
        Exit Function
    End If

    GetValidXml = True
End Function

Private Function LoadDoc(xmlText As String) As Object
    Dim d As Object
    Set d = CreateObject("MSXML2.DOMDocument.6.0")
    d.async = False: d.validateOnParse = False: d.resolveExternals = False
    d.SetProperty "ProhibitDTD", True
    If d.LoadXML(xmlText) Then Set LoadDoc = d
End Function

Private Function ResolveXsd(doc As Object) As String
    If Len(XSD_PATH) > 0 Then ResolveXsd = XSD_PATH Else ResolveXsd = SchemaUrl(doc, DCC_NS)
End Function

' URL schematu pro namespace z xsi:schemaLocation
Private Function SchemaUrl(doc As Object, ns As String) As String
    Dim s As String, parts() As String, i As Long
    s = doc.DocumentElement.getAttribute("xsi:schemaLocation") & ""
    s = Application.WorksheetFunction.Trim(Replace(Replace(Replace(s, vbCr, " "), vbLf, " "), vbTab, " "))
    If Len(s) = 0 Then Exit Function
    parts = Split(s, " ")
    For i = 0 To UBound(parts) - 1 Step 2
        If parts(i) = ns Then SchemaUrl = parts(i + 1): Exit Function
    Next
End Function

' Validace proti XSD; vrati seznam chyb (prazdny = OK)
Private Function XsdValidate(xmlText As String, ns As String, xsdUrl As String) As String
    Dim cache As Object, d As Object, e As Object, x As Object, res As String, n As Long
    Dim localXsd As String, stepTxt As String

    On Error GoTo SchemaErr
    stepTxt = "stazeni schematu"
    If LCase$(Left$(xsdUrl, 4)) = "http" Then
        localXsd = LocalSchema(xsdUrl)
    Else
        localXsd = xsdUrl
    End If

    stepTxt = "nacteni schematu (" & localXsd & ")"
    Set cache = CreateObject("MSXML2.XMLSchemaCache.6.0")
    cache.Add ns, localXsd
    On Error GoTo 0

    Set d = CreateObject("MSXML2.DOMDocument.6.0")
    d.async = False: d.validateOnParse = False: d.resolveExternals = False
    d.SetProperty "ProhibitDTD", True
    d.SetProperty "MultipleErrorMessages", True
    Set d.Schemas = cache
    d.LoadXML xmlText

    Set e = d.Validate()
    If e.ErrorCode = 0 Then Exit Function

    On Error Resume Next
    For Each x In e.allErrors
        n = n + 1
        res = res & n & ") " & Trim$(Replace(x.reason, vbCrLf, " ")) & vbLf & _
                    "    -> " & x.errorXPath & vbLf
        If n >= 8 Then res = res & "...": Exit For
    Next
    On Error GoTo 0
    If n = 0 Then res = Trim$(e.reason) & vbLf & "    -> " & e.errorXPath
    XsdValidate = res
    Exit Function

SchemaErr:
    XsdValidate = "Chyba pri kroku '" & stepTxt & "': " & Err.Description & vbLf & vbLf & _
                  "Tip: smazte slozku " & SchemaFolder() & " a zkuste to znovu."
End Function

' =====================================================================
'  Lokalni kopie XSD (vcetne importu) v %TEMP%\dcc_xsd
' =====================================================================
Private Function SchemaFolder() As String
    SchemaFolder = Environ$("TEMP") & "\dcc_xsd\"
End Function

Private Function LocalSchema(url As String) As String
    Dim visited As Object
    If Dir$(SchemaFolder(), vbDirectory) = "" Then MkDir SchemaFolder()
    Set visited = CreateObject("Scripting.Dictionary")
    LocalSchema = FetchSchema(url, visited)
End Function

Private Function FetchSchema(url As String, visited As Object) As String
    Dim localPath As String, http As Object, d As Object, nodes As Object, nd As Object
    Dim childUrl As String, childLocal As String, outText As String

    If visited.Exists(url) Then FetchSchema = visited(url): Exit Function
    localPath = SchemaFolder() & UrlToFileName(url)
    visited.Add url, localPath

    If Dir$(localPath) <> "" Then FetchSchema = localPath: Exit Function   ' uz stazeno

    Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
    http.Open "GET", url, False
    http.setRequestHeader "User-Agent", "Excel-DCC-Validator"
    http.send
    If http.Status <> 200 Then Err.Raise vbObjectError + 1, , "HTTP " & http.Status & " pro " & url

    Set d = CreateObject("MSXML2.DOMDocument.6.0")
    d.async = False: d.validateOnParse = False: d.resolveExternals = False
    d.SetProperty "ProhibitDTD", False          ' napr. xmldsig schema obsahuje DOCTYPE
    If Not d.LoadXML(http.responseText) Then
        Err.Raise vbObjectError + 2, , "Neplatne XSD " & url & ": " & d.parseError.reason
    End If
    d.SetProperty "SelectionNamespaces", "xmlns:xs='http://www.w3.org/2001/XMLSchema'"

    Set nodes = d.SelectNodes("//xs:import[@schemaLocation] | //xs:include[@schemaLocation] | //xs:redefine[@schemaLocation]")
    For Each nd In nodes
        childUrl = ResolveUrl(url, nd.getAttribute("schemaLocation"))
        childLocal = FetchSchema(childUrl, visited)
        nd.setAttribute "schemaLocation", Mid$(childLocal, InStrRev(childLocal, "\") + 1)
    Next

    ' ulozit bez DOCTYPE (MSXML6 DTD ve schematech nepovoluje)
    outText = "<?xml version=""1.0"" encoding=""UTF-8""?>" & vbLf & d.DocumentElement.XML
    WriteBytes localPath, Utf8Bytes(outText)
    FetchSchema = localPath
End Function

Private Function UrlToFileName(url As String) As String
    Dim s As String, i As Long, ch As String, r As String
    s = url
    If InStr(s, "://") > 0 Then s = Mid$(s, InStr(s, "://") + 3)
    For i = 1 To Len(s)
        ch = Mid$(s, i, 1)
        If ch Like "[A-Za-z0-9.-]" Then r = r & ch Else r = r & "_"
    Next
    If LCase$(Right$(r, 4)) <> ".xsd" Then r = r & ".xsd"
    UrlToFileName = r
End Function

Private Function ResolveUrl(baseUrl As String, ByVal rel As String) As String
    Dim baseDir As String
    If rel Like "http*://*" Then ResolveUrl = rel: Exit Function
    baseDir = Left$(baseUrl, InStrRev(baseUrl, "/"))
    If Left$(rel, 1) = "/" Then
        ResolveUrl = Left$(baseUrl, InStr(InStr(baseUrl, "://") + 3, baseUrl, "/") - 1) & rel
        Exit Function
    End If
    Do
        If Left$(rel, 2) = "./" Then
            rel = Mid$(rel, 3)
        ElseIf Left$(rel, 3) = "../" Then
            rel = Mid$(rel, 4)
            baseDir = Left$(baseDir, InStrRev(baseDir, "/", Len(baseDir) - 1))
        Else
            Exit Do
        End If
    Loop
    ResolveUrl = baseDir & rel
End Function

' =====================================================================
'  Kontrola vyplnenych hodnot
' =====================================================================
Private Function MissingVars(ws As Worksheet) As String
    Dim lo As ListObject, i As Long, v As Variant, res As String, n As Long
    Set lo = ws.ListObjects(TABLE_NAME)
    For i = 1 To lo.ListRows.Count
        v = lo.ListColumns("Values").DataBodyRange.Cells(i, 1).Value
        If IsError(v) Then
            res = res & "- " & lo.ListColumns("VarNames").DataBodyRange.Cells(i, 1).Value & " (chyba)" & vbLf: n = n + 1
        ElseIf Len(Trim$(CStr(v))) = 0 Then
            res = res & "- " & lo.ListColumns("VarNames").DataBodyRange.Cells(i, 1).Value & vbLf: n = n + 1
        End If
        If n >= 20 Then res = res & "...": Exit For
    Next i
    MissingVars = res
End Function

' =====================================================================
'  Pomocne funkce
' =====================================================================
Private Function FindCalSheet() As Worksheet
    Dim sh As Worksheet
    If Len(CAL_SHEET_NAME) > 0 Then
        On Error Resume Next
        Set FindCalSheet = ThisWorkbook.Worksheets(CAL_SHEET_NAME)
        On Error GoTo 0
        Exit Function
    End If
    For Each sh In ThisWorkbook.Worksheets
        If LCase$(sh.Name) Like "kalibra*list" Then Set FindCalSheet = sh: Exit Function
    Next
End Function

Private Function DefaultBaseName(ws As Worksheet) As String
    DefaultBaseName = "DCC_" & SafeName(LookupVar(ws, "serial_number")) & "_" & _
                      SafeName(LookupVar(ws, "calibration_end_date"))
End Function

Private Function LookupVar(ws As Worksheet, varName As String) As String
    On Error Resume Next
    Dim lo As ListObject, r As Variant
    Set lo = ws.ListObjects(TABLE_NAME)
    r = Application.Match(varName, lo.ListColumns("VarNames").DataBodyRange, 0)
    If Not IsError(r) Then LookupVar = CStr(lo.ListColumns("Values").DataBodyRange.Cells(r, 1).Value)
End Function

Private Function SafeName(ByVal s As String) As String
    Dim c As Variant
    For Each c In Array("\", "/", ":", "*", "?", """", "<", ">", "|", " ", "&")
        s = Replace(s, c, "_")
    Next
    If Len(s) = 0 Then s = "bez"
    SafeName = s
End Function

Private Function XmlEsc(ByVal s As String) As String
    s = Replace(s, "&", "&amp;")
    s = Replace(s, "<", "&lt;")
    s = Replace(s, ">", "&gt;")
    XmlEsc = s
End Function

Private Function Base64Encode(b() As Byte) As String
    Dim d As Object, el As Object
    Set d = CreateObject("MSXML2.DOMDocument.6.0")
    Set el = d.createElement("b64")
    el.DataType = "bin.base64"
    el.nodeTypedValue = b
    Base64Encode = Replace(Replace(el.text, vbLf, ""), vbCr, "")
End Function

Private Function Utf8Bytes(text As String) As Byte()
    Dim st As Object
    Set st = CreateObject("ADODB.Stream")
    st.Type = 2: st.Charset = "utf-8": st.Open
    st.WriteText text
    st.Position = 0: st.Type = 1: st.Position = 3   ' bez BOM
    Utf8Bytes = st.Read
    st.Close
End Function

Private Function ReadBytes(path As String) As Byte()
    Dim fh As Integer, b() As Byte
    fh = FreeFile
    Open path For Binary Access Read As #fh
    ReDim b(0 To LOF(fh) - 1)
    Get #fh, , b
    Close #fh
    ReadBytes = b
End Function

Private Sub WriteBytes(path As String, b() As Byte)
    Dim fh As Integer
    If Dir$(path) <> "" Then Kill path
    fh = FreeFile
    Open path For Binary Access Write As #fh
    Put #fh, , b
    Close #fh
End Sub

