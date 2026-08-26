"""
Dossier PDF generation via WeasyPrint (RTL-safe).

Bulk generation runs as a Celery task with:
  - Configurable worker concurrency
  - Per-item retry on failure
  - ZIP packaging of all PDFs
  - Job status tracked in Redis for polling
"""

import io
import logging
import zipfile
from pathlib import Path

logger = logging.getLogger(__name__)
TEMPLATE_DIR = Path(__file__).parent.parent.parent / "templates" / "dossiers"


def _get_template(lang: str) -> str:
    filename = "dossier_ar.html" if lang == "AR" else "dossier_en.html"
    return (TEMPLATE_DIR / filename).read_text(encoding="utf-8")


def generate_dossier_pdf_sync(student_data: dict, lang: str = "EN") -> bytes:
    """
    Synchronous PDF generation (called from Celery worker).
    student_data: dict with keys matching template placeholders.
    """
    from weasyprint import HTML
    template_html = _get_template(lang)
    rendered = template_html.format(**student_data)
    return HTML(string=rendered).write_pdf()


def package_dossiers_as_zip(dossiers: list[tuple[str, bytes]]) -> bytes:
    """Pack (filename, pdf_bytes) pairs into a ZIP archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename, pdf_bytes in dossiers:
            zf.writestr(filename, pdf_bytes)
    return buf.getvalue()
