"""
Notification service — bilingual (EN/AR) dispatcher.

Channels:
  - Resend (transactional email)
  - Knock (in-app notifications)
  - Africa's Talking (SMS)

SMS triggers (Africa's Talking):
  1. Student APPROVED after registration
  2. Student advances Preliminary → Finals
  3. Student confirmed in Finals

Template selection is based on recipient's stored preferred_language.
"""

import logging
from typing import Any

from app.core.config import settings
from app.models.admin_user import PreferredLanguage

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Email templates (EN + AR pairs)
# ---------------------------------------------------------------------------

EMAIL_TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "institution_approved": {
        "EN": {
            "subject": "Your Institution Registration Has Been Approved",
            "body": (
                "Dear {contact_person},\n\n"
                "We are pleased to inform you that {institution_name} has been approved "
                "to participate in the Jamia Mosque Nairobi Quran Memorization Competition.\n\n"
                "You may now log in to register your students.\n\nJazakumullahu Khairan."
            ),
        },
        "AR": {
            "subject": "تمت الموافقة على تسجيل مؤسستكم",
            "body": (
                "السلام عليكم ورحمة الله وبركاته،\n\n"
                "يسعدنا إخباركم بأن {institution_name} قد تمت الموافقة على مشاركتها "
                "في مسابقة جامع ناروبي لحفظ القرآن الكريم.\n\n"
                "يمكنكم الآن تسجيل الدخول لتسجيل الطلاب.\n\nجزاكم الله خيراً."
            ),
        },
    },
    "institution_rejected": {
        "EN": {
            "subject": "Institution Registration Update",
            "body": (
                "Dear {contact_person},\n\n"
                "We regret to inform you that the registration of {institution_name} "
                "has not been approved.\n\nReason: {reason}\n\n"
                "Please contact us if you have any questions."
            ),
        },
        "AR": {
            "subject": "تحديث بشأن تسجيل المؤسسة",
            "body": (
                "السلام عليكم،\n\n"
                "نأسف لإبلاغكم بأن طلب تسجيل {institution_name} لم يتم قبوله.\n\n"
                "السبب: {reason}\n\n"
                "يرجى التواصل معنا إذا كان لديكم أي استفسار."
            ),
        },
    },
    "student_approved": {
        "EN": {
            "subject": "Student Registration Approved",
            "body": (
                "Dear {contact_person},\n\n"
                "The registration of {student_name} has been approved for the "
                "{category_name} category.\n\nWe look forward to their participation."
            ),
        },
        "AR": {
            "subject": "تمت الموافقة على تسجيل الطالب",
            "body": (
                "السلام عليكم،\n\n"
                "تمت الموافقة على تسجيل {student_name} في فئة {category_name}.\n\n"
                "نتطلع إلى مشاركتهم."
            ),
        },
    },
    "student_rejected": {
        "EN": {
            "subject": "Student Registration Update",
            "body": (
                "Dear {contact_person},\n\n"
                "The registration of {student_name} was not approved.\n\n"
                "Reason: {reason}"
            ),
        },
        "AR": {
            "subject": "تحديث بشأن تسجيل الطالب",
            "body": (
                "السلام عليكم،\n\n"
                "لم تتم الموافقة على تسجيل {student_name}.\n\n"
                "السبب: {reason}"
            ),
        },
    },
    "student_regret": {
        "EN": {
            "subject": "Musabaqa Participation Update",
            "body": (
                "Dear {contact_person},\n\n"
                "We regret to inform you that {student_name} has not been selected "
                "to advance in the competition at this time.\n\n"
                "We appreciate their effort and encourage continued learning."
            ),
        },
        "AR": {
            "subject": "تحديث بشأن المشاركة في المسابقة",
            "body": (
                "السلام عليكم،\n\n"
                "نأسف لإخباركم بأنه لم يتم اختيار {student_name} "
                "للتقدم في المسابقة في هذه المرحلة.\n\n"
                "نقدر جهودهم ونشجع على الاستمرار في التعلم."
            ),
        },
    },
    "student_advanced_to_finals": {
        "EN": {
            "subject": "🎉 Congratulations! Selected for the Finals",
            "body": (
                "Dear {contact_person},\n\n"
                "Congratulations! {student_name} has successfully advanced to the "
                "FINALS of the Jamia Mosque Nairobi Quran Memorization Competition.\n\n"
                "Venue: {venue}\nDate: {date}\n\nJazakumullahu Khairan."
            ),
        },
        "AR": {
            "subject": "🎉 تهانينا! تم الاختيار للنهائيات",
            "body": (
                "السلام عليكم،\n\n"
                "تهانينا! لقد تأهل {student_name} إلى المرحلة النهائية "
                "من مسابقة جامع ناروبي لحفظ القرآن الكريم.\n\n"
                "المكان: {venue}\nالتاريخ: {date}\n\nجزاكم الله خيراً."
            ),
        },
    },
}

