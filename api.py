# -*- coding: utf-8 -*-
"""
REST API для веб-панели бота (Vue.js).
Защита: сессия, лимит попыток входа, заголовки безопасности.
"""
import logging
import os
import tempfile
import time
from collections import defaultdict

from datetime import date as date_type, datetime
from flask import Flask, request, session, jsonify, send_from_directory, send_file
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)
_start_time = time.time()

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from config import (
    TELEGRAM_BOT_TOKEN,
    WEB_PORT,
    WEB_PASSWORD,
    WEB_HOST,
    PUBLIC_BASE_URL,
    ARCHIVE_DIR,
)
from storage import (
    init_db,
    get_schedule,
    save_schedule,
    save_parsed_lessons,
    get_subscriber_count,
    get_new_subscribers_count,
    get_active_count,
    list_schedules,
    get_subscribers,
    get_feedback_list,
    set_feedback_replied,
    list_mail_events,
    list_subscribers,
    get_group_stats,
    cleanup_technical_data,
    remove_subscriber,
)
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

app = Flask(__name__, static_folder="webapp/dist", static_url_path="")
_secret = os.getenv("WEB_SECRET_KEY")
if not _secret:
    logger.warning("WEB_SECRET_KEY не задан — используется WEB_PASSWORD как secret_key. Задайте WEB_SECRET_KEY для безопасности.")
app.secret_key = _secret or WEB_PASSWORD or "change-me-in-production"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("WEB_HTTPS", "").lower() in ("1", "true", "yes")
app.config["PERMANENT_SESSION_LIFETIME"] = 3600 * 12  # 12 часов

# Лимит входа: 5 попыток в минуту с одного IP
_login_attempts = defaultdict(list)
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 5

bot = Bot(TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None


def _rate_limit_login():
    ip = request.remote_addr or "unknown"
    now = time.time()
    _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < RATE_LIMIT_WINDOW]
    if len(_login_attempts[ip]) >= RATE_LIMIT_MAX:
        return True
    _login_attempts[ip].append(now)
    return False


