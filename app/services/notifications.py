"""
Notification service — bilingual (EN/AR) dispatcher with Resend & SMS.

Channels:
  - Resend (rich HTML + plain text transactional email)
  - Knock (in-app notifications)
  - Africa's Talking (SMS)
"""

import logging
from typing import Any
import resend

from app.core.config import settings
from app.models.admin_user import PreferredLanguage

logger = logging.getLogger(__name__)


def _get_email_wrapper(title: str, content_html: str, lang: str = "EN") -> str:
    """Wraps body content in official Jamia Mosque Committee branded email template."""
    is_ar = lang == "AR"
    dir_attr = 'dir="rtl"' if is_ar else 'dir="ltr"'
    font_family = "Tahoma, Arial, sans-serif" if is_ar else "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

    return f"""<!DOCTYPE html>
<html lang="{lang.lower()}" {dir_attr}>
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{title}</title>
</head>
<body style="font-family: {font_family}; background-color: #f4f6f8; margin: 0; padding: 28px 12px; color: #1e293b;">
  <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.06); border: 1px solid #e2e8f0;">
    
    <!-- Top Header Banner -->
    <tr>
      <td style="background: linear-gradient(135deg, #006838 0%, #004d29 100%); padding: 32px 24px; text-align: center; color: #ffffff;">
        <div style="font-size: 11px; font-weight: 800; color: #f6cb7d; text-transform: uppercase; letter-spacing: 0.15em; margin-bottom: 6px;">
          JAMIA MOSQUE COMMITTEE · NAIROBI, KENYA
        </div>
        <h1 style="margin: 0; font-size: 22px; font-weight: 800; letter-spacing: -0.02em; color: #ffffff;">
          Quran Competition 2026
        </h1>
      </td>
    </tr>
    <tr>
      <td style="height: 4px; background: linear-gradient(90deg, #c99335, #f6cb7d, #c99335);"></td>
    </tr>

    <!-- Body Content -->
    <tr>
      <td style="padding: 32px 28px; line-height: 1.65; font-size: 14.5px;">
        {content_html}
      </td>
    </tr>

    <!-- Footer -->
    <tr>
      <td style="background-color: #f8fafc; border-top: 1px solid #e2e8f0; padding: 20px 24px; text-align: center; font-size: 11.5px; color: #64748b;">
        <p style="margin: 0 0 4px 0; font-weight: 700; color: #334155;">
          Jamia Mosque Committee · Musabaqa Secretariat
        </p>
        <p style="margin: 0; color: #94a3b8;">
          Kigali Road, Nairobi, Kenya &bull; Official Management &amp; Examination Portal
        </p>
      </td>
    </tr>

  </table>
</body>
</html>"""


async def _send_resend_email(
    to: str,
    subject: str,
    body_text: str,
    html_body: str | None = None,
) -> bool:
    """Sends email via Resend API."""
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not configured — skipping email to %s", to)
        return False
    if not to or not to.strip():
        return False

    try:
        resend.api_key = settings.RESEND_API_KEY
        params: dict[str, Any] = {
            "from": settings.RESEND_FROM_EMAIL or "Jamia Musabaqa <noreply@musabaqa.jmc.or.ke>",
            "to": [to.strip()],
            "subject": subject,
            "text": body_text,
        }
        if html_body:
            params["html"] = html_body

        resend.Emails.send(params)
        logger.info("Resend email sent successfully to %s (Subject: %s)", to, subject)
        return True
    except Exception as exc:
        logger.error("Failed to send Resend email to %s: %s", to, exc)
        return False


def _pick_lang(lang: str | None) -> str:
    return "AR" if lang == PreferredLanguage.AR else "EN"


# ---------------------------------------------------------------------------
# Africa's Talking (SMS)
# ---------------------------------------------------------------------------

