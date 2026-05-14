import os
import ssl
import shutil
from datetime import datetime, timedelta, date
from email.header import decode_header
from email.message import Message
from typing import Optional

import logging
import imaplib
import subprocess
import sys
import re
from dateutil import parser as date_parser
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

# Для инициализации COM в потоке, где работает планировщик (Windows)
try:
    import pythoncom  # type: ignore
except ImportError:
    pythoncom = None

from config import (
    IMAP_HOST,
    IMAP_PORT,
    IMAP_EMAIL,
    IMAP_PASSWORD,
    ALLOWED_SENDER,
    INCOMING_DIR,
    ARCHIVE_DIR,
    ADMIN_CHAT_IDS,
)
from storage import (
    save_schedule,
    get_schedule,
    get_subscribers_with_settings,
    save_parsed_lessons,
    remove_subscriber,
    is_email_processed,
    mark_email_processed,
    get_lessons_by_group,
    get_lessons_by_teacher,
    was_schedule_notification_sent,
    mark_schedule_notification_sent,
    bump_group_missing_count,
    reset_group_missing_count,
    add_mail_event,
)


def _decode_header(value: str) -> str:
    if not value:
        return ""
    decoded_fragments = decode_header(value)
    parts = []
    for text, enc in decoded_fragments:
        if isinstance(text, bytes):
            parts.append(text.decode(enc or "utf-8", errors="ignore"))
        else:
            parts.append(text)
    return "".join(parts)


def _parse_email_date(msg: Message) -> datetime:
    date_hdr = msg.get("Date")
    if not date_hdr:
        return datetime.utcnow()
    try:
        dt = date_parser.parse(date_hdr)
        if not dt.tzinfo:
            return dt
        return dt.astimezone().replace(tzinfo=None)
    except Exception:
        return datetime.utcnow()


def _extract_schedule_date_from_subject(subject: str, fallback_email_date: datetime) -> date:
    """
    Пытается вытащить дату из темы письма.

    Поддерживаем варианты:
    - 'расписание занятий на 28.01.2026'
    - 'ИЗМЕНЕНИЯ В РАСПИСАНИЕ НА 08.12.25'
    - 'изменение на завтра' / 'изменения на завтра' и т.п.
    """
    lower = subject.lower()

    # 1) Явная дата в формате дд.мм.гг или дд.мм.гггг
    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})", subject)
    if m:
        day = int(m.group(1))
        month = int(m.group(2))
        year_raw = int(m.group(3))
        if year_raw < 100:
            # 00-69 -> 2000+, 70-99 -> 1900+ (на всякий случай)
            year = 2000 + year_raw if year_raw < 70 else 1900 + year_raw
        else:
            year = year_raw
        try:
            return date(year, month, day)
        except ValueError:
            # Неверная дата — игнорируем и идём дальше
            pass

    # 2) Фразы типа "на завтра", "на сегодня", "на вчера"
    base = fallback_email_date.date()
    if "на завтра" in lower:
        return base + timedelta(days=1)
    if "на сегодня" in lower:
        return base
    if "на вчера" in lower:
        return base - timedelta(days=1)

    # 3) По умолчанию: как и раньше, завтрашний день относительно даты письма
    return (fallback_email_date + timedelta(days=1)).date()


def _ensure_dirs() -> None:
    os.makedirs(INCOMING_DIR, exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)