def login_required(f):
    from functools import wraps
    @wraps(f)
    def inner(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return inner


# --- API ---

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    password = data.get("password", "").strip()
    if _rate_limit_login():
        return jsonify({"error": "Слишком много попыток. Подождите минуту."}), 429
    if password != WEB_PASSWORD:
        return jsonify({"error": "Неверный пароль"}), 401
    session.permanent = True
    session["logged_in"] = True
    return jsonify({"ok": True})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.pop("logged_in", None)
    return jsonify({"ok": True})


@app.route("/api/me")
def api_me():
    if not session.get("logged_in"):
        return jsonify({"logged_in": False}), 200
    return jsonify({"logged_in": True}), 200


@app.route("/schedule/<date_str>.pdf", methods=["GET"])
def schedule_pdf(date_str: str):
    """Публичная раздача PDF расписания по дате (для инлайн-режима: PDF сразу в чат)."""
    if len(date_str) != 10 or date_str.count("-") != 2:
        return "", 404
    try:
        target_date = date_type.fromisoformat(date_str)
    except ValueError:
        return "", 404
    file_path = get_schedule(target_date)
    if not file_path:
        return "", 404
    if not os.path.isabs(file_path):
        file_path = os.path.abspath(os.path.join(os.getcwd(), file_path))
    if not os.path.isfile(file_path):
        return "", 404
    return send_file(
        file_path,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"Расписание_{date_str}.pdf",
        conditional=True,
    )


@app.route("/api/stats")
@login_required
def api_stats():
    total = get_subscriber_count()
    new_7 = get_new_subscribers_count(7)
    active_7 = get_active_count(7)
    schedules = list_schedules()
    return jsonify({
        "total": total,
        "new_7": new_7,
        "active_7": active_7,
        "schedules_count": len(schedules),
    })


@app.route("/api/users")
@login_required
def api_users():
    try:
        limit = int(request.args.get("limit", "500"))
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        limit = 500
        offset = 0
    group_code = (request.args.get("group") or "").strip() or None
    return jsonify({
        "items": list_subscribers(limit=limit, offset=offset, group_code=group_code),
        "group_stats": get_group_stats(),
    })


def _send_broadcast_to_chat(chat_id: int, text: str, photo_paths: list) -> bool:
    """Отправить пост (текст и/или фото) в один чат. Возвращает True при успехе."""
    try:
        if not photo_paths:
            bot.send_message(chat_id=chat_id, text=text)
            return True
        if len(photo_paths) == 1:
            with open(photo_paths[0], "rb") as f:
                bot.send_photo(chat_id=chat_id, photo=f, caption=text or None)
            return True
        from telegram import InputMediaPhoto
        media = []
        for i, path in enumerate(photo_paths):
            with open(path, "rb") as f:
                media.append(InputMediaPhoto(media=f.read(), caption=text if i == 0 else None))
        bot.send_media_group(chat_id=chat_id, media=media)
        return True
    except TelegramError:
        return False


@app.route("/api/broadcast", methods=["POST"])
@login_required
def api_broadcast():
    if not bot:
        return jsonify({"error": "Бот не настроен"}), 500

    text = ""
    photo_paths = []
    tmpdir = None

    if request.content_type and "multipart/form-data" in request.content_type:
        text = (request.form.get("message") or "").strip()
        files = request.files.getlist("photos")
        if not files:
            files = [request.files.get("photo")] if request.files.get("photo") else []
        tmpdir = tempfile.mkdtemp()
        try:
            for f in files:
                if not f or not f.filename:
                    continue
                ext = os.path.splitext(f.filename)[1] or ".jpg"
                path = os.path.join(tmpdir, f"img_{len(photo_paths)}{ext}")
                f.save(path)
                photo_paths.append(path)
        except Exception as e:
            for p in photo_paths:
                try:
                    os.remove(p)
                except OSError:
                    pass
            if tmpdir:
                try:
                    os.rmdir(tmpdir)
                except OSError:
                    pass
            return jsonify({"error": str(e)}), 400
    else:
        data = request.get_json() or {}
        text = (data.get("message") or "").strip()

    if not text and not photo_paths:
        return jsonify({"error": "Введите текст и/или приложите фото"}), 400

    subscribers = get_subscribers()
    sent, failed = 0, 0
    for chat_id in subscribers:
        if _send_broadcast_to_chat(chat_id, text, photo_paths):
            sent += 1
        else:
            failed += 1

    if tmpdir:
        for p in photo_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass

    return jsonify({"sent": sent, "failed": failed})


@app.route("/api/feedback")
@login_required
def api_feedback():
    items = get_feedback_list()
    return jsonify({"items": items})


@app.route("/api/feedback/<int:fid>/reply", methods=["POST"])
@login_required
def api_feedback_reply(fid):
    data = request.get_json() or {}
    reply = (data.get("reply") or "").strip()
    if not reply:
        return jsonify({"error": "Введите текст ответа"}), 400
    if not bot:
        return jsonify({"error": "Бот не настроен"}), 500
    items = get_feedback_list()
    item = next((x for x in items if x["id"] == fid), None)
    if not item:
        return jsonify({"error": "Обращение не найдено"}), 404
    try:
        bot.send_message(chat_id=item["chat_id"], text=reply)
        set_feedback_replied(fid, reply)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/schedules")
@login_required
def api_schedules():
    """Список всех расписаний в архиве."""
    schedules = list_schedules()
    return jsonify({
        "items": [
            {"date": d.isoformat(), "date_formatted": d.strftime("%d.%m.%Y"), "file_path": fp}
            for d, fp in schedules
        ]
    })


@app.route("/api/checkmail", methods=["POST"])
@login_required
def api_checkmail():
    if not bot:
        return jsonify({"error": "Бот не настроен"}), 500
    try:
        from mail_processor import process_mail
        process_mail(bot)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mail/scan")
@login_required
def api_mail_scan():
    """Сканировать почту и вернуть список писем (без обработки)."""
    try:
        from mail_processor import scan_mailbox
        emails = scan_mailbox()
        return jsonify({"items": emails})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mail/process", methods=["POST"])
@login_required
def api_mail_process():
    """Обработать конкретное письмо: конвертировать Word→PDF и сохранить."""
    data = request.get_json() or {}
    msg_id = (data.get("msg_id") or "").strip()
    if not msg_id:
        return jsonify({"error": "Укажите msg_id"}), 400
    notify = data.get("notify", False)
    try:
        from mail_processor import process_single_mail
        result = process_single_mail(msg_id, bot=bot, notify=notify)
        if "error" in result:
            return jsonify(result), 500
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/mail/events")
@login_required
def api_mail_events():
    try:
        limit = int(request.args.get("limit", "50"))
    except ValueError:
        limit = 50
    return jsonify({"items": list_mail_events(limit)})


@app.route("/api/maintenance/cleanup", methods=["POST"])
@login_required
def api_maintenance_cleanup():
    data = request.get_json(silent=True) or {}
    try:
        days = int(data.get("days", 90))
    except (TypeError, ValueError):
        days = 90
    return jsonify({"ok": True, **cleanup_technical_data(days)})


@app.route("/api/upload-schedule", methods=["POST"])
@login_required
def api_upload_schedule():
    """Ручная загрузка расписания: PDF или Word файл + дата.
    Word автоматически конвертируется в PDF.
    Опционально: notify=true — разослать уведомление подписчикам."""
    date_str = (request.form.get("date") or "").strip()
    if not date_str:
        return jsonify({"error": "Укажите дату"}), 400

    schedule_date = None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            schedule_date = datetime.strptime(date_str, fmt).date()
            break
        except ValueError:
            continue
    if not schedule_date:
        return jsonify({"error": "Некорректная дата. Формат: ДД.ММ.ГГГГ или YYYY-MM-DD"}), 400

    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "Приложите файл (PDF или Word)"}), 400

    filename_lower = f.filename.lower()
    is_word = filename_lower.endswith((".doc", ".docx"))
    is_pdf = filename_lower.endswith(".pdf")

    if not is_word and not is_pdf:
        return jsonify({"error": "Допустимы файлы PDF, DOC или DOCX"}), 400

    if is_word:
        # Конвертация Word → PDF
        try:
            from mail_processor import convert_uploaded_word
            word_bytes = f.read()
            pdf_path = convert_uploaded_word(word_bytes, f.filename, schedule_date)
        except Exception as e:
            return jsonify({"error": f"Ошибка конвертации Word→PDF: {e}"}), 500
    else:
        # PDF — сохраняем напрямую
        year_dir = os.path.join(ARCHIVE_DIR, str(schedule_date.year))
        month_dir = os.path.join(year_dir, f"{schedule_date.month:02d}")
        os.makedirs(month_dir, exist_ok=True)
        pdf_name = f"Расписание_{schedule_date.isoformat()}.pdf"
        pdf_path = os.path.join(month_dir, pdf_name)
        f.save(pdf_path)

    # Сохраняем в БД
    had_schedule = get_schedule(schedule_date) is not None
    save_schedule(schedule_date, pdf_path, datetime.utcnow())

    # Парсим для поиска по группам/преподавателям
    parsed_groups = 0
    try:
        from schedule_parser import parse_schedule_pdf
        parsed_date, groups_lessons = parse_schedule_pdf(pdf_path)
        if parsed_date and groups_lessons:
            save_parsed_lessons(parsed_date, groups_lessons)
            parsed_groups = len(groups_lessons)
    except Exception as e:
        logger.warning("Parse uploaded schedule error: %s", e)

    # Уведомление подписчиков
    notify = (request.form.get("notify") or "").strip().lower() in ("1", "true", "yes", "on")
    notified = 0
    if notify and bot:
        from mail_processor import notify_new_schedule
        notify_new_schedule(bot, schedule_date, pdf_path)
        notified = len(get_subscribers())

    return jsonify({
        "ok": True,
        "date": schedule_date.isoformat(),
        "converted_from_word": is_word,
        "new": not had_schedule,
        "parsed_groups": parsed_groups,
        "notified": notified,
    })


