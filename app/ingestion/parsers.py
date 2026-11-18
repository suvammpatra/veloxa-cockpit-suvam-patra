"""Deterministic parsers, one per file type (ARCHITECTURE.md 5, Parse stage).

Each parser turns a file into citable units. Every unit has a locator: a sheet
and row, a page, a paragraph, or the email message. Parsers never interpret
meaning; they only split and label. Problems inside a file are returned as
(locator, message) pairs so the pipeline can log them; a file that cannot be
opened at all raises ParseFailure.
"""

from __future__ import annotations

import csv
import email
import html
import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from email import policy
from pathlib import Path

SUPPORTED = {".csv", ".xlsx", ".pdf", ".docx", ".eml", ".txt"}


class ParseFailure(Exception):
    """The file as a whole cannot be read."""


@dataclass
class Unit:
    locator: str
    content: str
    fields: dict[str, object] | None = None  # table rows only: header -> cell
    sheet: str | None = None


@dataclass
class ParsedFile:
    units: list[Unit] = field(default_factory=list)
    problems: list[tuple[str | None, str, str]] = field(default_factory=list)  # locator, severity, message
    titles: dict[str, str] = field(default_factory=dict)  # sheet -> title line above the header
    headers: dict[str, dict[str, str]] = field(default_factory=dict)  # email headers
    text: str = ""  # all text, for file-level date rules

    def warn(self, locator, message):
        self.problems.append((locator, "warning", message))

    def error(self, locator, message):
        self.problems.append((locator, "error", message))


def parse(path: Path, data: bytes) -> ParsedFile:
    if not data:
        raise ParseFailure("The file is empty.")
    ext = path.suffix.lower()
    try:
        return {".csv": _csv, ".xlsx": _xlsx, ".pdf": _pdf, ".docx": _docx,
                ".eml": _eml, ".txt": _txt}[ext](data)
    except ParseFailure:
        raise
    except Exception as exc:  # noqa: BLE001 - any library failure means unreadable
        raise ParseFailure(f"Could not read {ext} file: {type(exc).__name__}: {exc}") from exc


def _cell(value) -> object:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ") if value.time() != datetime.min.time() else value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def row_content(fields: dict[str, object]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in fields.items() if v not in (None, ""))


def _headers(raw: list[object]) -> list[str]:
    names, seen = [], set()
    for i, h in enumerate(raw, start=1):
        name = str(h).strip() if h not in (None, "") else f"Column {i}"
        while name in seen:
            name += f" ({i})"
        seen.add(name)
        names.append(name)
    return names


def _decode(data: bytes, parsed: ParsedFile) -> str:
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        parsed.warn(None, "Not valid UTF-8; read as Windows-1252.")
        return data.decode("cp1252", errors="replace")


# ---------------------------------------------------------------- tables

def _csv(data: bytes) -> ParsedFile:
    parsed = ParsedFile()
    text = _decode(data, parsed)
    rows = list(csv.reader(io.StringIO(text)))
    rows_with_data = [(i, r) for i, r in enumerate(rows, start=1) if any(c.strip() for c in r)]
    if not rows_with_data:
        raise ParseFailure("The CSV file has no rows.")
    (_, header), body = rows_with_data[0], rows_with_data[1:]
    names = _headers(header)
    for line_no, r in body:
        loc = f"row {line_no}"
        if len(r) != len(names):
            parsed.error(loc, f"Expected {len(names)} columns, found {len(r)}; row kept as text only.")
            parsed.units.append(Unit(locator=loc, content=", ".join(r)))
            continue
        fields = {n: _cell(v) for n, v in zip(names, r)}
        parsed.units.append(Unit(locator=loc, content=row_content(fields), fields=fields))
    parsed.text = text
    return parsed


