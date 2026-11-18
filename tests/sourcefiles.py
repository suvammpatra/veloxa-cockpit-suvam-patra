"""Builders for synthetic source files. Not Veloxa data: names, figures and dates
exist only to exercise the parsers and rules. Layouts mirror the real exports
(a title line above the header row, UTC timestamps, initials as assignees)."""

from __future__ import annotations

import io
import zipfile
from email.message import EmailMessage
from pathlib import Path

import openpyxl


def xlsx(path: Path, sheets: dict[str, tuple[str | None, list[str], list[list]]]) -> Path:
    """sheets: name -> (title line or None, header, rows)."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, (title, header, rows) in sheets.items():
        ws = wb.create_sheet(name)
        if title:
            ws.append([title])
        ws.append(header)
        for r in rows:
            ws.append(r)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path


def csv_file(path: Path, header: list[str], rows: list[list]) -> Path:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    return path


def pdf(path: Path, pages: list[str]) -> Path:
    import pymupdf as fitz

    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_text((72, 72), text, fontsize=11)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(doc.tobytes())
    doc.close()
    return path


def docx(path: Path, paragraphs: list[str]) -> Path:
    from xml.sax.saxutils import escape

    body = "".join(f'<w:p><w:r><w:t xml:space="preserve">{escape(p, {chr(34): "&quot;"})}</w:t></w:r></w:p>'
                   for p in paragraphs)
    xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           f"<w:body>{body}</w:body></w:document>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        z.writestr("word/document.xml", xml)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())
    return path


def eml(path: Path, *, sender: str, to: str, subject: str, date: str | None, body: str) -> Path:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = sender, to, subject
    if date:
        m["Date"] = date
    m.set_content(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(m.as_bytes())
    return path


KEKA_HEADER = ["Emp ID", "Full Name", "Work Email", "Department", "Title", "Manager ID",
               "Join Date", "Location", "Status", "Exit Date"]


def keka(path: Path, rows: list[list], exported: str = "31-Oct-2026") -> Path:
    title = f"HRMS export, employees only. Exported {exported}." if exported else "HRMS export, employees only."
    return xlsx(path, {"Employees": (title, KEKA_HEADER, rows)})


def staff_rows() -> list[list]:
    """Five synthetic employees: a lead, two engineers sharing initials MK, and two others."""
    return [
        ["T001", "Lena Ortiz", "lena@example.test", "Leadership", "Chief", None, "2020-01-01", "City", "Active", None],
        ["T002", "Mira Kale", "mira@example.test", "Engineering", "Engineer", "T001", "2021-01-01", "City", "Active", None],
        ["T003", "Mohan Kale", "mohan@example.test", "Engineering", "Engineer", "T001", "2021-06-01", "City", "Active", None],
        ["T004", "Rina Shah", "rina.s@example.test", "Engineering", "SRE", "T001", "2022-01-01", "City", "Active", None],
        ["T005", "Dev Patel", "dev@example.test", "Sales", "Seller", "T001", "2023-01-01", "City", "Notice period", "2026-10-31"],
    ]