def _find_libreoffice() -> Optional[str]:
    """Найти путь к LibreOffice (soffice) на системе."""
    # 1) shutil.which — ищет в PATH
    soffice = shutil.which("soffice")
    if soffice:
        return soffice

    # 2) Типичные пути установки на Windows
    if sys.platform.startswith("win"):
        candidates = [
            os.path.join(os.environ.get("PROGRAMFILES", r"C:\Program Files"), "LibreOffice", "program", "soffice.exe"),
            os.path.join(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"), "LibreOffice", "program", "soffice.exe"),
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path

    return None


def _convert_via_libreoffice(soffice_path: str, tmp_word_path: str, pdf_path: str) -> str:
    """Конвертация через LibreOffice в headless-режиме."""
    out_dir = os.path.dirname(pdf_path)
    os.makedirs(out_dir, exist_ok=True)
    cmd = [
        soffice_path,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        out_dir,
        tmp_word_path,
    ]
    logger.info("LibreOffice conversion: %s", " ".join(cmd))
    subprocess.run(cmd, check=True)
    # LibreOffice называет файл по исходному имени
    base = os.path.splitext(os.path.basename(tmp_word_path))[0]
    generated_pdf = os.path.join(out_dir, base + ".pdf")
    if generated_pdf != pdf_path:
        if os.path.exists(pdf_path):
            os.remove(pdf_path)
        os.replace(generated_pdf, pdf_path)
    return pdf_path


def _convert_to_pdf(tmp_word_path: str, pdf_path: str) -> str:
    """
    Конвертация DOC/DOCX -> PDF.
    1) На Windows: пробуем docx2pdf (COM/Word)
    2) Если не удалось — пробуем LibreOffice
    3) Если ничего не доступно — понятная ошибка
    """
    errors = []

    # --- Попытка 1: docx2pdf (Windows COM / MS Word) ---
    if sys.platform.startswith("win"):
        try:
            from docx2pdf import convert as docx2pdf_convert
            logger.info("Trying docx2pdf (MS Word COM) for %s", tmp_word_path)
            if pythoncom is not None:
                pythoncom.CoInitialize()
            try:
                docx2pdf_convert(tmp_word_path, pdf_path)
            finally:
                if pythoncom is not None:
                    pythoncom.CoUninitialize()
            logger.info("docx2pdf conversion successful: %s", pdf_path)
            return pdf_path
        except Exception as e:
            logger.warning("docx2pdf failed: %s", e)
            errors.append(f"docx2pdf (MS Word): {e}")

    # --- Попытка 2: LibreOffice ---
    soffice = _find_libreoffice()
    if soffice:
        try:
            logger.info("Trying LibreOffice at %s", soffice)
            return _convert_via_libreoffice(soffice, tmp_word_path, pdf_path)
        except Exception as e:
            logger.warning("LibreOffice conversion failed: %s", e)
            errors.append(f"LibreOffice ({soffice}): {e}")
    else:
        logger.info("LibreOffice (soffice) not found on system")
        errors.append("LibreOffice: не найден (soffice отсутствует в PATH и стандартных папках)")

    # --- Ничего не сработало ---
    msg = (
        "Не удалось конвертировать Word в PDF.\n"
        "Попробованные способы:\n"
        + "\n".join(f"  - {e}" for e in errors)
        + "\n\nУстановите Microsoft Word (+ pip install docx2pdf) "
        "или LibreOffice (https://www.libreoffice.org)."
    )
    raise RuntimeError(msg)


def _connect_imap() -> Optional[imaplib.IMAP4_SSL]:
    missing = [
        name
        for name, value in (
            ("IMAP_EMAIL", IMAP_EMAIL),
            ("IMAP_PASSWORD", IMAP_PASSWORD),
            ("ALLOWED_SENDER", ALLOWED_SENDER),
        )
        if not value
    ]
    if missing:
        detail = "IMAP is not configured, missing: " + ", ".join(missing)
        logger.warning(detail)
        add_mail_event("warning", "imap_config", detail)
        return None

    try:
        logger.info("Connecting to IMAP %s as %s, looking for sender: %s", IMAP_HOST, IMAP_EMAIL, ALLOWED_SENDER)
        context = ssl.create_default_context()
        imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=context)
        imap.login(IMAP_EMAIL, IMAP_PASSWORD)
        return imap
    except Exception as e:
        detail = f"IMAP connect error: {e}"
        logger.warning(detail)
        add_mail_event("error", "imap_connect", detail)
        return None


def _iter_schedule_attachments(msg: Message):
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = part.get_filename()
        if not filename:
            continue
        decoded_name = _decode_header(filename)
        lower = decoded_name.lower()
        if lower.endswith(".doc") or lower.endswith(".docx"):
            yield decoded_name, part, "word"
        elif lower.endswith(".pdf"):
            yield decoded_name, part, "pdf"


def _schedule_pdf_path(schedule_date: date) -> str:
    pdf_name = f"Р Р°СЃРїРёСЃР°РЅРёРµ_{schedule_date.isoformat()}.pdf"
    year_dir = os.path.join(ARCHIVE_DIR, str(schedule_date.year))
    month_dir = os.path.join(year_dir, f"{schedule_date.month:02d}")
    os.makedirs(month_dir, exist_ok=True)
    return os.path.join(month_dir, pdf_name)


def _attachment_to_pdf(filename: str, part: Message, schedule_date: date) -> str:
    file_bytes = part.get_payload(decode=True)
    if not file_bytes:
        raise ValueError("empty attachment")

    pdf_path = _schedule_pdf_path(schedule_date)
    if filename.lower().endswith(".pdf"):
        with open(pdf_path, "wb") as f:
            f.write(file_bytes)
        logger.info("Saved PDF attachment %s -> %s", filename, pdf_path)
        return pdf_path

    base_name = os.path.splitext(os.path.basename(filename))[0]
    tmp_word_path = os.path.join(
        INCOMING_DIR,
        f"{base_name}_{int(datetime.utcnow().timestamp())}.docx",
    )
    try:
        with open(tmp_word_path, "wb") as f:
            f.write(file_bytes)
        logger.info("Converting %s -> %s", tmp_word_path, pdf_path)
        return _convert_to_pdf(tmp_word_path, pdf_path)
    finally:
        try:
            if os.path.exists(tmp_word_path):
                os.remove(tmp_word_path)
        except Exception:
            pass


def _alert_admins(bot: Optional[Bot], title: str, detail: str) -> None:
    if not bot or not ADMIN_CHAT_IDS:
        return
    text = f"⚠️ {title}\n\n{detail}"
    for admin_id in ADMIN_CHAT_IDS:
        try:
            bot.send_message(chat_id=admin_id, text=text[:3500])
        except Exception as e:
            logger.warning("Admin alert to %s failed: %s", admin_id, e)


def process_mail(bot: Bot) -> None:
    """
    Проверка почты, конвертация Word->PDF, сохранение в архив и отправка уведомлений.
    """
    _ensure_dirs()
    imap = _connect_imap()
    if not imap:
        return

    try:
        imap.select("INBOX")

        # Ищем письма: непрочитанные ИЛИ за последние 7 дней (чтобы не терять уже прочитанные)
        since_date = (datetime.utcnow() - timedelta(days=7)).strftime("%d-%b-%Y")
        search_criteria = (
            '(OR (UNSEEN FROM "{sender}") (FROM "{sender}" SINCE "{since}"))'
        ).format(sender=ALLOWED_SENDER, since=since_date)
        status, data = imap.search(None, search_criteria)
        if status != "OK":
            logger.warning("IMAP search failed")
            add_mail_event("error", "imap_search", "IMAP search failed")
            return

        message_ids = data[0].split()
        if not message_ids:
            logger.info("No messages found from %s (criteria: %s)", ALLOWED_SENDER, search_criteria)
            return

        logger.info("Found %d message(s) from %s", len(message_ids), ALLOWED_SENDER)

        for msg_id in message_ids:
            status, msg_data = imap.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
            raw_email = msg_data[0][1]

            from email import message_from_bytes

            msg = message_from_bytes(raw_email)

            # Пропускаем уже обработанные письма по Message-ID
            email_message_id = msg.get("Message-ID", "")
            if not email_message_id:
                email_message_id = f"noid-{msg_id.decode() if isinstance(msg_id, bytes) else msg_id}"
            if is_email_processed(email_message_id):
                logger.debug("Skip already processed email: %s", email_message_id)
                continue

            email_date = _parse_email_date(msg)
            subject = _decode_header(msg.get("Subject", ""))
            schedule_date = _extract_schedule_date_from_subject(subject, email_date)

            attachments_found = False
            for filename, part, attachment_type in _iter_schedule_attachments(msg):
                attachments_found = True
                try:
                    pdf_path = _attachment_to_pdf(filename, part, schedule_date)

                    had_schedule = get_schedule(schedule_date) is not None
                    save_schedule(schedule_date, pdf_path, email_date)
                    try:
                        from schedule_parser import parse_schedule_pdf
                        parsed_date, groups_lessons = parse_schedule_pdf(pdf_path)
                        if parsed_date and groups_lessons:
                            save_parsed_lessons(parsed_date, groups_lessons)
                            logger.info("Parsed %d groups for %s", len(groups_lessons), parsed_date)
                    except Exception as e:
                        logger.warning("Parse schedule error: %s", e)
                        add_mail_event(
                            "warning",
                            "parse_schedule",
                            str(e),
                            message_id=email_message_id,
                            subject=subject,
                            schedule_date=schedule_date,
                        )
                    if not had_schedule:
                        notify_new_schedule(bot, schedule_date, pdf_path)
                    else:
                        notify_updated_schedule(bot, schedule_date, pdf_path)
                    add_mail_event(
                        "info",
                        "schedule_processed",
                        f"{'new' if not had_schedule else 'updated'} schedule saved from {attachment_type}: {pdf_path}",
                        message_id=email_message_id,
                        subject=subject,
                        schedule_date=schedule_date,
                    )

                except Exception as e:
                    logger.warning("Error processing attachment %s: %s", filename, e)
                    _alert_admins(
                        bot,
                        "Schedule processing error",
                        f"Email: {subject or email_message_id}\nFile: {filename}\nError: {e}",
                    )
                    add_mail_event(
                        "error",
                        "attachment_process",
                        f"{filename}: {e}",
                        message_id=email_message_id,
                        subject=subject,
                        schedule_date=schedule_date,
                    )
            mark_email_processed(email_message_id)
            if not attachments_found:
                logger.info("No schedule attachments in email %s, marked as processed", email_message_id)
                add_mail_event(
                    "info",
                    "no_schedule_attachments",
                    "No Word or PDF attachments in email, marked as processed",
                    message_id=email_message_id,
                    subject=subject,
                    schedule_date=schedule_date,
                )

    finally:
        try:
            imap.close()
            imap.logout()
        except Exception:
            pass


def scan_mailbox() -> list:
    """Сканирование почты: возвращает список писем с метаданными (без обработки).
    Каждый элемент: {id, subject, sender, date, attachments: [{name, type}]}."""
    _ensure_dirs()
    imap = _connect_imap()
    if not imap:
        return []
    result = []
    try:
        imap.select("INBOX", readonly=True)
        since_date = (datetime.utcnow() - timedelta(days=30)).strftime("%d-%b-%Y")
        search_criteria = '(FROM "{sender}" SINCE "{since}")'.format(
            sender=ALLOWED_SENDER, since=since_date
        )
        status, data = imap.search(None, search_criteria)
        if status != "OK":
            return []
        message_ids = data[0].split()
        from email import message_from_bytes
        for msg_id in message_ids[-30:]:  # последние 30
            status, msg_data = imap.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue
            raw_email = msg_data[0][1]
            msg = message_from_bytes(raw_email)
            email_date = _parse_email_date(msg)
            subject = _decode_header(msg.get("Subject", ""))
            sender = _decode_header(msg.get("From", ""))
            schedule_date = _extract_schedule_date_from_subject(subject, email_date)
            attachments = []
            for part in msg.walk():
                if part.get_content_maintype() == "multipart":
                    continue
                fname = part.get_filename()
                if fname:
                    decoded = _decode_header(fname)
                    lower = decoded.lower()
                    if lower.endswith((".doc", ".docx")):
                        atype = "word"
                    elif lower.endswith(".pdf"):
                        atype = "pdf"
                    else:
                        atype = "other"
                    attachments.append({"name": decoded, "type": atype})
            already_loaded = get_schedule(schedule_date) is not None
            result.append({
                "msg_id": msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id),
                "subject": subject,
                "sender": sender,
                "date": email_date.strftime("%d.%m.%Y %H:%M"),
                "schedule_date": schedule_date.isoformat(),
                "schedule_date_formatted": schedule_date.strftime("%d.%m.%Y"),
                "attachments": attachments,
                "has_word": any(a["type"] == "word" for a in attachments),
                "has_pdf": any(a["type"] == "pdf" for a in attachments),
                "has_schedule_file": any(a["type"] in ("word", "pdf") for a in attachments),
                "already_loaded": already_loaded,
            })
    finally:
        try:
            imap.close()
            imap.logout()
        except Exception:
            pass
    result.reverse()  # новые сверху
    return result