async def _send_at_sms(phone: str, message: str) -> None:
    if not settings.AT_API_KEY or not phone:
        return
    try:
        import africastalking
        africastalking.initialize(settings.AT_USERNAME, settings.AT_API_KEY)
        sms = africastalking.SMS
        sms.send(message, [phone], sender_id=settings.AT_SENDER_ID)
    except Exception as exc:
        logger.error("Africa's Talking SMS error: %s", exc)


# ---------------------------------------------------------------------------
# Knock (in-app notifications)
# ---------------------------------------------------------------------------

async def _send_knock_notification(
    recipient_id: str, event_key: str, data: dict[str, Any]
) -> None:
    if not settings.KNOCK_API_KEY:
        return
    try:
        from knockapi import Knock
        client = Knock(api_key=settings.KNOCK_API_KEY)
        client.workflows.trigger(
            key=event_key,
            actor={"id": "system"},
            recipients=[{"id": recipient_id}],
            data=data,
        )
    except Exception as exc:
        logger.error("Knock notification error: %s", exc)


# ---------------------------------------------------------------------------
# Public Email Notification Handlers
# ---------------------------------------------------------------------------

async def send_registration_confirmation_email(student, institution, category) -> bool:
    """Sends candidate registration confirmation email with application reference."""
    recipient = student.email or (institution.email if institution else None)
    if not recipient:
        return False

    ref_str = f"REF-{student.id:05d}"
    cat_name = category.name_en if category else f"Category #{student.category_id}"
    inst_name = institution.name if institution else "Registered Institution"

    content = f"""
      <p style="font-size: 16px; font-weight: 700; color: #006838; margin-top: 0;">
        Assalamu Alaikum wa Rahmatullahi wa Barakatuh,
      </p>
      <p style="font-size: 15px; font-weight: 600; color: #0f172a;">
        Dear <strong>{student.full_name}</strong>,
      </p>
      <p style="color: #475569; margin-bottom: 20px;">
        Your application for the <strong>Jamia Mosque Quran Memorization Competition 2026</strong> has been received and entered into the screening registry.
      </p>

      <!-- Reference Box -->
      <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 18px; margin-bottom: 24px;">
        <table width="100%" border="0" cellspacing="0" cellpadding="6" style="font-size: 13.5px;">
          <tr>
            <td style="color: #64748b; font-weight: 600; width: 140px;">Candidate ID</td>
            <td style="color: #006838; font-weight: 800; font-family: monospace;">{ref_str}</td>
          </tr>
          <tr>
            <td style="color: #64748b; font-weight: 600;">Category</td>
            <td style="color: #0f172a; font-weight: 700;">{cat_name}</td>
          </tr>
          <tr>
            <td style="color: #64748b; font-weight: 600;">Institution</td>
            <td style="color: #0f172a; font-weight: 600;">{inst_name}</td>
          </tr>
          <tr>
            <td style="color: #64748b; font-weight: 600;">Status</td>
            <td><span style="background: #fef3c7; color: #b45309; border: 1px solid #fde68a; padding: 2px 8px; border-radius: 6px; font-weight: 700; font-size: 11px;">UNDER REVIEW</span></td>
          </tr>
        </table>
      </div>

      <p style="color: #475569;">
        The review committee will verify your age requirements and submitted identification documents. You will receive an official status update once screening is complete.
      </p>

      <p style="color: #006838; font-weight: 700; margin-top: 24px; margin-bottom: 0;">
        جزاكم الله خيراً وبارك الله فيكم<br/>
        <span style="font-size: 12.5px; color: #64748b; font-weight: 500;">May Allah bless your continuous efforts in the study and memorization of the Holy Quran.</span>
      </p>
    """

    subject = f"Registration Received: {student.full_name} ({ref_str}) | Jamia Quran Competition 2026"
    body_text = f"Assalamu Alaikum {student.full_name},\n\nYour application for Quran Competition 2026 has been received.\nReference: {ref_str}\nCategory: {cat_name}\nStatus: UNDER REVIEW\n\nJamia Mosque Committee"
    html_body = _get_email_wrapper(subject, content)

    return await _send_resend_email(recipient, subject, body_text, html_body)


