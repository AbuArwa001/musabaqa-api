"""
Certified candidate dossier PDF compilation and document merging engine.
Renders official Jamia Mosque Committee styling (WeasyPrint) matching the exact
institutional specification and merges attached identification documents (PDF/Image) using pypdf.
"""

import io
import os
import base64
import logging
import zipfile
from pathlib import Path
from datetime import datetime

from weasyprint import HTML
from pypdf import PdfWriter, PdfReader

from app.services.s3 import get_s3_object_bytes

logger = logging.getLogger(__name__)

_CACHED_LOGO_DATA_URI = None


def get_logo_data_uri() -> str:
    global _CACHED_LOGO_DATA_URI
    if _CACHED_LOGO_DATA_URI is not None:
        return _CACHED_LOGO_DATA_URI

    logo_paths = [
        Path(__file__).parent.parent / "static" / "logo.png",
        Path("/home/khalfan/Desktop/musabaqa-admin/public/logo.png"),
        Path("/home/khalfan/Desktop/musabaqa-web/public/images/jamia_logo.png"),
    ]
    for p in logo_paths:
        if p.exists():
            try:
                b64 = base64.b64encode(p.read_bytes()).decode("utf-8")
                _CACHED_LOGO_DATA_URI = f"data:image/png;base64,{b64}"
                return _CACHED_LOGO_DATA_URI
            except Exception as exc:
                logger.warning("Failed to load logo from %s: %s", p, exc)
    _CACHED_LOGO_DATA_URI = ""
    return _CACHED_LOGO_DATA_URI


def _calculate_age(dob) -> str:
    if not dob:
        return "—"
    try:
        today = datetime.today()
        birth_date = dob if isinstance(dob, datetime) else datetime.strptime(str(dob)[:10], "%Y-%m-%d")
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        return f"{age} years old"
    except Exception:
        return "—"


def _format_date(d) -> str:
    if not d:
        return "—"
    try:
        dt = d if isinstance(d, datetime) else datetime.strptime(str(d)[:10], "%Y-%m-%d")
        return dt.strftime("%d %B %Y")
    except Exception:
        return str(d)