SMS_TEMPLATES: dict[str, dict[str, str]] = {
    "student_approved_sms": {
        "EN": (
            "Musabaqa: {student_name} approved for {category_name}. "
            "Venue: {venue}. Date: {date}. JMC Nairobi"
        ),
        "AR": (
            "مسابقة: تمت الموافقة على {student_name} لفئة {category_name}. "
            "المكان: {venue}. التاريخ: {date}. جامع ناروبي"
        ),
    },
    "student_preliminary_passed": {
        "EN": (
            "Musabaqa: Congratulations! {student_name} has passed the Preliminary "
            "round and advances to the Finals. Venue: {venue}. Date: {date}. JMC"
        ),
        "AR": (
            "مسابقة: تهانينا! اجتاز {student_name} الدور التمهيدي وتأهل للنهائي. "
            "المكان: {venue}. التاريخ: {date}. جامع ناروبي"
        ),
    },
    "student_confirmed_finals": {
        "EN": (
            "Musabaqa: {student_name} is confirmed for the Finals. "
            "Venue: {venue}. Date: {date}. JMC Nairobi"
        ),
        "AR": (
            "مسابقة: تم تأكيد مشاركة {student_name} في النهائيات. "
            "المكان: {venue}. التاريخ: {date}. جامع ناروبي"
        ),
    },
}

KNOCK_EVENTS: dict[str, str] = {
    "institution_approved": "institution-approved",
    "institution_rejected": "institution-rejected",
    "student_approved": "student-approved",
    "student_rejected": "student-rejected",
    "student_advanced_to_finals": "student-advanced-finals",
}


# ---------------------------------------------------------------------------
# Resend (email)
# ---------------------------------------------------------------------------

async def _send_resend_email(
    to: str,
    subject: str,
    body: str,
) -> None:
    if not settings.RESEND_API_KEY:
        logger.warning("RESEND_API_KEY not set — skipping email to %s", to)
        return
    try:
        import resend
        resend.api_key = settings.RESEND_API_KEY
        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": [to],
            "subject": subject,
            "text": body,
        })
    except Exception as exc:
        logger.error("Resend error: %s", exc)


def _pick_lang(lang: str | None) -> str:
    return "AR" if lang == PreferredLanguage.AR else "EN"


# ---------------------------------------------------------------------------
# Africa's Talking (SMS)
# ---------------------------------------------------------------------------

async def _send_at_sms(phone: str, message: str) -> None:
    if not settings.AT_API_KEY:
        logger.warning("AT_API_KEY not set — skipping SMS to %s", phone)
        return
    try:
        import africastalking
        africastalking.initialize(settings.AT_USERNAME, settings.AT_API_KEY)
        sms = africastalking.SMS
        sms.send(message, [phone], sender_id=settings.AT_SENDER_ID)
    except Exception as exc:
        logger.error("Africa's Talking SMS error: %s", exc)


# ---------------------------------------------------------------------------
# Knock (in-app)
# ---------------------------------------------------------------------------

async def _send_knock_notification(
    recipient_id: str, event_key: str, data: dict[str, Any]
) -> None:
    if not settings.KNOCK_API_KEY:
        logger.warning("KNOCK_API_KEY not set — skipping knock notification")
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
# Public API
# ---------------------------------------------------------------------------

async def notify_institution_approved(institution) -> None:
    lang = _pick_lang(institution.preferred_language)
    tmpl = EMAIL_TEMPLATES["institution_approved"][lang]
    body = tmpl["body"].format(
        contact_person=institution.contact_person,
        institution_name=institution.name,
    )
    await _send_resend_email(institution.email, tmpl["subject"], body)
    await _send_knock_notification(
        str(institution.id),
        KNOCK_EVENTS["institution_approved"],
        {"institution_name": institution.name},
    )