async def send_category_change_email(student, institution, old_cat_name: str, new_cat_name: str, reason: str | None = None) -> bool:
    """Sends category change notification email."""
    recipient = student.email or (institution.email if institution else None)
    if not recipient:
        return False

    ref_str = f"REF-{student.id:05d}"
    notes_block = ""
    if reason and reason.strip():
        notes_block = f"""
        <div style="background-color: #eff6ff; border-left: 4px solid #3b82f6; padding: 14px 16px; margin: 18px 0; border-radius: 6px;">
          <p style="font-size: 12px; font-weight: 800; color: #1d4ed8; margin: 0 0 4px 0; text-transform: uppercase;">
            📌 Committee Note / Justification:
          </p>
          <p style="font-size: 13.5px; color: #1e40af; margin: 0; font-weight: 500;">{reason.strip()}</p>
        </div>
        """

    content = f"""
      <p style="font-size: 16px; font-weight: 700; color: #006838; margin-top: 0;">
        Assalamu Alaikum wa Rahmatullahi wa Barakatuh,
      </p>
      <p style="font-size: 15px; font-weight: 600; color: #0f172a;">
        Dear <strong>{student.full_name}</strong>,
      </p>
      <p style="color: #475569;">
        Please be informed that your memorization competition category has been officially updated by the administration:
      </p>

      <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 18px; margin: 18px 0;">
        <table width="100%" border="0" cellspacing="0" cellpadding="6" style="font-size: 13.5px;">
          <tr>
            <td style="color: #64748b; font-weight: 600; width: 140px;">Candidate ID</td>
            <td style="color: #006838; font-weight: 800; font-family: monospace;">{ref_str}</td>
          </tr>
          <tr>
            <td style="color: #64748b; font-weight: 600;">Previous Category</td>
            <td style="color: #64748b; text-decoration: line-through;">{old_cat_name}</td>
          </tr>
          <tr>
            <td style="color: #64748b; font-weight: 600;">New Category</td>
            <td style="color: #006838; font-weight: 800;">{new_cat_name}</td>
          </tr>
        </table>
      </div>

      {notes_block}

      <p style="color: #475569;">
        Your official examination schedule and jury guidelines will follow the updated category criteria.
      </p>
      <p style="color: #006838; font-weight: 700; margin-top: 24px; margin-bottom: 0;">
        جزاكم الله خيراً وبارك الله فيكم
      </p>
    """

    subject = f"Category Updated: {student.full_name} -> {new_cat_name} | Jamia Quran Competition"
    body_text = f"Assalamu Alaikum {student.full_name},\n\nYour competition category has been updated to {new_cat_name}.\nReference: {ref_str}\n\nJamia Mosque Committee"
    html_body = _get_email_wrapper(subject, content)

    return await _send_resend_email(recipient, subject, body_text, html_body)