def _send_ad_to_chat(chat_id: int, text: str, photo_path, button_text, button_url) -> tuple:
    """Отправить рекламный пост (HTML) в один чат. Возвращает (success, error_str)."""
    try:
        reply_markup = None
        if button_text and button_url:
            reply_markup = InlineKeyboardMarkup(
                [[InlineKeyboardButton(text=button_text, url=button_url)]]
            )

        if photo_path:
            with open(photo_path, "rb") as f:
                bot.send_photo(
                    chat_id=chat_id,
                    photo=f,
                    caption=text or None,
                    parse_mode="HTML",
                    reply_markup=reply_markup,
                )
        else:
            bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
        return True, ""
    except TelegramError as e:
        return False, str(e).lower()


@app.route("/api/ads/send", methods=["POST"])
@login_required
def api_ads_send():
    """Рассылка рекламного поста с HTML-разметкой, фото и кнопкой."""
    if not bot:
        return jsonify({"error": "Бот не настроен"}), 500

    message = (request.form.get("message") or "").strip()
    button_text = (request.form.get("button_text") or "").strip() or None
    button_url = (request.form.get("button_url") or "").strip() or None

    photo_path = None
    tmpdir = None
    photo_file = request.files.get("photo")

    if photo_file and photo_file.filename:
        tmpdir = tempfile.mkdtemp()
        ext = os.path.splitext(photo_file.filename)[1] or ".jpg"
        photo_path = os.path.join(tmpdir, f"ad_banner{ext}")
        photo_file.save(photo_path)

    if not message and not photo_path:
        return jsonify({"error": "Введите текст и/или приложите изображение"}), 400

    # Telegram: caption max 1024 chars when photo is attached
    if photo_path and message and len(message) > 1024:
        if tmpdir:
            try:
                os.remove(photo_path)
                os.rmdir(tmpdir)
            except OSError:
                pass
        return jsonify({"error": "Текст с фото не должен превышать 1024 символа (сейчас: {})".format(len(message))}), 400

    subscribers = get_subscribers()
    sent, failed = 0, 0
    for chat_id in subscribers:
        ok, err_msg = _send_ad_to_chat(chat_id, message, photo_path, button_text, button_url)
        if ok:
            sent += 1
        else:
            failed += 1
            if "blocked" in err_msg or "deactivated" in err_msg or "kicked" in err_msg:
                remove_subscriber(chat_id)
                logger.info("Removed inactive subscriber %s", chat_id)

    if tmpdir:
        try:
            if photo_path:
                os.remove(photo_path)
            os.rmdir(tmpdir)
        except OSError:
            pass

    return jsonify({"sent": sent, "failed": failed})


# --- Заголовки безопасности ---

@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-XSS-Protection"] = "1; mode=block"
    resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return resp


# --- SPA: отдаём index.html для всех не-API путей ---

@app.route("/favicon.ico")
def favicon():
    return "", 204


def _dist_path():
    return os.path.join(app.root_path, "webapp", "dist")


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_spa(path):
    dist = _dist_path()
    if not os.path.isdir(dist):
        return jsonify({"error": "Frontend not built. Run: cd webapp && npm install && npm run build"}), 503
    if path:
        full = os.path.join(dist, path)
        if os.path.isfile(full):
            return send_from_directory(dist, path)
    return send_from_directory(dist, "index.html")


@app.route("/health")
def health_check():
    uptime = time.time() - _start_time
    return jsonify({"status": "ok", "uptime": round(uptime, 1)})


def main():
    init_db()
    if WEB_PORT == 80:
        logger.info("Панель: http://%s", WEB_HOST)
    else:
        logger.info("Панель: http://%s:%s", WEB_HOST, WEB_PORT)
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    import sys
    import traceback
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)