def process_single_mail(msg_id_str: str, bot: Optional[Bot] = None, notify: bool = False) -> dict:
    """Обработать конкретное письмо по msg_id: конвертация Word→PDF, сохранение."""
    _ensure_dirs()
    imap = _connect_imap()
    if not imap:
        return {"error": "Не удалось подключиться к IMAP"}
    try:
        imap.select("INBOX")
        msg_id_bytes = msg_id_str.encode() if isinstance(msg_id_str, str) else msg_id_str
        status, msg_data = imap.fetch(msg_id_bytes, "(RFC822)")
        if status != "OK":
            return {"error": "Письмо не найдено"}
        raw_email = msg_data[0][1]
        from email import message_from_bytes
        msg = message_from_bytes(raw_email)
        email_date = _parse_email_date(msg)
        subject = _decode_header(msg.get("Subject", ""))
        schedule_date = _extract_schedule_date_from_subject(subject, email_date)
        processed = 0
        for filename, part, attachment_type in _iter_schedule_attachments(msg):
            try:
                pdf_path = _attachment_to_pdf(filename, part, schedule_date)
                had_schedule = get_schedule(schedule_date) is not None
                save_schedule(schedule_date, pdf_path, email_date)
                try:
                    from schedule_parser import parse_schedule_pdf
                    parsed_date, groups_lessons = parse_schedule_pdf(pdf_path)
                    if parsed_date and groups_lessons:
                        save_parsed_lessons(parsed_date, groups_lessons)
                except Exception as e:
                    logger.warning("Parse error: %s", e)
                if notify and bot:
                    if not had_schedule:
                        notify_new_schedule(bot, schedule_date, pdf_path)
                    else:
                        notify_updated_schedule(bot, schedule_date, pdf_path)
                processed += 1
            except Exception as e:
                logger.warning("Error processing attachment %s: %s", filename, e)
                raise
        return {
            "ok": True,
            "schedule_date": schedule_date.isoformat(),
            "processed": processed,
        }
    finally:
        try:
            imap.close()
            imap.logout()
        except Exception:
            pass