async def send_regret_email(student, institution, reason: str | None = None, custom_notes: str | None = None) -> bool:
    """Sends official regret notification email."""
    recipient = student.email or (institution.email if institution else None)
    if not recipient:
        return False

    ref_str = f"REF-{student.id:05d}"
    notes_text = (custom_notes or reason or student.deletion_reason or student.review_notes or "").strip()

    notes_block = ""
    if notes_text:
        notes_block = f"""
        <div style="background-color: #fef2f2; border: 1px solid #fecaca; border-left: 5px solid #dc2626; padding: 16px 18px; margin: 20px 0; border-radius: 8px;">
          <p style="font-size: 12px; font-weight: 800; color: #991b1b; margin: 0 0 6px 0; text-transform: uppercase; letter-spacing: 0.05em;">
            📌 Committee Note / Reason:
          </p>
          <p style="font-size: 13.5px; color: #7f1d1d; margin: 0; line-height: 1.6; font-weight: 500;">{notes_text}</p>
        </div>
        """

    content = f"""
      <p style="font-size: 16px; font-weight: 700; color: #006838; margin-top: 0;">
        Assalamu Alaikum wa Rahmatullahi wa Barakatuh,
      </p>
      <p style="font-size: 15px; font-weight: 600; color: #0f172a;">
        Dear <strong>{student.full_name}</strong>,
      </p>
      <p style="color: #475569; line-height: 1.7;">
        Thank you for submitting your application for the <strong>Annual Quran Memorization Competition 2026</strong> organized by the Jamia Mosque Committee, Nairobi.
      </p>
      <p style="color: #475569; line-height: 1.7;">
        The registration and screening phase has concluded. Due to high candidate volume and strict quota regulations across categories and counties, we regret to inform you that your application was <strong style="color: #dc2626;">not selected</strong> to proceed to the examination rounds for this edition.
      </p>

      {notes_block}

      <p style="color: #475569; line-height: 1.7;">
        We deeply appreciate your noble effort and dedication to memorizing the Book of Allah. We wholeheartedly encourage you to continue your Quranic studies and look forward to your participation in future competitions.
      </p>

      <p style="color: #006838; font-weight: 700; margin-top: 24px; margin-bottom: 0;">
        جزاكم الله خيراً وبارك الله فيكم ونفع بكم الإسلام والمسلمين<br/>
        <span style="font-size: 12.5px; color: #64748b; font-weight: 500;">May Allah reward you abundantly and bless your continuous journey with the Holy Quran.</span>
      </p>
    """

    subject = f"Application Status Update: {student.full_name} ({ref_str}) | Jamia Quran Competition 2026"
    body_text = f"Assalamu Alaikum {student.full_name},\n\nThank you for applying for the Jamia Quran Competition 2026. We regret to inform you that your application was not selected for this edition.\n\nJamia Mosque Committee"
    html_body = _get_email_wrapper(subject, content)

    return await _send_resend_email(recipient, subject, body_text, html_body)


async def notify_student_approved(student, institution, category, venue: str = "", date: str = "") -> None:
    """Sends candidate approval notice."""
    recipient = student.email or (institution.email if institution else None)
    ref_str = f"REF-{student.id:05d}"
    cat_name = category.name_en if category else f"Category #{student.category_id}"

    content = f"""
      <p style="font-size: 16px; font-weight: 700; color: #006838; margin-top: 0;">
        Assalamu Alaikum wa Rahmatullahi wa Barakatuh,
      </p>
      <p style="font-size: 15px; font-weight: 600; color: #0f172a;">
        Dear <strong>{student.full_name}</strong>,
      </p>
      <p style="color: #475569;">
        🎉 <strong>Congratulations!</strong> Your registration for the <strong>Jamia Quran Memorization Competition 2026</strong> has been <strong style="color: #059669;">APPROVED</strong> for the <strong>{cat_name}</strong> category.
      </p>

      <div style="background-color: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 12px; padding: 18px; margin: 18px 0;">
        <p style="margin: 0 0 6px 0; font-size: 13.5px; color: #065f46;"><strong>Candidate Reference:</strong> {ref_str}</p>
        <p style="margin: 0 0 6px 0; font-size: 13.5px; color: #065f46;"><strong>Approved Category:</strong> {cat_name}</p>
        <p style="margin: 0; font-size: 13.5px; color: #065f46;"><strong>Venue:</strong> {venue or "Jamia Mosque Multi-Purpose Hall, Nairobi"}</p>
      </div>

      <p style="color: #475569;">
        Please ensure you arrive at the examination venue on time with your official national ID or birth certificate.
      </p>

      <p style="color: #006838; font-weight: 700; margin-top: 24px; margin-bottom: 0;">
        جزاكم الله خيراً وبارك الله فيكم
      </p>
    """

    subject = f"Registration Approved: {student.full_name} ({ref_str}) | Jamia Quran Competition"
    body_text = f"Congratulations {student.full_name}!\nYour registration for {cat_name} has been APPROVED.\nReference: {ref_str}\n\nJamia Mosque Committee"
    html_body = _get_email_wrapper(subject, content)

    if recipient:
        await _send_resend_email(recipient, subject, body_text, html_body)

    if student.guardian_phone:
        sms_text = f"Musabaqa: {student.full_name} approved for {cat_name}. Venue: Jamia Mosque Nairobi. Ref: {ref_str}"
        await _send_at_sms(student.guardian_phone, sms_text)