async def notify_institution_rejected(institution) -> None:
    lang = _pick_lang(institution.preferred_language)
    tmpl = EMAIL_TEMPLATES["institution_rejected"][lang]
    body = tmpl["body"].format(
        contact_person=institution.contact_person,
        institution_name=institution.name,
        reason=institution.rejection_reason or "",
    )
    await _send_resend_email(institution.email, tmpl["subject"], body)
    await _send_knock_notification(
        str(institution.id),
        KNOCK_EVENTS["institution_rejected"],
        {"reason": institution.rejection_reason},
    )


async def notify_student_approved(student, institution, category, venue: str = "", date: str = "") -> None:
    lang = _pick_lang(institution.preferred_language)
    tmpl = EMAIL_TEMPLATES["student_approved"][lang]
    cat_name = category.name_ar if lang == "AR" else category.name_en
    body = tmpl["body"].format(
        contact_person=institution.contact_person,
        student_name=student.full_name,
        category_name=cat_name,
    )
    await _send_resend_email(institution.email, tmpl["subject"], body)

    # SMS: notify on approval (lifecycle event 1)
    sms_tmpl = SMS_TEMPLATES["student_approved_sms"][lang]
    sms_text = sms_tmpl.format(
        student_name=student.full_name,
        category_name=cat_name,
        venue=venue or "TBD",
        date=date or "TBD",
    )
    await _send_at_sms(institution.phone, sms_text)

    await _send_knock_notification(
        str(institution.id),
        KNOCK_EVENTS["student_approved"],
        {"student_name": student.full_name},
    )


async def notify_student_rejected(student, institution) -> None:
    lang = _pick_lang(institution.preferred_language)
    tmpl = EMAIL_TEMPLATES["student_rejected"][lang]
    body = tmpl["body"].format(
        contact_person=institution.contact_person,
        student_name=student.full_name,
        reason=student.rejection_reason or "",
    )
    await _send_resend_email(institution.email, tmpl["subject"], body)
    await _send_knock_notification(
        str(institution.id),
        KNOCK_EVENTS["student_rejected"],
        {"student_name": student.full_name, "reason": student.rejection_reason},
    )


async def notify_student_advanced_to_finals(
    student, institution, category, venue: str = "", date: str = ""
) -> None:
    """Lifecycle event 2: student passes Preliminary → Finals."""
    lang = _pick_lang(institution.preferred_language)
    tmpl = EMAIL_TEMPLATES["student_advanced_to_finals"][lang]
    cat_name = category.name_ar if lang == "AR" else category.name_en
    body = tmpl["body"].format(
        contact_person=institution.contact_person,
        student_name=student.full_name,
        venue=venue or "TBD",
        date=date or "TBD",
    )
    await _send_resend_email(institution.email, tmpl["subject"], body)

    # SMS: lifecycle event 2
    sms_tmpl = SMS_TEMPLATES["student_preliminary_passed"][lang]
    sms_text = sms_tmpl.format(
        student_name=student.full_name,
        venue=venue or "TBD",
        date=date or "TBD",
    )
    await _send_at_sms(institution.phone, sms_text)

    await _send_knock_notification(
        str(institution.id),
        KNOCK_EVENTS["student_advanced_to_finals"],
        {"student_name": student.full_name},
    )


async def notify_student_confirmed_finals(
    student, institution, venue: str = "", date: str = ""
) -> None:
    """Lifecycle event 3: student confirmed in Finals."""
    lang = _pick_lang(institution.preferred_language)
    sms_tmpl = SMS_TEMPLATES["student_confirmed_finals"][lang]
    sms_text = sms_tmpl.format(
        student_name=student.full_name,
        venue=venue or "TBD",
        date=date or "TBD",
    )
    await _send_at_sms(institution.phone, sms_text)


async def send_regret_email(student, institution) -> None:
    lang = _pick_lang(institution.preferred_language)
    tmpl = EMAIL_TEMPLATES["student_regret"][lang]
    body = tmpl["body"].format(
        contact_person=institution.contact_person,
        student_name=student.full_name,
    )
    await _send_resend_email(institution.email, tmpl["subject"], body)
