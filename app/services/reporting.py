"""
Reporting service — XlsxWriter-based exports with Jamia Mosque Committee styling.

1. generate_comprehensive_analytics_workbook — multi-tab executive summary & pivot sheets
2. generate_print_ready_report              — customizable columns, grouped
3. generate_power_bi_export                 — multi-sheet fact + dimension tables
4. generate_granular_export                 — raw student data with optional presigned URLs
"""

import io
import logging
from datetime import date, datetime
from typing import Any

import xlsxwriter

logger = logging.getLogger(__name__)


def _calculate_age_val(dob) -> int | str:
    if not dob:
        return "—"
    try:
        today = datetime.today()
        birth_date = dob if isinstance(dob, datetime) else datetime.strptime(str(dob)[:10], "%Y-%m-%d")
        return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    except Exception:
        return "—"


def generate_comprehensive_analytics_workbook(
    students: list[Any],
    categories: list[Any] | None = None,
    institutions: list[Any] | None = None,
    pivot: str = "timeline",
) -> bytes:
    """
    Generates a rich, multi-tab Excel analytics workbook with styled emerald/gold theme.
    """
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})

    cat_map = {c.id: c.name_en for c in (categories or [])}
    inst_map = {i.id: i.name for i in (institutions or [])}

    # Styles
    title_fmt = wb.add_format({
        "bold": True, "font_size": 16, "font_color": "#006838",
        "align": "left", "valign": "vcenter"
    })
    sub_fmt = wb.add_format({
        "font_size": 10, "font_color": "#64748B", "italic": True
    })
    header_fmt = wb.add_format({
        "bold": True, "font_size": 11, "font_color": "#FFFFFF",
        "bg_color": "#006838", "border": 1, "border_color": "#004d29",
        "align": "center", "valign": "vcenter"
    })
    cell_fmt = wb.add_format({
        "font_size": 10, "border": 1, "border_color": "#E2E8F0", "valign": "vcenter"
    })
    cell_center = wb.add_format({
        "font_size": 10, "border": 1, "border_color": "#E2E8F0", "align": "center", "valign": "vcenter"
    })
    kpi_val_fmt = wb.add_format({
        "bold": True, "font_size": 18, "font_color": "#006838", "align": "center"
    })
    kpi_lbl_fmt = wb.add_format({
        "bold": True, "font_size": 9, "font_color": "#64748B", "align": "center"
    })

    # ─── Sheet 1: Executive Overview ──────────────────────────────────────────
    ws_summary = wb.add_worksheet("Executive Overview")
    ws_summary.write(1, 1, "Jamia Mosque Nairobi — Quran Competition 2026", title_fmt)
    ws_summary.write(2, 1, f"Official Analytics & Demographics Report • Generated {datetime.now().strftime('%d %B %Y, %H:%M')}", sub_fmt)

    total_candidates = len(students)
    approved_count = sum(1 for s in students if getattr(s, "review_status", "") in ("APPROVED", "approved"))
    rejected_count = sum(1 for s in students if getattr(s, "review_status", "") in ("REJECTED", "rejected"))
    pending_count = total_candidates - approved_count - rejected_count

    # KPI Boxes
    ws_summary.merge_range("B5:C5", "TOTAL REGISTRANTS", kpi_lbl_fmt)
    ws_summary.merge_range("B6:C6", total_candidates, kpi_val_fmt)

    ws_summary.merge_range("D5:E5", "APPROVED", kpi_lbl_fmt)
    ws_summary.merge_range("D6:E6", approved_count, kpi_val_fmt)

    ws_summary.merge_range("F5:G5", "UNDER REVIEW", kpi_lbl_fmt)
    ws_summary.merge_range("F6:G6", pending_count, kpi_val_fmt)

    ws_summary.merge_range("H5:I5", "REJECTED / ARCHIVED", kpi_lbl_fmt)
    ws_summary.merge_range("H6:I6", rejected_count, kpi_val_fmt)

    # ─── Sheet 2: Candidate Registry ──────────────────────────────────────────
    ws_registry = wb.add_worksheet("Candidate Registry")
    headers = [
        "REF ID", "Full Name", "Category", "Institution / Madrasa",
        "Age", "DOB", "Gender", "Residence", "National ID", "Phone",
        "Email", "Review Status", "Submission Date"
    ]
    for col_idx, h in enumerate(headers):
        ws_registry.write(0, col_idx, h, header_fmt)

    for row_idx, s in enumerate(students, start=1):
        s_id = getattr(s, "id", row_idx)
        full_name = getattr(s, "full_name", "")
        cat_id = getattr(s, "category_id", 0)
        cat_name = cat_map.get(cat_id, f"Category #{cat_id}")
        inst_id = getattr(s, "institution_id", 0)
        inst_name = inst_map.get(inst_id, "—")
        dob = getattr(s, "dob", None)
        age = _calculate_age_val(dob)
        gender = getattr(s, "gender", "—")
        residence = getattr(s, "residence", "—")
        national_id = getattr(s, "national_id", "—")
        phone = getattr(s, "guardian_phone", "") or getattr(s, "alternative_phone", "—")
        email = getattr(s, "email", "—")
        status = getattr(s, "review_status", "PENDING_REVIEW")
        created_at = getattr(s, "created_at", None)
        created_str = created_at.strftime("%Y-%m-%d") if created_at else "—"

        ws_registry.write(row_idx, 0, f"REF-{s_id:05d}", cell_center)
        ws_registry.write(row_idx, 1, full_name, cell_fmt)
        ws_registry.write(row_idx, 2, cat_name, cell_fmt)
        ws_registry.write(row_idx, 3, inst_name, cell_fmt)
        ws_registry.write(row_idx, 4, age, cell_center)
        ws_registry.write(row_idx, 5, str(dob or "—"), cell_center)
        ws_registry.write(row_idx, 6, str(gender), cell_center)
        ws_registry.write(row_idx, 7, str(residence), cell_fmt)
        ws_registry.write(row_idx, 8, str(national_id), cell_center)
        ws_registry.write(row_idx, 9, str(phone), cell_center)
        ws_registry.write(row_idx, 10, str(email), cell_fmt)
        ws_registry.write(row_idx, 11, str(status), cell_center)
        ws_registry.write(row_idx, 12, created_str, cell_center)

    ws_registry.set_column(0, 0, 14)
    ws_registry.set_column(1, 1, 26)
    ws_registry.set_column(2, 2, 20)
    ws_registry.set_column(3, 3, 28)
    ws_registry.set_column(7, 7, 18)
    ws_registry.set_column(9, 10, 22)

    # ─── Sheet 3: Category Breakdown Pivot ────────────────────────────────────
    ws_cats = wb.add_worksheet("Category Breakdown")
    ws_cats.write(0, 0, "Category Name", header_fmt)
    ws_cats.write(0, 1, "Total Candidates", header_fmt)
    ws_cats.write(0, 2, "Approved", header_fmt)
    ws_cats.write(0, 3, "Pending", header_fmt)
    ws_cats.write(0, 4, "Rejected", header_fmt)

    cat_counts: dict[str, dict[str, int]] = {}
    for s in students:
        c_name = cat_map.get(getattr(s, "category_id", 0), "Other")
        if c_name not in cat_counts:
            cat_counts[c_name] = {"total": 0, "approved": 0, "pending": 0, "rejected": 0}
        cat_counts[c_name]["total"] += 1
        st = str(getattr(s, "review_status", "")).upper()
        if "APPROVED" in st:
            cat_counts[c_name]["approved"] += 1
        elif "REJECTED" in st:
            cat_counts[c_name]["rejected"] += 1
        else:
            cat_counts[c_name]["pending"] += 1

    for row_idx, (c_name, counts) in enumerate(cat_counts.items(), start=1):
        ws_cats.write(row_idx, 0, c_name, cell_fmt)
        ws_cats.write(row_idx, 1, counts["total"], cell_center)
        ws_cats.write(row_idx, 2, counts["approved"], cell_center)
        ws_cats.write(row_idx, 3, counts["pending"], cell_center)
        ws_cats.write(row_idx, 4, counts["rejected"], cell_center)
    ws_cats.set_column(0, 0, 24)

    # ─── Sheet 4: Location / County Breakdown ─────────────────────────────────
    ws_loc = wb.add_worksheet("Location Breakdown")
    ws_loc.write(0, 0, "Residence / County", header_fmt)
    ws_loc.write(0, 1, "Total Candidates", header_fmt)

    loc_counts: dict[str, int] = {}
    for s in students:
        loc = getattr(s, "residence", "Mombasa") or "Mombasa"
        loc_counts[loc] = loc_counts.get(loc, 0) + 1

    for row_idx, (loc_name, count) in enumerate(sorted(loc_counts.items()), start=1):
        ws_loc.write(row_idx, 0, loc_name, cell_fmt)
        ws_loc.write(row_idx, 1, count, cell_center)
    ws_loc.set_column(0, 0, 24)

    wb.close()
    return buf.getvalue()