async def notify_student_rejected(student, institution) -> None:
    """Sends candidate rejection notice with reason."""
    recipient = student.email or (institution.email if institution else None)
    reason = student.rejection_reason or "Document verification requirements not met"
    ref_str = f"REF-{student.id:05d}"

    content = f"""
      <p style="font-size: 16px; font-weight: 700; color: #006838; margin-top: 0;">
        Assalamu Alaikum wa Rahmatullahi wa Barakatuh,
      </p>
      <p style="font-size: 15px; font-weight: 600; color: #0f172a;">
        Dear <strong>{student.full_name}</strong>,
      </p>
      <p style="color: #475569;">
        The registration entry (ID: <strong>{ref_str}</strong>) was reviewed by the screening committee and was not approved.
      </p>

      <div style="background-color: #fef2f2; border-left: 4px solid #dc2626; padding: 14px 16px; margin: 18px 0; border-radius: 6px;">
        <p style="font-size: 12px; font-weight: 800; color: #991b1b; margin: 0 0 4px 0;">Reason for Rejection:</p>
        <p style="font-size: 13.5px; color: #7f1d1d; margin: 0;">{reason}</p>
      </div>

      <p style="color: #006838; font-weight: 700; margin-top: 24px; margin-bottom: 0;">
        جزاكم الله خيراً
      </p>
    """

    subject = f"Registration Update: {student.full_name} ({ref_str}) | Jamia Quran Competition"
    body_text = f"Assalamu Alaikum {student.full_name},\nYour registration was not approved. Reason: {reason}\n\nJamia Mosque Committee"
    html_body = _get_email_wrapper(subject, content)

    if recipient:
        await _send_resend_email(recipient, subject, body_text, html_body)