def _xlsx(data: bytes) -> ParsedFile:
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    except zipfile.BadZipFile as exc:
        raise ParseFailure("Not a valid .xlsx file (the archive is damaged).") from exc
    parsed = ParsedFile()
    texts = []
    for ws in wb.worksheets:
        rows = [(i, list(r)) for i, r in enumerate(ws.iter_rows(values_only=True), start=1)
                if any(c not in (None, "") for c in r)]
        if not rows:
            parsed.warn(ws.title, "Sheet is empty.")
            continue
        # A title line above the header has a single filled cell (e.g. the Keka export note).
        title_parts, header_at = [], None
        for idx, (_, r) in enumerate(rows):
            if sum(c not in (None, "") for c in r) >= 2:
                header_at = idx
                break
            title_parts.append(str(next(c for c in r if c not in (None, ""))).strip())
        if title_parts:
            parsed.titles[ws.title] = " ".join(title_parts)
            texts.extend(title_parts)
        if header_at is None:
            parsed.warn(ws.title, "No header row found; title kept, no rows read.")
            continue
        names = _headers(rows[header_at][1])
        for row_no, r in rows[header_at + 1:]:
            fields = {n: _cell(v) for n, v in zip(names, r)}
            extra = [c for c in r[len(names):] if c not in (None, "")]
            loc = f"{ws.title}!row {row_no}"
            if extra:
                parsed.warn(loc, f"{len(extra)} cell(s) beyond the header were ignored.")
            parsed.units.append(Unit(locator=loc, content=row_content(fields), fields=fields, sheet=ws.title))
    wb.close()
    parsed.text = "\n".join(texts)
    return parsed


# ---------------------------------------------------------------- documents

def _pdf(data: bytes) -> ParsedFile:
    import pymupdf as fitz

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise ParseFailure("Not a readable PDF.") from exc
    if doc.needs_pass:
        raise ParseFailure("The PDF is password-protected.")
    parsed = ParsedFile()
    texts = []
    for i, page in enumerate(doc, start=1):
        text = page.get_text().strip()
        if not text:
            parsed.warn(f"page {i}", "Page has no text layer (it may be a scanned image); nothing extracted.")
            continue
        texts.append(text)
        parsed.units.append(Unit(locator=f"page {i}", content=text))
    doc.close()
    if not parsed.units:
        raise ParseFailure("No text could be extracted from any page.")
    parsed.text = "\n".join(texts)
    return parsed


_W_P = re.compile(r"<w:p[ >].*?</w:p>|<w:p/>", re.S)
_W_RUN = re.compile(r"<w:t(?: [^>]*)?>([^<]*)</w:t>|<w:(tab|br|cr)/>")


def _docx(data: bytes) -> ParsedFile:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
        xml = zf.read("word/document.xml").decode("utf-8")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ParseFailure("Not a valid .docx file (no readable document body).") from exc
    parsed = ParsedFile()
    texts, n = [], 0
    for para in _W_P.findall(xml):
        parts = []
        for t, ctrl in _W_RUN.findall(para):
            parts.append(t if not ctrl else ("\t" if ctrl == "tab" else "\n"))
        text = html.unescape("".join(parts)).strip()
        if not text:
            continue
        n += 1
        texts.append(text)
        parsed.units.append(Unit(locator=f"para {n}", content=text))
    if not parsed.units:
        raise ParseFailure("The document has no text.")
    parsed.text = "\n".join(texts)
    return parsed


def _eml(data: bytes) -> ParsedFile:
    msg = email.message_from_bytes(data, policy=policy.default)
    if not any(msg.get(h) for h in ("From", "Subject", "Date")):
        raise ParseFailure("No email headers found (From, Subject or Date).")
    parsed = ParsedFile()
    for h in ("From", "To", "Cc", "Subject", "Date", "Message-ID", "In-Reply-To"):
        if msg.get(h):
            parsed.headers[h] = str(msg.get(h))
    body_part = msg.get_body(preferencelist=("plain", "html"))
    body = ""
    if body_part is not None:
        body = body_part.get_content()
        if body_part.get_content_type() == "text/html":
            body = html.unescape(re.sub(r"<[^>]+>", " ", body))
    else:
        parsed.warn("body", "No text body found.")
    attachments = [p.get_filename() for p in msg.iter_attachments() if p.get_filename()]
    head = "\n".join(f"{k}: {v}" for k, v in parsed.headers.items() if k in ("From", "To", "Cc", "Subject", "Date"))
    content = head + "\n\n" + body.strip()
    if attachments:
        content += "\n\nAttachments (not ingested): " + ", ".join(attachments)
        parsed.warn("attachments", f"{len(attachments)} attachment(s) listed but not ingested.")
    parsed.units.append(Unit(locator="message", content=content))
    parsed.text = content
    return parsed


def _txt(data: bytes) -> ParsedFile:
    parsed = ParsedFile()
    text = _decode(data, parsed)
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        raise ParseFailure("The text file has no content.")
    for i, p in enumerate(paras, start=1):
        parsed.units.append(Unit(locator=f"para {i}", content=p))
    parsed.text = text
    return parsed