def generate_single_student_pdf(student, category=None, institution=None) -> bytes:
    """
    Compiles a multi-page certified dossier PDF matching the exact reference design:
      Page 1: Official certified candidate dossier with profile details, metadata, and passport photo.
      Page 2+: Merges any attached identification document (PDF or image).
    """
    logo_data_uri = get_logo_data_uri()
    now_str = datetime.now().strftime("%d %b %Y, %H:%M").upper()

    sub_date = _format_date(getattr(student, "created_at", datetime.now()))
    dob_str = _format_date(getattr(student, "dob", None))
    age_str = _calculate_age(getattr(student, "dob", None))

    status_raw = str(getattr(student, "review_status", "PENDING_REVIEW"))
    if hasattr(student.review_status, "value"):
        status_raw = student.review_status.value

    status_upper = status_raw.upper()
    if "APPROVED" in status_upper:
        status_label = "• APPROVED"
        status_color = "#059669"
        status_bg = "#ECFDF5"
    elif "REJECTED" in status_upper:
        status_label = "• REJECTED"
        status_color = "#DC2626"
        status_bg = "#FEF2F2"
    else:
        status_label = "• PENDING"
        status_color = "#D97706"
        status_bg = "#FEF3C7"

    # Candidate details with safe fallbacks
    full_name = getattr(student, "full_name", "Unknown Candidate")
    student_id = getattr(student, "id", 1)
    nationality = getattr(student, "nationality", None) or "kenyan"
    national_id = getattr(student, "national_id", None) or "—"
    residence = getattr(student, "residence", None) or getattr(student, "county", None) or "Nakuru"
    county = getattr(student, "county", None) or getattr(student, "residence", None) or "Nakuru"
    phone = getattr(student, "guardian_phone", None) or "—"
    alt_phone = getattr(student, "alternative_phone", None) or "—"
    email = getattr(student, "email", None) or "—"
    inst_name = institution.name if institution else "Taqwa Islamic center"

    # Passport photo embedding
    photo_html = "<div style='color: #6B7280; font-size: 12px; margin-top: 50px;'>No photo attached</div>"
    photo_field = getattr(student, "photo", None)
    photo_bytes = None
    if photo_field:
        if os.path.exists(str(photo_field)):
            try:
                with open(photo_field, "rb") as f:
                    photo_bytes = f.read()
            except Exception:
                pass
        if not photo_bytes:
            photo_bytes = get_s3_object_bytes(photo_field)

        if photo_bytes:
            try:
                img_b64 = base64.b64encode(photo_bytes).decode("utf-8")
                mime = "image/png" if str(photo_field).lower().endswith(".png") else "image/jpeg"
                photo_html = f'<img src="data:{mime};base64,{img_b64}" />'
            except Exception as exc:
                logger.error("Error encoding photo for student #%s: %s", student_id, exc)

    # Document card preview
    id_doc_field = getattr(student, "id_document", None)
    if id_doc_field:
        doc_html = """
        <div class="document-card">
          <div class="document-icon">
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M7 18H17V16H7V18ZM7 14H17V12H7V14ZM7 10H14V8H7V10ZM3 22V2H15L21 8V22H3ZM14 9H19.5L14 3.5V9Z" fill="#3B82F6"/>
            </svg>
          </div>
          <div class="document-info">
            <div class="doc-title">National ID /<br/>Document</div>
            <div class="doc-desc">Click to view secure<br/>PDF/Image</div>
          </div>
        </div>
        """
    else:
        doc_html = "<div style='color: #6B7280; font-size: 12px; padding: 12px;'>No ID document attached</div>"

    html_string = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
  @page {{
    size: A4;
    margin: 0;
  }}
  * {{
    box-sizing: border-box;
  }}
  body {{
    font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
    margin: 10mm;
    color: #111827;
    background: #FFFFFF;
  }}
  .card {{
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    overflow: hidden;
    background: #FFFFFF;
  }}
  .header {{
    background: #0E7A4A;
    background-image: url('data:image/svg+xml;utf8,<svg width="100" height="100" xmlns="http://www.w3.org/2000/svg"><path d="M10 10h10v10H10z" fill="rgba(255,255,255,0.03)"/></svg>');
    padding: 24px 32px;
    display: table;
    width: 100%;
    box-sizing: border-box;
    border-bottom: 2px solid #043823;
  }}
  .header-logo-cell {{
    display: table-cell;
    vertical-align: top;
    width: 80px;
  }}
  .header-logo {{
    width: 68px;
    height: 68px;
    border-radius: 50%;
    background-color: white;
    object-fit: contain;
    border: 2px solid #F0D97A;
    padding: 2px;
  }}
  .header-content-cell {{
    display: table-cell;
    vertical-align: top;
    padding-left: 16px;
  }}
  .header-title {{
    color: #F0D97A;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 1px;
    margin-bottom: 6px;
    text-transform: uppercase;
  }}
  .header-name {{
    color: white;
    font-size: 22px;
    font-weight: 800;
    margin: 0 0 8px 0;
    text-transform: capitalize;
  }}
  .header-meta {{
    color: #E2E8F0;
    font-size: 11px;
    font-weight: 600;
  }}
  .header-meta span {{
    color: #F0D97A;
    font-weight: 800;
  }}
  .header-badge-cell {{
    display: table-cell;
    vertical-align: top;
    text-align: right;
    width: 130px;
  }}
  .status-badge {{
    display: inline-block;
    background-color: {status_bg};
    color: {status_color};
    padding: 6px 14px;
    border-radius: 20px;
    font-weight: 800;
    font-size: 10.5px;
    text-transform: uppercase;
    margin-top: 4px;
    letter-spacing: 0.5px;
  }}
  .grid-container {{
    display: table;
    width: 100%;
    padding: 24px;
    box-sizing: border-box;
    table-layout: fixed;
  }}
  .col-left {{
    display: table-cell;
    width: 60%;
    padding-right: 24px;
    vertical-align: top;
  }}
  .col-right {{
    display: table-cell;
    width: 40%;
    vertical-align: top;
  }}
  .section {{
    border: 1px solid #F3F4F6;
    border-radius: 12px;
    background: #F9FAFB;
    margin-bottom: 20px;
  }}
  .section-header {{
    padding: 14px 20px;
    font-size: 11.5px;
    font-weight: 800;
    color: #111827;
    border-bottom: 1px solid #F3F4F6;
    background: #FFFFFF;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    letter-spacing: 0.5px;
  }}
  .section-content {{
    padding: 18px 20px;
  }}
  .field {{
    margin-bottom: 15px;
  }}
  .field:last-child {{
    margin-bottom: 0;
  }}
  .field-label {{
    font-size: 9px;
    color: #6B7280;
    font-weight: 800;
    text-transform: uppercase;
    margin-bottom: 5px;
    letter-spacing: 0.5px;
  }}
  .field-value {{
    font-size: 13.5px;
    color: #111827;
    font-weight: 700;
  }}
  .photo-container {{
    text-align: center;
    background: #FFFFFF;
    border-bottom-left-radius: 12px;
    border-bottom-right-radius: 12px;
    padding: 16px 20px 24px 20px;
    min-height: 180px;
  }}
  .photo-container img {{
    width: 120px;
    height: 150px;
    object-fit: cover;
    border-radius: 8px;
    border: 1px dashed #D1D5DB;
    padding: 4px;
    background: white;
  }}
  .document-card {{
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    padding: 12px;
    display: table;
    width: 100%;
    box-sizing: border-box;
  }}
  .document-icon {{
    display: table-cell;
    width: 36px;
    height: 36px;
    background: #EFF6FF;
    border-radius: 6px;
    vertical-align: middle;
    text-align: center;
  }}
  .document-icon svg {{
    width: 20px;
    height: 20px;
    display: inline-block;
    margin-top: 4px;
  }}
  .document-info {{
    display: table-cell;
    vertical-align: middle;
    padding-left: 12px;
  }}
  .document-info .doc-title {{
    font-size: 11px;
    font-weight: 800;
    margin-bottom: 3px;
    color: #111827;
    line-height: 1.3;
  }}
  .document-info .doc-desc {{
    font-size: 10px;
    color: #6B7280;
    line-height: 1.2;
  }}
  .footer {{
    margin-top: 10px;
    padding: 12px 24px;
    background: #F8FAFC;
    font-size: 9px;
    color: #9CA3AF;
    display: table;
    width: 100%;
    box-sizing: border-box;
    border-top: 1px solid #E5E7EB;
  }}
  .footer .left {{
    display: table-cell;
    font-weight: 800;
    text-transform: uppercase;
    text-align: left;
  }}
  .footer .right {{
    display: table-cell;
    text-transform: uppercase;
    text-align: right;
    font-weight: 600;
  }}