async def send_institution_registration_review_email(
    institution,
    region_name: str | None = None,
    county_name: str | None = None,
) -> bool:
    """
    Sends an ultra-premium registration review & accreditation receipt email to the institution
    via Resend upon initial account creation.
    """
    is_ar = institution.preferred_language == "AR" or getattr(institution, "preferred_language", None) == PreferredLanguage.AR
    inst_name = institution.name or "Honorable Madrasa / Institution"
    contact_person = institution.contact_person or "Administrator"
    ref_id = f"REF-INST-{institution.id:04d}" if institution.id else "REF-INST-PENDING"
    inst_type = getattr(institution, "type", "MADRASA")
    type_str = str(inst_type).replace("InstitutionType.", "").title()
    login_url = "http://localhost:3000/ar/login" if is_ar else "http://localhost:3000/en/login"
    location_str = f"{region_name or 'Nairobi'} ({county_name or 'Kenya'})"

    if is_ar:
        subject = f"تأكيد تسجيل المؤسسة وملف الاعتماد ({ref_id}) | مسابقة مسجد جامع نيروبي"
        content = f"""
          <div style="text-align: center; margin-bottom: 24px;">
            <p style="font-family: 'Traditional Arabic', 'Scheherazade', 'Amiri', Tahoma, serif; font-size: 20px; font-weight: bold; color: #006838; margin: 0 0 8px 0; letter-spacing: 0.05em;">
              بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ
            </p>
            <h2 style="font-size: 18px; font-weight: 800; color: #0f172a; margin: 0;">
              السلام عليكم ورحمة الله وبركاته
            </h2>
            <p style="font-size: 13px; color: #64748b; margin-top: 4px;">
              تحية طيبة مباركة من لجنة مسابقة القرآن الكريم — مسجد جامع نيروبي
            </p>
          </div>

          <p style="font-size: 14.5px; color: #334155; line-height: 1.7; margin-bottom: 20px;">
            يسرنا إبلاغكم بأنه تم استلام طلب تسجيل مؤسستكم <strong>«{inst_name}»</strong> بنجاح في البوابة الرسمية لمسابقة حفظ القرآن الكريم السنوية لعام ٢٠٢٦.
            طلبكم قيد المراجعة والتدقيق حالياً لدى اللجنة المنظمة للاعتماد الرسمي.
          </p>

          <!-- Institution Details Card -->
          <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin: 24px 0; box-shadow: inset 0 1px 2px rgba(0,0,0,0.02);">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 14px;">
              <span style="font-size: 12px; font-weight: 800; color: #006838; text-transform: uppercase; letter-spacing: 0.05em;">
                بيانات التسجيل الرسمية
              </span>
              <span style="font-family: monospace; font-size: 11.5px; font-weight: 800; background-color: #fef3c7; color: #92400e; border: 1px solid #fde68a; padding: 3px 8px; border-radius: 6px;">
                {ref_id}
              </span>
            </div>

            <table width="100%" cellpadding="6" cellspacing="0" style="font-size: 13px; color: #334155; text-align: right;">
              <tr>
                <td style="color: #64748b; width: 35%; font-weight: 600;">اسم المؤسسة:</td>
                <td style="font-weight: 700; color: #0f172a;">{inst_name}</td>
              </tr>
              <tr>
                <td style="color: #64748b; font-weight: 600;">نوع المؤسسة:</td>
                <td>{type_str}</td>
              </tr>
              <tr>
                <td style="color: #64748b; font-weight: 600;">المسؤول / الأستاذ المشرف:</td>
                <td>{contact_person} ({institution.phone})</td>
              </tr>
              <tr>
                <td style="color: #64748b; font-weight: 600;">البريد الإلكتروني:</td>
                <td style="font-family: monospace; color: #006838;">{institution.email}</td>
              </tr>
              <tr>
                <td style="color: #64748b; font-weight: 600;">المنطقة / المقاطعة:</td>
                <td>{location_str}</td>
              </tr>
            </table>
          </div>

          <!-- Status Roadmap -->
          <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 12px; padding: 18px 20px; margin: 24px 0;">
            <p style="font-size: 13px; font-weight: 800; color: #166534; margin: 0 0 10px 0;">
              خطة المراجعة والاعتماد:
            </p>
            <ul style="margin: 0; padding-right: 20px; font-size: 13px; color: #15803d; line-height: 1.8;">
              <li><strong>تم الاستلام:</strong> إنشاء الحساب وملف المؤسسة (مكتمل ✓)</li>
              <li><strong>قيد المراجعة:</strong> مراجعة مستندات وصور المدرسة من قبل اللجنة (جارٍ ⏳)</li>
              <li><strong>الخطوة التالية:</strong> تسجيل حتى 4 طلاب من حفظة القرآن وإصدار بطاقات المشاركة</li>
            </ul>
          </div>

          <!-- CTA Button -->
          <div style="text-align: center; margin: 32px 0;">
            <a href="{login_url}" style="background: linear-gradient(135deg, #006838 0%, #004d29 100%); color: #ffffff; text-decoration: none; padding: 14px 32px; font-size: 14px; font-weight: bold; border-radius: 8px; display: inline-block; box-shadow: 0 4px 12px rgba(0, 104, 56, 0.25); border: 1px solid #004d29;">
              الدخول إلى بوابة المؤسسة وإدارة الطلاب &larr;
            </a>
          </div>

          <p style="font-size: 12.5px; color: #64748b; line-height: 1.6; margin-top: 24px;">
            * ملاحظة: يمكنك الدخول في أي وقت لرفع صور إضافية للمعلم والفصول أو فيديو تعريفي لتسريع عملية الاعتماد.
          </p>

          <div style="border-top: 1px solid #e2e8f0; padding-top: 16px; margin-top: 24px; text-align: center;">
            <p style="font-size: 14px; font-weight: 700; color: #006838; margin: 0 0 4px 0;">
              وفقكم الله وسدد خطاكم في خدمة كتاب الله الكريم
            </p>
            <p style="font-size: 12px; color: #94a3b8; margin: 0;">
              لجنة مسابقة القرآن الكريم &bull; مسجد جامع نيروبي
            </p>
          </div>
        """
        body_text = f"""بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ\nالسلام عليكم ورحمة الله وبركاته،\n\nتم استلام طلب تسجيل مؤسستكم ({inst_name}) في مسابقة مسجد جامع نيروبي بنجاح.\nرقم المرجع: {ref_id}\n\nيمكنكم تسجيل الدخول ومتابعة ملف الاعتماد عبر: {login_url}\n\nلجنة مسابقة القرآن الكريم - مسجد جامع نيروبي"""

    else:
        subject = f"Registration Received & Under Review ({ref_id}) | Jamia Mosque Musabaqa 2026"
        content = f"""
          <div style="text-align: center; margin-bottom: 24px;">
            <p style="font-family: 'Traditional Arabic', 'Scheherazade', 'Amiri', Tahoma, serif; font-size: 18px; font-weight: bold; color: #c99335; margin: 0 0 6px 0;">
              بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ
            </p>
            <h2 style="font-size: 19px; font-weight: 800; color: #0f172a; margin: 0;">
              Assalamu Alaikum wa Rahmatullahi wa Barakatuh
            </h2>
            <p style="font-size: 13px; color: #64748b; margin-top: 4px;">
              Official Notification from Jamia Mosque Quran Competition Secretariat
            </p>
          </div>

          <p style="font-size: 14.5px; color: #334155; line-height: 1.7; margin-bottom: 20px;">
            We are pleased to confirm that the registration entry for <strong>{inst_name}</strong> has been successfully received and submitted for accreditation screening for the <strong>Jamia Mosque Annual Quran Memorization Competition 2026</strong>.
          </p>

          <!-- Institution Details Card -->
          <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; margin: 24px 0; box-shadow: inset 0 1px 2px rgba(0,0,0,0.02);">
            <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e2e8f0; padding-bottom: 12px; margin-bottom: 14px;">
              <span style="font-size: 11.5px; font-weight: 800; color: #006838; text-transform: uppercase; letter-spacing: 0.08em;">
                OFFICIAL REGISTRATION DOSSIER
              </span>
              <span style="font-family: monospace; font-size: 11.5px; font-weight: 800; background-color: #fef3c7; color: #92400e; border: 1px solid #fde68a; padding: 3px 8px; border-radius: 6px;">
                {ref_id}
              </span>
            </div>

            <table width="100%" cellpadding="6" cellspacing="0" style="font-size: 13px; color: #334155;">
              <tr>
                <td style="color: #64748b; width: 35%; font-weight: 600;">Institution Name:</td>
                <td style="font-weight: 700; color: #0f172a;">{inst_name}</td>
              </tr>
              <tr>
                <td style="color: #64748b; font-weight: 600;">Institution Type:</td>
                <td>{type_str}</td>
              </tr>
              <tr>
                <td style="color: #64748b; font-weight: 600;">Head Ustadh / Contact:</td>
                <td>{contact_person} ({institution.phone})</td>
              </tr>
              <tr>
                <td style="color: #64748b; font-weight: 600;">Official Email:</td>
                <td style="font-family: monospace; color: #006838;">{institution.email}</td>
              </tr>
              <tr>
                <td style="color: #64748b; font-weight: 600;">Registered Location:</td>
                <td>{location_str}</td>
              </tr>
            </table>
          </div>

          <!-- Status Roadmap -->
          <div style="background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 12px; padding: 18px 20px; margin: 24px 0;">
            <p style="font-size: 13px; font-weight: 800; color: #166534; margin: 0 0 10px 0;">
              Accreditation & Review Roadmap:
            </p>
            <ul style="margin: 0; padding-left: 20px; font-size: 13px; color: #15803d; line-height: 1.8;">
              <li><strong>Step 1: Account Created & Dossier Logged</strong> (Completed ✓)</li>
              <li><strong>Step 2: Committee Verification & Quota Allocation</strong> (Under Review ⏳)</li>
              <li><strong>Step 3: Register up to 4 Student Contestants</strong> (1 candidate per category)</li>
            </ul>
          </div>

          <!-- Action Guidance -->
          <p style="font-size: 13.5px; color: #475569; line-height: 1.6;">
            While your accreditation review is underway, you may log in to your institutional portal to manage your profile, upload supporting madrasa/teacher media, and prepare your student candidates.
          </p>

          <!-- Primary CTA Button -->
          <div style="text-align: center; margin: 32px 0;">
            <a href="{login_url}" style="background: linear-gradient(135deg, #006838 0%, #004d29 100%); color: #ffffff; text-decoration: none; padding: 14px 32px; font-size: 14px; font-weight: bold; border-radius: 8px; display: inline-block; box-shadow: 0 4px 12px rgba(0, 104, 56, 0.25); border: 1px solid #004d29;">
              Access Institution Portal &rarr;
            </a>
          </div>

          <div style="border-top: 1px solid #e2e8f0; padding-top: 18px; margin-top: 28px; text-align: center;">
            <p style="font-size: 13.5px; font-weight: 700; color: #006838; margin: 0 0 4px 0;">
              May Allah ﷻ bless your madrasa and student efforts.
            </p>
            <p style="font-size: 11.5px; color: #94a3b8; margin: 0;">
              Jamia Mosque Committee &bull; Musabaqa Organizing Secretariat &bull; Kigali Road, Nairobi
            </p>
          </div>
        """
        body_text = f"""Assalamu Alaikum wa Rahmatullahi wa Barakatuh,\n\nWe have received the registration entry for {inst_name} ({ref_id}) for the Jamia Mosque Quran Memorization Competition 2026.\n\nYour application is currently under review by the screening committee.\nYou can access your portal here: {login_url}\n\nJamia Mosque Committee Secretariat"""

    html_body = _get_email_wrapper(subject, content, lang="AR" if is_ar else "EN")
    return await _send_resend_email(institution.email, subject, body_text, html_body)