def convert_uploaded_word(word_bytes: bytes, original_filename: str, schedule_date: date) -> str:
    """Конвертировать загруженный Word-файл в PDF, сохранить в архив. Возвращает путь к PDF."""
    _ensure_dirs()
    base_name = os.path.splitext(os.path.basename(original_filename))[0]
    tmp_word_path = os.path.join(
        INCOMING_DIR, f"{base_name}_{int(datetime.utcnow().timestamp())}.docx"
    )
    try:
        with open(tmp_word_path, "wb") as f:
            f.write(word_bytes)
        pdf_name = f"Расписание_{schedule_date.isoformat()}.pdf"
        year_dir = os.path.join(ARCHIVE_DIR, str(schedule_date.year))
        month_dir = os.path.join(year_dir, f"{schedule_date.month:02d}")
        os.makedirs(month_dir, exist_ok=True)
        pdf_path = os.path.join(month_dir, pdf_name)
        logger.info("Converting uploaded %s -> %s", tmp_word_path, pdf_path)
        _convert_to_pdf(tmp_word_path, pdf_path)
        return pdf_path
    finally:
        try:
            if os.path.exists(tmp_word_path):
                os.remove(tmp_word_path)
        except Exception:
            pass


def _format_teacher_notification(schedule_date: date, teacher_name: str, groups_lessons: list) -> str:
    lines = [f"📅 {schedule_date.strftime('%d.%m.%Y')}", f"👤 {teacher_name}:"]
    for group_code, lessons in groups_lessons:
        lines.append(f"📋 {group_code}")
        for les in lessons:
            room = f" (каб. {les['room']})" if les.get("room") else ""
            lines.append(
                f"{les['num']}. {les['time_start']}-{les['time_end']}{room}\n"
                f"{les['discipline']}"
            )
    return "\n\n".join(lines)