</style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="header-logo-cell">
        <img src="{logo_data_uri}" class="header-logo" />
      </div>
      <div class="header-content-cell">
        <div class="header-title">JAMIA MOSQUE COMMITTEE · NAIROBI, KENYA</div>
        <h1 class="header-name">{full_name}</h1>
        <div class="header-meta">
          <span>ID:</span> REF-{student_id:05d} &nbsp;&nbsp;•&nbsp;&nbsp; 
          <span>Submitted:</span> {sub_date}
        </div>
      </div>
      <div class="header-badge-cell">
        <div class="status-badge">
          {status_label}
        </div>
      </div>
    </div>
    
    <div class="grid-container">
      <div class="col-left">
        <!-- Personal Information -->
        <div class="section" style="background: #FFFFFF;">
          <div class="section-header" style="background: #F9FAFB; border-bottom: none;">
            <span style="color: #3B82F6; font-size: 14px; margin-right: 8px;">👤</span>
            PERSONAL INFORMATION
          </div>
          <div class="section-content" style="background: #FFFFFF; border-top: 1px solid #F3F4F6;">
            <div class="field">
              <div class="field-label">DATE OF BIRTH</div>
              <div class="field-value">{dob_str}</div>
            </div>
            <div class="field">
              <div class="field-label">AGE</div>
              <div class="field-value">{age_str}</div>
            </div>
            <div class="field">
              <div class="field-label">NATIONALITY</div>
              <div class="field-value">{nationality}</div>
            </div>
            <div class="field">
              <div class="field-label">NATIONAL ID / PASSPORT</div>
              <div class="field-value">{national_id}</div>
            </div>
            <div class="field">
              <div class="field-label">CURRENT RESIDENCE</div>
              <div class="field-value">{residence}</div>
            </div>
            <div class="field">
              <div class="field-label">HOME COUNTY</div>
              <div class="field-value">{county}</div>
            </div>
          </div>
        </div>

        <!-- Contact & Institutional Data -->
        <div class="section" style="background: #FFFFFF;">
          <div class="section-header" style="background: #F9FAFB; border-bottom: none;">
            <span style="color: #4B5563; font-size: 14px; margin-right: 8px;">📞</span>
            CONTACT & INSTITUTIONAL DATA
          </div>
          <div class="section-content" style="background: #FFFFFF; border-top: 1px solid #F3F4F6;">
            <div class="field">
              <div class="field-label">PRIMARY PHONE</div>
              <div class="field-value">{phone}</div>
            </div>
            <div class="field">
              <div class="field-label">ALTERNATIVE PHONE</div>
              <div class="field-value">{alt_phone}</div>
            </div>
            <div class="field">
              <div class="field-label">EMAIL ADDRESS</div>
              <div class="field-value">{email}</div>
            </div>
            <div class="field">
              <div class="field-label">NOMINATING INSTITUTION</div>
              <div class="field-value">{inst_name}</div>
            </div>
          </div>
        </div>
      </div>
      
      <div class="col-right">
        <!-- Applicant Photo -->
        <div class="section" style="background: #FFFFFF;">
          <div class="section-header" style="background: #FFFFFF; border-bottom: none; text-align: center;">
            APPLICANT PHOTO
          </div>
          <div class="section-content photo-container">
            {photo_html}
          </div>
        </div>

        <!-- Attached Documents -->
        <div class="section" style="background: #FFFFFF;">
          <div class="section-header" style="background: #FFFFFF; border-bottom: none;">
            ATTACHED DOCUMENTS
          </div>
          <div class="section-content" style="padding-top: 8px;">
            {doc_html}
          </div>
        </div>
      </div>
    </div>
    
    <div class="footer">
      <div class="left">OFFICIAL QURAN COMPETITION 2026 REGISTRY</div>
      <div class="right">GENERATED: {now_str}</div>
    </div>
  </div>