async def notify_institution_approved(institution) -> None:
    content = f"""
      <p style="font-size: 16px; font-weight: 700; color: #006838; margin-top: 0;">Assalamu Alaikum,</p>
      <p>We are pleased to inform you that <strong>{institution.name}</strong> has been approved to participate in the Jamia Quran Memorization Competition 2026.</p>
      <p>You may now log in to the portal to register candidates from your institution.</p>
      <p style="color: #006838; font-weight: 700; margin-top: 24px;">جزاكم الله خيراً</p>
    """
    subject = "Institution Registration Approved | Jamia Mosque Committee"
    body_text = f"Assalamu Alaikum,\n{institution.name} has been approved to participate in Jamia Quran Competition.\n\nJamia Mosque Committee"
    html_body = _get_email_wrapper(subject, content)
    await _send_resend_email(institution.email, subject, body_text, html_body)


async def notify_institution_rejected(institution) -> None:
    content = f"""
      <p style="font-size: 16px; font-weight: 700; color: #006838; margin-top: 0;">Assalamu Alaikum,</p>
      <p>The registration for institution <strong>{institution.name}</strong> was not approved.</p>
      <p><strong>Reason:</strong> {institution.rejection_reason or 'Quota / verification requirements'}</p>
      <p style="color: #006838; font-weight: 700; margin-top: 24px;">جزاكم الله خيراً</p>
    """
    subject = "Institution Registration Update | Jamia Mosque Committee"
    body_text = f"Assalamu Alaikum,\nRegistration for {institution.name} was not approved. Reason: {institution.rejection_reason}\n\nJamia Mosque Committee"
    html_body = _get_email_wrapper(subject, content)
    await _send_resend_email(institution.email, subject, body_text, html_body)

