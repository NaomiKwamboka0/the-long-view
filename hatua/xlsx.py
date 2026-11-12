"""Read and write simple Excel (.xlsx) sheets with the standard library only.

Schools keep results in Excel, so the school drive accepts .xlsx as well as .csv.
Hatua reads the FIRST sheet: row 1 is the column headings, every row after it is one
result. Nothing here needs Excel, the internet or an extra package.

Safety, because an .xlsx is a zip of XML that someone else made:
* a file that unpacks to more than MAX_UNPACKED bytes is refused (zip bomb);
* XML with a DOCTYPE or ENTITY is refused (entity-expansion tricks);
* formulas are never run: Hatua reads the value Excel last saved, as text.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

MAX_UNPACKED = 20 * 1024 * 1024
MAX_ROWS = 20000
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
BUILTIN_DATE_FORMATS = set(range(14, 23)) | {27, 30, 36, 45, 46, 47, 50, 57}
_CELL = re.compile(r"^([A-Z]+)(\d+)$")


class BadSheet(ValueError):
    """The file is not an Excel sheet Hatua can read."""


def _col(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _letters(index: int) -> str:
    out = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def _xml(z: zipfile.ZipFile, name: str) -> ET.Element | None:
    try:
        raw = z.read(name)
    except KeyError:
        return None
    if b"<!DOCTYPE" in raw or b"<!ENTITY" in raw:
        raise BadSheet("This Excel file has content Hatua does not open. Save it again as .xlsx and retry.")
    try:
        return ET.fromstring(raw)
    except ET.ParseError:
        raise BadSheet("This Excel file is damaged. Open it in Excel, save it again and retry.") from None


def _text(node: ET.Element | None) -> str:
    return "" if node is None else "".join(t.text or "" for t in node.iter(f"{{{NS['m']}}}t"))


def _date_styles(z: zipfile.ZipFile) -> set[int]:
    """Indexes of the cell styles that show a number as a date."""
    styles = _xml(z, "xl/styles.xml")
    if styles is None:
        return set()
    custom = {int(f.get("numFmtId", 0)) for f in styles.findall("m:numFmts/m:numFmt", NS)
              if re.search(r"[dmy]", re.sub(r'"[^"]*"|\[[^\]]*\]', "", f.get("formatCode", "").lower()))}
    return {i for i, xf in enumerate(styles.findall("m:cellXfs/m:xf", NS))
            if int(xf.get("numFmtId", 0)) in BUILTIN_DATE_FORMATS | custom}


def _number(raw: str, as_date: bool) -> str:
    try:
        value = float(raw)
    except ValueError:
        return raw
    if as_date and 1 <= value < 2958466:
        return (date(1899, 12, 30) + timedelta(days=int(value))).isoformat()
    return str(int(value)) if value == int(value) else raw


def _first_sheet(z: zipfile.ZipFile) -> str:
    book, rels = _xml(z, "xl/workbook.xml"), _xml(z, "xl/_rels/workbook.xml.rels")
    if book is None or rels is None:
        raise BadSheet("This is not an Excel (.xlsx) file.")
    sheet = book.find("m:sheets/m:sheet", NS)
    if sheet is None:
        raise BadSheet("This Excel file has no sheet.")
    rid = sheet.get(f"{{{NS['r']}}}id")
    for rel in rels.findall("p:Relationship", NS):
        if rel.get("Id") == rid:
            target = rel.get("Target", "").lstrip("/")
            return target if target.startswith("xl/") else "xl/" + target
    raise BadSheet("This Excel file has no sheet.")


def read_bytes(content: bytes) -> tuple[list[str], list[dict]]:
    """(column headings, rows) from the first sheet. Every value comes back as text."""
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise BadSheet("This is not an Excel (.xlsx) file. Old .xls files must be saved as .xlsx first.") from None
    with z:
        if sum(i.file_size for i in z.infolist()) > MAX_UNPACKED:
            raise BadSheet("This Excel file is too large for Hatua.")
        strings = _xml(z, "xl/sharedStrings.xml")
        shared = [] if strings is None else [_text(si) for si in strings.findall("m:si", NS)]
        dates = _date_styles(z)
        sheet = _xml(z, _first_sheet(z))
        if sheet is None:
            raise BadSheet("This Excel file has no sheet.")
        table: list[dict[int, str]] = []
        for row in sheet.findall("m:sheetData/m:row", NS):
            cells: dict[int, str] = {}
            for i, c in enumerate(row.findall("m:c", NS)):
                m = _CELL.match(c.get("r", ""))
                col = _col(m.group(1)) if m else i
                kind, v = c.get("t", "n"), c.find("m:v", NS)
                if kind == "inlineStr":
                    value = _text(c.find("m:is", NS))
                elif v is None or v.text is None:
                    value = ""
                elif kind == "s":
                    value = shared[int(v.text)] if v.text.isdigit() and int(v.text) < len(shared) else ""
                elif kind == "b":
                    value = "TRUE" if v.text == "1" else "FALSE"
                elif kind in ("str", "e"):
                    value = v.text
                else:
                    value = _number(v.text, int(c.get("s", 0) or 0) in dates)
                cells[col] = value.strip()
            if any(cells.values()):
                table.append(cells)
            if len(table) > MAX_ROWS:
                raise BadSheet(f"This sheet has more than {MAX_ROWS} rows. Split it by term.")
    if not table:
        return [], []
    width = max(table[0]) + 1
    header = [table[0].get(i, "").strip() for i in range(width)]
    rows = [{h: r.get(i, "") for i, h in enumerate(header) if h} for r in table[1:]]
    return [h for h in header if h], rows


def read(path: Path) -> tuple[list[str], list[dict]]:
    return read_bytes(Path(path).read_bytes())


# ---------------------------------------------------------------- writing
_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
          '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
          '</Types>')
_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
         '</Relationships>')
_BOOK_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
              '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
              '</Relationships>')
_STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
           '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
           '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
           '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
           '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
           '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
           '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
           '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
           '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
           '</styleSheet>')
_NUMBER = re.compile(r"^-?\d{1,9}$")


def _cell(ref: str, value, style: int = 0) -> str:
    text = "" if value is None else str(value)
    s = f' s="{style}"' if style else ""
    if not text:
        return ""
    if _NUMBER.match(text) and not (len(text) > 1 and text.lstrip("-").startswith("0")):
        return f'<c r="{ref}"{s}><v>{text}</v></c>'
    return f'<c r="{ref}"{s} t="inlineStr"><is><t xml:space="preserve">{escape(text)}</t></is></c>'


def to_bytes(rows: list[dict], sheet_name: str = "Results", header: list[str] | None = None) -> bytes:
    """One sheet: a bold heading row that stays in view, then one row per result."""
    header = header or (list(rows[0].keys()) if rows else [])
    out = [f'<row r="1">{"".join(_cell(f"{_letters(i)}1", h, 1) for i, h in enumerate(header))}</row>']
    for n, row in enumerate(rows, start=2):
        out.append(f'<row r="{n}">{"".join(_cell(f"{_letters(i)}{n}", row.get(h, "")) for i, h in enumerate(header))}</row>')
    widths = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{max(10, min(34, len(h) + 6))}" customWidth="1"/>'
                     for i, h in enumerate(header))
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
             '</sheetView></sheetViews>'
             f'<cols>{widths}</cols><sheetData>{"".join(out)}</sheetData></worksheet>')
    book = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{escape(sheet_name[:31])}" sheetId="1" r:id="rId1"/></sheets></workbook>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in (("[Content_Types].xml", _TYPES), ("_rels/.rels", _RELS), ("xl/workbook.xml", book),
                           ("xl/_rels/workbook.xml.rels", _BOOK_RELS), ("xl/styles.xml", _STYLES),
                           ("xl/worksheets/sheet1.xml", sheet)):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))  # fixed, so the same rows give the same file
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, body)
    return buf.getvalue()


def write(path: Path, rows: list[dict], sheet_name: str = "Results") -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(to_bytes(rows, sheet_name))