</body>
</html>"""

    page1_bytes = HTML(string=html_string).write_pdf()

    # If no ID document attached, return page 1
    if not id_doc_field:
        return page1_bytes

    # Merge ID Document onto Page 2+
    writer = PdfWriter()
    p1_reader = PdfReader(io.BytesIO(page1_bytes))
    for page in p1_reader.pages:
        writer.add_page(page)

    doc_bytes = get_s3_object_bytes(id_doc_field)
    if not doc_bytes and os.path.exists(id_doc_field):
        try:
            with open(id_doc_field, "rb") as f:
                doc_bytes = f.read()
        except Exception:
            pass

    if doc_bytes:
        try:
            doc_key_lower = str(id_doc_field).lower()
            if doc_key_lower.endswith(".pdf"):
                id_reader = PdfReader(io.BytesIO(doc_bytes))
                for p in id_reader.pages:
                    writer.add_page(p)
            elif doc_key_lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
                img_b64 = base64.b64encode(doc_bytes).decode("utf-8")
                mime = "image/png" if doc_key_lower.endswith(".png") else "image/jpeg"
                img_page_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    @page {{ size: A4 portrait; margin: 10mm; }}
    body {{ font-family: sans-serif; text-align: center; margin: 0; }}
    .header {{ font-size: 13px; font-weight: 800; color: #0E7A4A; text-transform: uppercase; margin-bottom: 12px; border-bottom: 2px solid #0E7A4A; padding-bottom: 6px; }}
    img {{ max-width: 100%; max-height: 250mm; object-fit: contain; border-radius: 6px; border: 1px solid #E2E8F0; }}
  </style>
</head>
<body>
  <div class="header">Attached Identification Document — {full_name} (REF-{student_id:05d})</div>
  <img src="data:{mime};base64,{img_b64}" />
</body>
</html>"""
                img_pdf_bytes = HTML(string=img_page_html).write_pdf()
                img_reader = PdfReader(io.BytesIO(img_pdf_bytes))
                for p in img_reader.pages:
                    writer.add_page(p)
        except Exception as exc:
            logger.error("Failed to merge ID document for student #%s: %s", student_id, exc)

    merged_buf = io.BytesIO()
    writer.write(merged_buf)
    return merged_buf.getvalue()


def package_dossiers_as_zip(dossiers: list[tuple[str, bytes]]) -> bytes:
    """Pack (filename, pdf_bytes) pairs into a ZIP archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, pdf_bytes in dossiers:
            zf.writestr(filename, pdf_bytes)
    return buf.getvalue()