def _notify_schedule_document(bot: Bot, schedule_date: date, pdf_path: str, caption: str) -> None:
    kind_base = "updated" if "ИЗМЕНЕНИЕ" in caption else "new"
    for item in get_subscribers_with_settings():
        chat_id = item["chat_id"]
        if not item.get("notifications_enabled", True):
            continue
        kind = f"{kind_base}:personal" if (item.get("teacher_name") or item.get("group_code")) else f"{kind_base}:pdf"
        if was_schedule_notification_sent(chat_id, schedule_date, kind):
            continue
        try:
            teacher_name = item.get("teacher_name")
            if teacher_name:
                result = get_lessons_by_teacher(schedule_date, teacher_name)
                if result:
                    bot.send_message(
                        chat_id=chat_id,
                        text=_format_teacher_notification(schedule_date, teacher_name, result),
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("Полный PDF", callback_data=f"schedule_{schedule_date.isoformat()}")
                        ]]),
                    )
                    mark_schedule_notification_sent(chat_id, schedule_date, kind)
                    continue

            group_code = item.get("group_code")
            if group_code:
                result = get_lessons_by_group(schedule_date, group_code)
                if result:
                    actual_group, lessons = result
                    reset_group_missing_count(chat_id)
                    lines = [f"📅 {schedule_date.strftime('%d.%m.%Y')}", f"📋 {actual_group}:"]
                    for les in lessons:
                        room = f" (каб. {les['room']})" if les.get("room") else ""
                        lines.append(
                            f"{les['num']}. {les['time_start']}-{les['time_end']}{room}\n"
                            f"{les['discipline']}\n"
                            f"{les['teacher']}"
                        )
                    bot.send_message(
                        chat_id=chat_id,
                        text="\n\n".join(lines),
                        reply_markup=InlineKeyboardMarkup([[
                            InlineKeyboardButton("Полный PDF", callback_data=f"schedule_{schedule_date.isoformat()}")
                        ]]),
                    )
                    mark_schedule_notification_sent(chat_id, schedule_date, kind)
                    continue

                missing_count = bump_group_missing_count(chat_id)
                if missing_count >= 2:
                    bot.send_message(
                        chat_id=chat_id,
                        text=(
                            f"Не нашел вашу группу {group_code} в новом расписании.\n"
                            "Возможно, группа переименована. Используйте /group, чтобы выбрать новую."
                        ),
                    )

            with open(pdf_path, "rb") as f:
                bot.send_document(
                    chat_id=chat_id,
                    document=f,
                    filename=f"Расписание_{schedule_date.isoformat()}.pdf",
                    caption=caption,
                )
            mark_schedule_notification_sent(chat_id, schedule_date, kind)
        except Exception as e:
            logger.warning("Notify error for chat %s: %s", chat_id, e)
            err_msg = str(e).lower()
            if "blocked" in err_msg or "deactivated" in err_msg or "kicked" in err_msg:
                remove_subscriber(chat_id)
                logger.info("Removed inactive subscriber %s", chat_id)


def notify_new_schedule(bot: Bot, schedule_date: date, pdf_path: str) -> None:
    caption = (
        f"📅 НОВОЕ РАСПИСАНИЕ!\n"
        f"Доступно расписание на {schedule_date.strftime('%d.%m.%Y')}"
    )
    _notify_schedule_document(bot, schedule_date, pdf_path, caption)


def notify_updated_schedule(bot: Bot, schedule_date: date, pdf_path: str) -> None:
    caption = (
        f"🔄 ИЗМЕНЕНИЕ В РАСПИСАНИИ!\n"
        f"Обновлено расписание на {schedule_date.strftime('%d.%m.%Y')}"
    )
    _notify_schedule_document(bot, schedule_date, pdf_path, caption)

