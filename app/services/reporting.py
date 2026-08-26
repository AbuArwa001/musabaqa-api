"""
Reporting service — XlsxWriter-based exports.

1. print_ready_report   — customizable columns, grouped
2. power_bi_export      — multi-sheet fact + dimension tables
3. granular_export      — raw student data with optional presigned URLs + photos
"""

import io
import logging
from datetime import date

import xlsxwriter

logger = logging.getLogger(__name__)


def _add_header_row(ws, headers: list[str], bold_fmt) -> None:
    for col, h in enumerate(headers):
        ws.write(0, col, h, bold_fmt)


def generate_print_ready_report(
    students: list[dict],
    columns: list[str],
    group_by: str | None = None,
) -> bytes:
    """
    columns: subset of ["category", "region", "institution", "age",
                        "registration_date", "phone", "review_status"]
    group_by: "region" | "category" | None
    """
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    bold = wb.add_format({"bold": True})

    if group_by:
        groups: dict[str, list[dict]] = {}
        for s in students:
            key = s.get(group_by, "Unknown")
            groups.setdefault(key, []).append(s)
        for group_key, rows in groups.items():
            ws = wb.add_worksheet(str(group_key)[:31])  # XlsxWriter max sheet name length
            _add_header_row(ws, columns, bold)
            for row_idx, row in enumerate(rows, start=1):
                for col_idx, col in enumerate(columns):
                    ws.write(row_idx, col_idx, row.get(col, ""))
    else:
        ws = wb.add_worksheet("Students")
        _add_header_row(ws, columns, bold)
        for row_idx, row in enumerate(students, start=1):
            for col_idx, col in enumerate(columns):
                ws.write(row_idx, col_idx, row.get(col, ""))

    wb.close()
    return buf.getvalue()


def generate_power_bi_export(
    students: list[dict],
    regions: list[dict],
    categories: list[dict],
    rounds: list[dict],
) -> bytes:
    """Multi-sheet XlsxWriter: Students (fact) + Regions, Categories, Rounds (dims)."""
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    bold = wb.add_format({"bold": True})
    date_fmt = wb.add_format({"num_format": "yyyy-mm-dd"})

    def write_sheet(name: str, data: list[dict]) -> None:
        ws = wb.add_worksheet(name)
        if not data:
            return
        headers = list(data[0].keys())
        _add_header_row(ws, headers, bold)
        for row_idx, row in enumerate(data, start=1):
            for col_idx, key in enumerate(headers):
                val = row.get(key)
                if isinstance(val, date):
                    ws.write_datetime(row_idx, col_idx, val, date_fmt)
                else:
                    ws.write(row_idx, col_idx, val)

    write_sheet("Students", students)
    write_sheet("Regions", regions)
    write_sheet("Categories", categories)
    write_sheet("Rounds", rounds)

    wb.close()
    return buf.getvalue()


def generate_granular_export(
    students: list[dict],
    include_presigned_urls: bool = False,
    include_photos: bool = False,
) -> bytes:
    """
    Raw student data export.
    include_presigned_urls: adds a column with 5-min S3 URLs for photo/id_doc
    include_photos: embeds photo images in cells (requires Pillow)
    """
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    bold = wb.add_format({"bold": True})
    ws = wb.add_worksheet("Students")

    base_headers = [
        "id", "full_name", "dob", "gender", "national_id", "guardian_phone",
        "review_status", "institution_id", "category_id", "is_deleted",
        "regret_email_sent", "created_at",
    ]
    headers = base_headers[:]
    if include_presigned_urls:
        headers += ["photo_url", "id_document_url"]

    _add_header_row(ws, headers, bold)

    for row_idx, s in enumerate(students, start=1):
        for col_idx, key in enumerate(base_headers):
            ws.write(row_idx, col_idx, str(s.get(key, "")))
        if include_presigned_urls:
            col_offset = len(base_headers)
            ws.write(row_idx, col_offset, s.get("photo_url", ""))
            ws.write(row_idx, col_offset + 1, s.get("id_document_url", ""))

    wb.close()
    return buf.getvalue()
