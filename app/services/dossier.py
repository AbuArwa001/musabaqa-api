"""
Certified candidate dossier PDF compilation and document merging engine.
Renders official Jamia Mosque Committee styling (WeasyPrint) and merges attached
identification documents (PDF/Image) using pypdf.
"""

import io
import os
import base64
import logging
import zipfile
from datetime import datetime

from weasyprint import HTML
from pypdf import PdfWriter, PdfReader
from PIL import Image as PILImage

from app.services.s3 import get_s3_object_bytes

logger = logging.getLogger(__name__)


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


def generate_single_student_pdf(student, category=None, institution=None) -> bytes:
    """
    Compiles a multi-page certified dossier PDF for a candidate:
      Page 1: Official certified candidate dossier with profile details, metadata, and passport photo.
      Page 2+: Merges any attached identification document (PDF or image).
    """
    now_str = datetime.now().strftime("%d %b %Y, %H:%M").upper()
    cat_name = category.name_en if category else (f"Category #{student.category_id}" if student.category_id else "Quran Category")
    inst_name = institution.name if institution else "Registered Madrasa / Institution"

    sub_date = (
        student.created_at.strftime("%d %B %Y")
        if hasattr(student, "created_at") and student.created_at
        else datetime.now().strftime("%d %B %Y")
    )
    dob_str = str(student.dob) if student.dob else "—"
    age_str = _calculate_age(student.dob)

    status = (student.review_status.value if hasattr(student.review_status, "value") else str(student.review_status)).upper()
    status_color = "#059669" if status == "APPROVED" else "#DC2626" if status == "REJECTED" else "#D97706"
    status_bg = "#ECFDF5" if status == "APPROVED" else "#FEF2F2" if status == "REJECTED" else "#FEF3C7"

    # Passport photo embedding
    photo_html = "<div style='color: #94A3B8; font-size: 11px; text-align: center; margin-top: 45px;'>No photo attached</div>"
    if student.photo:
        photo_bytes = get_s3_object_bytes(student.photo)
        if not photo_bytes and os.path.exists(student.photo):
            try:
                with open(student.photo, "rb") as f:
                    photo_bytes = f.read()
            except Exception:
                pass

        if photo_bytes:
            try:
                b64 = base64.b64encode(photo_bytes).decode("utf-8")
                mime = "image/png" if str(student.photo).lower().endswith(".png") else "image/jpeg"
                photo_html = f'<img src="data:{mime};base64,{b64}" style="width: 100%; height: 100%; object-fit: cover; border-radius: 6px;" />'
            except Exception as exc:
                logger.error("Failed to base64-encode passport photo: %s", exc)

    doc_badge_html = """
      <div style="display: flex; align-items: center; gap: 10px; background: #F8FAFC; border: 1px solid #E2E8F0; padding: 10px; border-radius: 8px;">
        <span style="font-size: 18px;">📄</span>
        <div>
          <div style="font-size: 11px; font-weight: 700; color: #1E293B;">National ID / Certificate</div>
          <div style="font-size: 9.5px; color: #64748B;">Attached &bull; See Page 2</div>
        </div>
      </div>
    """ if student.id_document else "<div style='color: #94A3B8; font-size: 11px;'>No ID document attached</div>"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    @page {{
      size: A4 portrait;
      margin: 8mm 10mm;
    }}
    * {{
      box-sizing: border-box;
    }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
      margin: 0;
      padding: 0;
      color: #0F172A;
      font-size: 12px;
      line-height: 1.4;
      background: #FFFFFF;
    }}
    .dossier-card {{
      border: 1px solid #CBD5E1;
      border-radius: 12px;
      overflow: hidden;
    }}
    .header {{
      background: linear-gradient(135deg, #006838 0%, #004d29 100%);
      padding: 20px 24px;
      color: #FFFFFF;
      display: table;
      width: 100%;
    }}
    .header-left {{
      display: table-cell;
      vertical-align: middle;
    }}
    .header-sub {{
      color: #F6CB7D;
      font-size: 9.5px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      margin-bottom: 4px;
    }}
    .header-name {{
      font-size: 20px;
      font-weight: 900;
      margin: 0 0 6px 0;
      letter-spacing: -0.02em;
      text-transform: capitalize;
    }}
    .header-meta {{
      font-size: 11px;
      color: #E2E8F0;
      font-family: monospace;
    }}
    .header-badge {{
      display: table-cell;
      vertical-align: middle;
      text-align: right;
      width: 130px;
    }}
    .status-pill {{
      display: inline-block;
      padding: 4px 10px;
      background: {status_bg};
      color: {status_color};
      border: 1px solid {status_color};
      font-weight: 800;
      font-size: 10px;
      border-radius: 9999px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .body-table {{
      width: 100%;
      display: table;
      table-layout: fixed;
      padding: 16px 20px;
    }}
    .col-left {{
      display: table-cell;
      width: 65%;
      vertical-align: top;
      padding-right: 16px;
    }}
    .col-right {{
      display: table-cell;
      width: 35%;
      vertical-align: top;
    }}
    .section-card {{
      border: 1px solid #E2E8F0;
      border-radius: 8px;
      margin-bottom: 14px;
      overflow: hidden;
    }}
    .section-header {{
      background: #F8FAFC;
      border-bottom: 1px solid #E2E8F0;
      padding: 7px 12px;
      font-size: 10.5px;
      font-weight: 800;
      color: #334155;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .section-content {{
      padding: 10px 12px;
    }}
    .grid-2 {{
      display: table;
      width: 100%;
    }}
    .grid-cell {{
      display: table-cell;
      width: 50%;
      vertical-align: top;
      padding-bottom: 8px;
    }}
    .field-label {{
      font-size: 9px;
      text-transform: uppercase;
      font-weight: 700;
      color: #64748B;
      letter-spacing: 0.04em;
      margin-bottom: 1px;
    }}
    .field-val {{
      font-size: 11.5px;
      font-weight: 700;
      color: #0F172A;
    }}
    .photo-box {{
      width: 100%;
      height: 155px;
      border: 1.5px dashed #CBD5E1;
      border-radius: 8px;
      overflow: hidden;
      background: #F8FAFC;
      display: flex;
      align-items: center;
      justify-content: center;
    }}
    .footer {{
      border-top: 1px solid #E2E8F0;
      background: #F8FAFC;
      padding: 8px 20px;
      display: table;
      width: 100%;
      font-size: 8.5px;
      color: #94A3B8;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .footer-left {{ display: table-cell; text-align: left; }}
    .footer-right {{ display: table-cell; text-align: right; }}
  </style>
</head>
<body>
  <div class="dossier-card">
    <div class="header">
      <div class="header-left">
        <div class="header-sub">Jamia Mosque Committee &bull; Nairobi, Kenya</div>
        <h1 class="header-name">{student.full_name}</h1>
        <div class="header-meta">
          <span>ID:</span> REF-{student.id:05d} &bull; 
          <span>Category:</span> {cat_name} &bull; 
          <span>Submitted:</span> {sub_date}
        </div>
      </div>
      <div class="header-badge">
        <span class="status-pill">{status}</span>
      </div>
    </div>

    <div class="body-table">
      <div class="col-left">
        
        <!-- Personal Information -->
        <div class="section-card">
          <div class="section-header">Personal Information</div>
          <div class="section-content">
            <div class="grid-2">
              <div class="grid-cell">
                <div class="field-label">Date of Birth</div>
                <div class="field-val">{dob_str}</div>
              </div>
              <div class="grid-cell">
                <div class="field-label">Age</div>
                <div class="field-val">{age_str}</div>
              </div>
            </div>
            <div class="grid-2">
              <div class="grid-cell">
                <div class="field-label">Nationality</div>
                <div class="field-val">{student.nationality or "Kenyan"}</div>
              </div>
              <div class="grid-cell">
                <div class="field-label">National ID / Birth Cert</div>
                <div class="field-val">{student.national_id or "—"}</div>
              </div>
            </div>
            <div class="grid-2">
              <div class="grid-cell">
                <div class="field-label">Residence</div>
                <div class="field-val">{student.residence or "Mombasa"}</div>
              </div>
              <div class="grid-cell">
                <div class="field-label">Gender</div>
                <div class="field-val">{student.gender or "Male"}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Contact & Institutional Data -->
        <div class="section-card">
          <div class="section-header">Contact &amp; Institutional Data</div>
          <div class="section-content">
            <div class="grid-2">
              <div class="grid-cell">
                <div class="field-label">Guardian Phone</div>
                <div class="field-val">{student.guardian_phone or "—"}</div>
              </div>
              <div class="grid-cell">
                <div class="field-label">Alternative Phone</div>
                <div class="field-val">{student.alternative_phone or "—"}</div>
              </div>
            </div>
            <div class="grid-2">
              <div class="grid-cell">
                <div class="field-label">Email Address</div>
                <div class="field-val">{student.email or "—"}</div>
              </div>
              <div class="grid-cell">
                <div class="field-label">Nominating Madrasa</div>
                <div class="field-val">{inst_name}</div>
              </div>
            </div>
          </div>
        </div>

      </div>

      <div class="col-right">
        <!-- Applicant Photo -->
        <div class="section-card">
          <div class="section-header">Applicant Photo</div>
          <div class="section-content">
            <div class="photo-box">
              {photo_html}
            </div>
          </div>
        </div>

        <!-- Attached Documents -->
        <div class="section-card">
          <div class="section-header">Attached Identification</div>
          <div class="section-content">
            {doc_badge_html}
          </div>
        </div>
      </div>
    </div>

    <div class="footer">
      <div class="footer-left">Official Quran Competition 2026 Registry</div>
      <div class="footer-right">Generated: {now_str}</div>
    </div>
  </div>
</body>
</html>"""

    page1_bytes = HTML(string=html_content).write_pdf()

    # If no ID document attached, return page 1
    if not student.id_document:
        return page1_bytes

    # Merge ID Document onto Page 2+
    writer = PdfWriter()
    p1_reader = PdfReader(io.BytesIO(page1_bytes))
    for page in p1_reader.pages:
        writer.add_page(page)

    doc_bytes = get_s3_object_bytes(student.id_document)
    if not doc_bytes and os.path.exists(student.id_document):
        try:
            with open(student.id_document, "rb") as f:
                doc_bytes = f.read()
        except Exception:
            pass

    if doc_bytes:
        try:
            doc_key_lower = str(student.id_document).lower()
            if doc_key_lower.endswith(".pdf"):
                id_reader = PdfReader(io.BytesIO(doc_bytes))
                for p in id_reader.pages:
                    writer.add_page(p)
            elif doc_key_lower.endswith((".jpg", ".jpeg", ".png", ".webp")):
                # Convert image to clean A4 PDF page
                img_b64 = base64.b64encode(doc_bytes).decode("utf-8")
                mime = "image/png" if doc_key_lower.endswith(".png") else "image/jpeg"
                img_page_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    @page {{ size: A4 portrait; margin: 10mm; }}
    body {{ font-family: sans-serif; text-align: center; margin: 0; }}
    .header {{ font-size: 13px; font-weight: 800; color: #006838; text-transform: uppercase; margin-bottom: 12px; border-bottom: 2px solid #006838; padding-bottom: 6px; }}
    img {{ max-width: 100%; max-height: 250mm; object-fit: contain; border-radius: 6px; border: 1px solid #E2E8F0; }}
  </style>
</head>
<body>
  <div class="header">Attached Identification Document — {student.full_name} (REF-{student.id:05d})</div>
  <img src="data:{mime};base64,{img_b64}" />
</body>
</html>"""
                img_pdf_bytes = HTML(string=img_page_html).write_pdf()
                img_reader = PdfReader(io.BytesIO(img_pdf_bytes))
                for p in img_reader.pages:
                    writer.add_page(p)
        except Exception as exc:
            logger.error("Failed to merge ID document for student #%s: %s", student.id, exc)

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