def generate_print_ready_report(
    students: list[dict],
    columns: list[str],
    group_by: str | None = None,
) -> bytes:
    """Print-ready XlsxWriter export."""
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    bold = wb.add_format({"bold": True})

    def _add_header_row(ws, hdrs: list[str]) -> None:
        for col, h in enumerate(hdrs):
            ws.write(0, col, h, bold)

    if group_by:
        groups: dict[str, list[dict]] = {}
        for s in students:
            key = s.get(group_by, "Unknown")
            groups.setdefault(key, []).append(s)
        for group_key, rows in groups.items():
            ws = wb.add_worksheet(str(group_key)[:31])
            _add_header_row(ws, columns)
            for row_idx, row in enumerate(rows, start=1):
                for col_idx, col in enumerate(columns):
                    ws.write(row_idx, col_idx, row.get(col, ""))
    else:
        ws = wb.add_worksheet("Students")
        _add_header_row(ws, columns)
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
        for col, h in enumerate(headers):
            ws.write(0, col, h, bold)
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
    """Raw student data export with optional presigned S3 URLs."""
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

    for col, h in enumerate(headers):
        ws.write(0, col, h, bold)

    for row_idx, s in enumerate(students, start=1):
        for col_idx, key in enumerate(base_headers):
            ws.write(row_idx, col_idx, str(s.get(key, "")))
        if include_presigned_urls:
            col_offset = len(base_headers)
            ws.write(row_idx, col_offset, s.get("photo_url", ""))
            ws.write(row_idx, col_offset + 1, s.get("id_document_url", ""))

    wb.close()
    return buf.getvalue()
