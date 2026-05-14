import logging
import os
import re
import signal
from collections import OrderedDict
from datetime import datetime, timedelta, date, time as dtime
from time import monotonic
from typing import Optional

import pytz

MSK = pytz.timezone("Europe/Moscow")

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InlineQueryResultDocument,
    InputTextMessageContent,
)
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
    CallbackQueryHandler,
    MessageHandler,
    Filters,
    InlineQueryHandler,
)

from config import TELEGRAM_BOT_TOKEN, MAIL_CHECK_INTERVAL, ADMIN_CHAT_IDS, CHANNEL_USERNAME, TEACHERS_DIR, PUBLIC_BASE_URL
from storage import (
    init_db,
    add_subscriber,
    update_subscriber_activity,
    get_schedule,
    list_schedules,
    get_subscribers,
    get_subscriber_count,
    get_new_subscribers_count,
    get_active_count,
    save_feedback,
    add_teacher,
    find_teachers_by_name,
    get_available_dates_with_lessons,
    save_parsed_lessons,
    remove_subscriber,
    get_lessons_by_group,
    get_lessons_by_teacher,
    get_subscriber_settings,
    set_subscriber_group,
    set_notifications_enabled,
    get_latest_groups,
    mark_update_processed,
)
from mail_processor import process_mail


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

_RECENT_MESSAGES = OrderedDict()
_RECENT_MESSAGES_TTL = 120
_RECENT_MESSAGES_LIMIT = 1000
_LOCK_FH = None


def _today() -> date:
    return datetime.now(MSK).date()


def _is_duplicate_message(update: Update) -> bool:
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return False

    now = monotonic()
    while _RECENT_MESSAGES:
        _, seen_at = next(iter(_RECENT_MESSAGES.items()))
        if now - seen_at <= _RECENT_MESSAGES_TTL:
            break
        _RECENT_MESSAGES.popitem(last=False)

    key = (chat.id, message.message_id)
    if key in _RECENT_MESSAGES:
        logger.info("Skip duplicate message chat_id=%s message_id=%s", chat.id, message.message_id)
        return True
    if not mark_update_processed(chat.id, message.message_id):
        logger.info("Skip persisted duplicate message chat_id=%s message_id=%s", chat.id, message.message_id)
        return True

    _RECENT_MESSAGES[key] = now
    if len(_RECENT_MESSAGES) > _RECENT_MESSAGES_LIMIT:
        _RECENT_MESSAGES.popitem(last=False)
    return False


def _acquire_single_instance_lock() -> None:
    global _LOCK_FH
    if os.name == "nt":
        return
    import fcntl

    lock_path = os.getenv("BOT_LOCK_FILE", "/tmp/bot_rasp.lock")
    _LOCK_FH = open(lock_path, "w")
    try:
        fcntl.flock(_LOCK_FH, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError(f"Another bot instance is already running (lock: {lock_path})")
    _LOCK_FH.write(str(os.getpid()))
    _LOCK_FH.flush()


def _next_school_day(d: date) -> date:
    """Следующий учебный день (пн–пт). Пятница/суббота/воскресенье → понедельник."""
    w = d.weekday()  # 0=Пн, 4=Пт, 5=Сб, 6=Вс
    if w >= 4:  # Пт → +3, Сб → +2, Вс → +1
        return d + timedelta(days=7 - w)
    return d + timedelta(days=1)


def _schedule_date_keyboard() -> ReplyKeyboardMarkup:
    """Клавиатура: Сегодня, Завтра/Понедельник (учебные дни)."""
    today = _today()
    label_tomorrow = "Понедельник" if today.weekday() >= 4 else "Завтра"
    keyboard = [
        [KeyboardButton("📅 Сегодня"), KeyboardButton(f"🌅 {label_tomorrow}")],
        [KeyboardButton("💬 Задать вопрос")],
    ]
    keyboard.insert(1, [KeyboardButton("👥 Моя группа"), KeyboardButton("⚙️ Настройки")])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def _date_from_button(text: str) -> Optional[date]:
    """По тексту кнопки вернуть дату расписания (или None)."""
    if not text:
        return None
    text = text.strip()
    today = _today()
    if text == "📅 Сегодня" or text == "Сегодня":
        return today
    if text.startswith("🌅") or text in ("Завтра", "Понедельник"):
        return _next_school_day(today)
    return None


def _parse_inline_query_to_dates(query: str) -> list:
    """По тексту инлайн-запроса вернуть список (date, label)."""
    q = (query or "").strip().lower()
    today = _today()
    if not q or q in ("расписание", "расп", "р"):
        return [
            (today, "Сегодня"),
            (_next_school_day(today), "Завтра" if today.weekday() < 4 else "Понедельник"),
        ]
    if q in ("сегодня", "today", "на сегодня"):
        return [(today, "Сегодня")]
    if q in ("завтра", "tomorrow", "понедельник", "на завтра"):
        d = _next_school_day(today)
        return [(d, d.strftime("%d.%m.%Y"))]
    if q in ("вчера", "yesterday"):
        d = today - timedelta(days=1)
        return [(d, "Вчера")]
    # дд.мм или дд.мм.гггг
    m = re.match(r"^(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?$", q.replace(" ", ""))
    if m:
        day, month = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else today.year
        if year < 100:
            year += 2000
        try:
            d = date(year, month, day)
            return [(d, d.strftime("%d.%m.%Y"))]
        except ValueError:
            pass
    return []


def _is_admin(chat_id: int) -> bool:
    return chat_id in ADMIN_CHAT_IDS


def _is_channel_member(bot, user_id: int) -> bool:
    """Проверка подписки на канал. Бот должен быть админом канала."""
    if not CHANNEL_USERNAME:
        return True
    try:
        member = bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status not in ("left", "kicked")
    except Exception as e:
        logger.warning("Channel check failed for %s: %s", user_id, e)
        return True  # при ошибке (например бот не админ канала) пропускаем


def _send_subscribe_message(update: Update, context: CallbackContext) -> None:
    """Отправить сообщение «подпишитесь на канал» с кнопкой."""
    url = f"https://t.me/{CHANNEL_USERNAME}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔔 Подписаться на канал", url=url)],
    ])
    update.message.reply_text(
        "🔔 Чтобы пользоваться ботом, подпишитесь на канал СП ЦПСУ «Энергия».\n\n"
        "Нажмите кнопку ниже → подпишитесь → снова нажмите /start.",
        reply_markup=keyboard,
    )


def _require_channel(update: Update, context: CallbackContext) -> bool:
    """True — можно продолжать, False — отправили «подпишитесь» и выходим."""
    if _is_admin(update.effective_user.id):
        return True
    if not _is_channel_member(context.bot, update.effective_user.id):
        _send_subscribe_message(update, context)
        return False
    return True


def _safe_send(bot, chat_id: int, method: str, **kwargs) -> bool:
    """Send message/document, return True on success. Remove subscriber if blocked."""
    try:
        getattr(bot, method)(chat_id=chat_id, **kwargs)
        return True
    except Exception as e:
        err_msg = str(e).lower()
        if "blocked" in err_msg or "deactivated" in err_msg or "kicked" in err_msg:
            remove_subscriber(chat_id)
            logger.info("Removed inactive subscriber %s", chat_id)
        else:
            logger.warning("Send to %s failed: %s", chat_id, e)
        return False


def _format_lessons_text(group_code: str, lessons: list) -> str:
    """Format lessons list as readable text."""
    lines = [f"📋 {group_code}:"]
    for les in lessons:
        room_str = f" (каб. {les['room']})" if les.get("room") else ""
        lines.append(
            f"  {les['num']}. {les['time_start']}-{les['time_end']}{room_str}\n"
            f"     {les['discipline']}\n"
            f"     {les['teacher']}"
        )
    return "\n".join(lines)


def _format_group_options(limit: int = 24) -> str:
    groups = get_latest_groups()
    if not groups:
        return "Список групп пока недоступен: нужно загрузить и распарсить расписание."
    shown = ", ".join(groups[:limit])
    suffix = "" if len(groups) <= limit else f" и еще {len(groups) - limit}"
    return f"Доступные группы: {shown}{suffix}"


def _set_group_from_text(update: Update, context: CallbackContext, raw_group: str) -> None:
    group_query = (raw_group or "").strip().upper()
    if not group_query:
        update.message.reply_text("Напишите группу, например: 1И25Б")
        return

    groups = get_latest_groups()
    matched = None
    for group_code in groups:
        if group_code.upper() == group_query:
            matched = group_code
            break
    if matched is None:
        for group_code in groups:
            if group_query in group_code.upper():
                matched = group_code
                break
    if matched is None and groups:
        update.message.reply_text(
            f"Не нашел группу «{group_query}» в последнем расписании.\n\n{_format_group_options()}"
        )
        return

    set_subscriber_group(update.effective_chat.id, matched or group_query)
    context.user_data.pop("awaiting_group", None)
    update.message.reply_text(
        f"Группа сохранена: {matched or group_query}\nТеперь кнопки «Сегодня» и «Завтра» будут сначала показывать ваше расписание по группе.",
        reply_markup=_schedule_date_keyboard(),
    )


def _send_group_prompt(update: Update, context: CallbackContext) -> None:
    settings = get_subscriber_settings(update.effective_chat.id)
    current = settings.get("group_code") or "не выбрана"
    context.user_data["awaiting_group"] = True
    update.message.reply_text(
        f"Текущая группа: {current}\n\nНапишите новую группу одним сообщением, например: 1И25Б.\n\n{_format_group_options()}",
        reply_markup=_schedule_date_keyboard(),
    )


def _send_settings(update: Update, context: CallbackContext) -> None:
    settings = get_subscriber_settings(update.effective_chat.id)
    group_code = settings.get("group_code") or "не выбрана"
    notify = "включены" if settings.get("notifications_enabled", True) else "выключены"
    update.message.reply_text(
        "⚙️ Настройки\n\n"
        f"Группа: {group_code}\n"
        f"Уведомления: {notify}\n\n"
        "Команды:\n"
        "/group — сменить группу\n"
        "/notify_on — включить уведомления\n"
        "/notify_off — выключить уведомления",
        reply_markup=_schedule_date_keyboard(),
    )


def _send_user_schedule_for(update: Update, context: CallbackContext, target_date: date) -> None:
    settings = get_subscriber_settings(update.effective_chat.id)
    group_code = settings.get("group_code")
    if group_code:
        result = get_lessons_by_group(target_date, group_code)
        if result:
            actual_group, lessons = result
            header = f"📅 {target_date.strftime('%d.%m.%Y')}\n"
            update.message.reply_text(
                header + _format_lessons_text(actual_group, lessons),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("Полный PDF", callback_data=f"schedule_{target_date.isoformat()}")
                ]]),
            )
            return
        update.message.reply_text(
            f"Не нашел группу {group_code} в расписании на {target_date.strftime('%d.%m.%Y')}.\n"
            "Возможно, группа переименована. Нажмите «Моя группа» или используйте /group, чтобы сменить ее."
        )
    _send_schedule_for(update, context, target_date)


def _send_schedule_for(update: Update, context: CallbackContext, target_date: date) -> None:
    file_path = get_schedule(target_date)
    if not file_path:
        update.message.reply_text(
            f"📭 Расписание на {target_date.strftime('%d.%m.%Y')} пока не загружено."
        )
        return
    try:
        with open(file_path, "rb") as f:
            context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=f,
                filename=f"Расписание_{target_date.isoformat()}.pdf",
                caption=f"📅 Расписание на {target_date.strftime('%d.%m.%Y')}",
            )
    except FileNotFoundError:
        update.message.reply_text(
            "⚠️ Файл расписания не найден. Сообщите администратору: @seb0g"
        )


def start(update: Update, context: CallbackContext) -> None:
    if not update.message:
        return
    # Deep link: t.me/bot?start=schedule_YYYY-MM-DD — сразу отправить расписание на дату
    args = context.args or []
    if args and args[0].startswith("schedule_"):
        if not _require_channel(update, context):
            return
        try:
            date_str = args[0].replace("schedule_", "")
            target_date = date.fromisoformat(date_str)
            chat_id = update.effective_chat.id
            add_subscriber(chat_id)
            update_subscriber_activity(chat_id)
            file_path = get_schedule(target_date)
            if file_path and os.path.isfile(file_path):
                with open(file_path, "rb") as f:
                    context.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename=f"Расписание_{target_date.isoformat()}.pdf",
                        caption=f"📅 Расписание на {target_date.strftime('%d.%m.%Y')}",
                    )
            else:
                update.message.reply_text(
                    f"📭 Расписание на {target_date.strftime('%d.%m.%Y')} пока не загружено."
                )
            return
        except (ValueError, IndexError):
            pass
    if not _require_channel(update, context):
        return
    chat_id = update.effective_chat.id
    add_subscriber(chat_id)
    update_subscriber_activity(chat_id)

    reply_markup = _schedule_date_keyboard()

    channel_line = (
        "🔔 Подписка на канал @{channel} обязательна.\n\n"
    ).format(channel=CHANNEL_USERNAME) if CHANNEL_USERNAME else ""
    text = (
        "✨ Бот расписания СП ЦПСУ «ЭНЕРГИЯ»\n\n"
        + channel_line +
        "📅 Удобное расписание в одном месте\n"
        "🔔 Уведомления о новых расписаниях\n"
        "📄 Формат PDF — открыть на любом устройстве\n\n"
        "⚡ Команды:\n"
        "/today — на сегодня\n"
        "/tomorrow — на завтра\n"
        "/yesterday — на вчера\n"
        "/date дд.мм — на дату\n"
        "/list — архив расписаний\n"
        "/help — справка\n\n"
        "💬 Кнопка «Задать вопрос» — ответим в боте\n"
        "👤 Фамилия преподавателя — расписание по PDF (если загружено)\n\n"
        "⚡ В любом чате: @raspisaniecpsu_bot завтра — быстрое расписание\n\n"
        "by @Seb0g"
    )
    update.message.reply_text(text, reply_markup=reply_markup)
    share_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Поделиться ботом", switch_inline_query="расписание")],
    ])
    update.message.reply_text("Поделитесь ботом с однокурсниками:", reply_markup=share_markup)


def help_command(update: Update, context: CallbackContext) -> None:
    if not _require_channel(update, context):
        return
    update_subscriber_activity(update.effective_chat.id)
    text = (
        "📋 Команды:\n"
        "/today — расписание на сегодня\n"
        "/tomorrow — на завтра\n"
        "/yesterday — на вчера\n"
        "/date дд.мм — на дату\n"
        "/list — архив\n"
        "/help — эта справка\n"
        "/feedback текст — отзыв или предложение"
    )
    if _is_admin(update.effective_chat.id):
        text += "\n\n👑 Админ:\n/stats — аналитика\n/broadcast текст — рассылка\n📎 PDF с подписью (фамилия) — добавить расписание преподавателя"
    text += "\n\n👤 Фамилия преподавателя — расписание по PDF."
    update.message.reply_text(text)


def group_command(update: Update, context: CallbackContext) -> None:
    if not _require_channel(update, context):
        return
    add_subscriber(update.effective_chat.id)
    update_subscriber_activity(update.effective_chat.id)
    if context.args:
        _set_group_from_text(update, context, " ".join(context.args))
        return
    _send_group_prompt(update, context)


def settings_command(update: Update, context: CallbackContext) -> None:
    if not _require_channel(update, context):
        return
    add_subscriber(update.effective_chat.id)
    update_subscriber_activity(update.effective_chat.id)
    _send_settings(update, context)


def notify_on_command(update: Update, context: CallbackContext) -> None:
    if not _require_channel(update, context):
        return
    set_notifications_enabled(update.effective_chat.id, True)
    update.message.reply_text("Уведомления включены.", reply_markup=_schedule_date_keyboard())


def notify_off_command(update: Update, context: CallbackContext) -> None:
    if not _require_channel(update, context):
        return
    set_notifications_enabled(update.effective_chat.id, False)
    update.message.reply_text("Уведомления выключены. Расписание по кнопкам останется доступным.", reply_markup=_schedule_date_keyboard())


def today(update: Update, context: CallbackContext) -> None:
    if not _require_channel(update, context):
        return
    update_subscriber_activity(update.effective_chat.id)
    target = _today()
    _send_user_schedule_for(update, context, target)


def tomorrow(update: Update, context: CallbackContext) -> None:
    if not _require_channel(update, context):
        return
    update_subscriber_activity(update.effective_chat.id)
    target = _next_school_day(_today())
    _send_user_schedule_for(update, context, target)


def yesterday(update: Update, context: CallbackContext) -> None:
    if not _require_channel(update, context):
        return
    update_subscriber_activity(update.effective_chat.id)
    target = _today() - timedelta(days=1)
    _send_user_schedule_for(update, context, target)


def date_command(update: Update, context: CallbackContext) -> None:
    if not _require_channel(update, context):
        return
    update_subscriber_activity(update.effective_chat.id)
    if not context.args:
        update.message.reply_text("📅 Использование: /date дд.мм")
        return
    text = context.args[0]
    try:
        day, month = map(int, text.split("."))
        year = _today().year
        target = date(year, month, day)
    except Exception:
        update.message.reply_text("⚠️ Некорректная дата. Формат: /date дд.мм")
        return
    _send_user_schedule_for(update, context, target)


def list_command(update: Update, context: CallbackContext) -> None:
    if not _require_channel(update, context):
        return
    update_subscriber_activity(update.effective_chat.id)
    schedules = list_schedules()
    if not schedules:
        update.message.reply_text("📭 Архив расписаний пока пуст.")
        return
    last_10 = schedules[:10]
    buttons = []
    for d, _ in last_10:
        buttons.append([InlineKeyboardButton(
            f"📅 {d.strftime('%d.%m.%Y')}",
            callback_data=f"schedule_{d.isoformat()}",
        )])
    markup = InlineKeyboardMarkup(buttons)
    update.message.reply_text("📂 Доступные расписания (нажмите для получения PDF):", reply_markup=markup)


def list_callback_handler(update: Update, context: CallbackContext) -> None:
    """Handle inline button press from /list."""
    query = update.callback_query
    if not query or not query.data or not query.data.startswith("schedule_"):
        return
    query.answer()
    date_str = query.data.replace("schedule_", "")
    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        query.edit_message_text("⚠️ Некорректная дата.")
        return
    file_path = get_schedule(target_date)
    if not file_path:
        query.edit_message_text(f"📭 Расписание на {target_date.strftime('%d.%m.%Y')} не найдено.")
        return
    try:
        with open(file_path, "rb") as f:
            context.bot.send_document(
                chat_id=query.message.chat_id,
                document=f,
                filename=f"Расписание_{target_date.isoformat()}.pdf",
                caption=f"📅 Расписание на {target_date.strftime('%d.%m.%Y')}",
            )
    except FileNotFoundError:
        query.edit_message_text("⚠️ Файл расписания не найден.")


def stats_command(update: Update, context: CallbackContext) -> None:
    """Аналитика: количество подписчиков (только для админа)."""
    if not _is_admin(update.effective_chat.id):
        update.message.reply_text("🔒 Команда только для администратора.")
        return
    total = get_subscriber_count()
    new_7 = get_new_subscribers_count(7)
    active_7 = get_active_count(7)
    schedules_count = len(list_schedules())
    text = (
        "📊 Аналитика\n\n"
        f"👥 Подписчиков: {total}\n"
        f"🆕 Новых (7 дн.): {new_7}\n"
        f"✨ Активных (7 дн.): {active_7}\n"
        f"📅 Расписаний в архиве: {schedules_count}"
    )
    update.message.reply_text(text)


def broadcast_command(update: Update, context: CallbackContext) -> None:
    """Рассылка сообщения всем подписчикам (только для админа)."""
    if not _is_admin(update.effective_chat.id):
        update.message.reply_text("🔒 Команда только для администратора.")
        return
    if not context.args:
        update.message.reply_text(
            "📢 Использование: /broadcast ваш текст\n"
            "Пример: /broadcast Завтра занятия по расписанию."
        )
        return
    text = "📢 Рассылка от администрации:\n\n" + " ".join(context.args)
    subscribers = get_subscribers()
    if not subscribers:
        update.message.reply_text("📭 Нет подписчиков для рассылки.")
        return
    sent = 0
    failed = 0
    for chat_id in subscribers:
        if _safe_send(context.bot, chat_id, "send_message", text=text):
            sent += 1
        else:
            failed += 1
    update.message.reply_text(
        f"✅ Рассылка: доставлено {sent}, ошибок {failed}."
    )


def _notify_admins_new_feedback(bot, user_info: str, feedback_text: str) -> None:
    """Уведомить админов о новом обращении (в боте и на веб придут)."""
    msg = f"💬 Новое обращение\n{user_info}\n\n{feedback_text}"
    for admin_id in ADMIN_CHAT_IDS:
        try:
            bot.send_message(chat_id=admin_id, text=msg)
        except Exception as e:
            logger.warning("Feedback to admin %s failed: %s", admin_id, e)


def feedback_command(update: Update, context: CallbackContext) -> None:
    """Отправить отзыв/предложение администратору."""
    if not _require_channel(update, context):
        return
    if not context.args:
        update.message.reply_text(
            "✍️ Напишите отзыв после команды. Пример: /feedback Хотелось бы расписание на неделю."
        )
        return
    feedback_text = " ".join(context.args)
    user = update.effective_user
    user_info = f"id:{user.id} @{user.username or '—'} {user.first_name or ''} {user.last_name or ''}"
    save_feedback(update.effective_chat.id, user_info, feedback_text)
    _notify_admins_new_feedback(context.bot, user_info, feedback_text)
    update.message.reply_text("✅ Спасибо! Ваш отзыв отправлен.")


def checkmail_command(update: Update, context: CallbackContext) -> None:
    """
    Ручная проверка почты и обработка новых расписаний.
    Удобно для отладки: сразу виден результат в логах и по уведомлениям.
    """
    if not _is_admin(update.effective_chat.id):
        update.message.reply_text("🔒 Команда только для администратора.")
        return
    update.message.reply_text("📬 Запускаю проверку почты...")
    logger.info("Manual /checkmail triggered by chat %s", update.effective_chat.id)
    process_mail(context.bot)
    update.message.reply_text("✅ Проверка почты завершена.")


def text_buttons_handler(update: Update, context: CallbackContext) -> None:
    """
    Обработчик кнопок: дата (Сегодня/Завтра/Понедельник), Задать вопрос, текст (фамилия).
    """
    if not update.message:
        return
    if _is_duplicate_message(update):
        return
    if not _require_channel(update, context):
        return
    update_subscriber_activity(update.effective_chat.id)
    text = (update.message.text or "").strip()
    text_lower = text.lower()

    if context.user_data.get("awaiting_group"):
        _set_group_from_text(update, context, text)
        return

    if "моя группа" in text_lower:
        _send_group_prompt(update, context)
        return

    if "настройки" in text_lower:
        _send_settings(update, context)
        return

    # Пользователь в режиме «пишет вопрос» — сохраняем как обращение и уведомляем админов
    if context.user_data.get("awaiting_question"):
        context.user_data.pop("awaiting_question", None)
        if not text:
            update.message.reply_text("✍️ Напишите текст вопроса.")
            return
        user = update.effective_user
        user_info = f"id:{user.id} @{user.username or '—'} {user.first_name or ''} {user.last_name or ''}"
        save_feedback(update.effective_chat.id, user_info, text)
        _notify_admins_new_feedback(context.bot, user_info, text)
        update.message.reply_text("✅ Вопрос отправлен. Ответим здесь в боте.")
        return

    if "задать вопрос" in text_lower:
        context.user_data["awaiting_question"] = True
        update.message.reply_text("✍️ Напишите ваш вопрос — мы ответим вам здесь в боте.")
        return

    # Кнопки даты: Сегодня, Завтра, Понедельник, Послезавтра — полное расписание PDF
    target_date = _date_from_button(text)
    if target_date is not None:
        _send_user_schedule_for(update, context, target_date)
        return

    # Поиск по группе в распарсенном расписании (если текст похож на код группы)
    if re.match(r"^\d[А-Яа-яA-Za-z0-9\-]+$", text):
        today = _today()
        for check_date in [today, _next_school_day(today)]:
            result = get_lessons_by_group(check_date, text)
            if result:
                group_code, lessons = result
                header = f"📅 {check_date.strftime('%d.%m.%Y')}\n"
                update.message.reply_text(header + _format_lessons_text(group_code, lessons))
                return

    # Поиск по преподавателю в распарсенном расписании
    if len(text) >= 3 and text[0].isupper() and text.isalpha():
        today = _today()
        for check_date in [today, _next_school_day(today)]:
            result = get_lessons_by_teacher(check_date, text)
            if result:
                header = f"📅 {check_date.strftime('%d.%m.%Y')}\n"
                parts = [header]
                for group_code, lessons in result:
                    parts.append(_format_lessons_text(group_code, lessons))
                update.message.reply_text("\n\n".join(parts))
                return

    # Поиск по загруженным PDF преподавателей (ручная загрузка админом)
    teachers = find_teachers_by_name(text)
    if len(teachers) == 1:
        t = teachers[0]
        try:
            with open(t["file_path"], "rb") as f:
                caption = f"👤 {t['name']}"
                if t.get("group_abbr"):
                    caption += f" ({t['group_abbr']})"
                update.message.reply_document(
                    document=f,
                    filename=os.path.basename(t["file_path"]),
                    caption=caption,
                )
        except FileNotFoundError:
            update.message.reply_text("⚠️ Файл не найден. Обратитесь к администратору.")
    elif len(teachers) > 1:
        names = ", ".join(t["name"] for t in teachers)
        update.message.reply_text(
            f"👤 Найдено несколько: {names}. Уточните фамилию."
        )
    else:
        update.message.reply_text(
            "👤 Преподаватель не найден. Используйте кнопки 📅 Сегодня / 🌅 Завтра для полного расписания."
        )


def inline_query_handler(update: Update, context: CallbackContext) -> None:
    """Инлайн: @bot завтра → результат с кнопкой «Открыть в боте» для получения PDF.
    В BotFather нужно включить: Bot Settings → Inline Mode → Turn on."""
    inline_query = update.inline_query
    if not inline_query:
        return
    query = (inline_query.query or "").strip()
    logger.info("Inline query: %r", query)

    try:
        me = context.bot.get_me()
        bot_username = me.username if me else "raspisaniecpsu_bot"
    except Exception:
        bot_username = "raspisaniecpsu_bot"
    bot_link = f"https://t.me/{bot_username}"

    def fallback_result(msg: str = "Открыть бота"):
        return [InlineQueryResultArticle(
            id="fallback",
            title="📅 Расписание СП ЦПСУ «Энергия»",
            description=msg,
            input_message_content=InputTextMessageContent(
                message_text="📅 Расписание СП ЦПСУ «Энергия»"
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📄 Открыть в боте", url=bot_link),
            ]]),
        )]

    try:
        dates_with_labels = _parse_inline_query_to_dates(query)
    except Exception as e:
        logger.warning("Inline parse error: %s", e)
        context.bot.answer_inline_query(
            inline_query.id,
            fallback_result("Ошибка запроса. Попробуйте: сегодня, завтра"),
            cache_time=0,
            switch_pm_text="📅 Открыть бота",
            switch_pm_parameter="",
        )
        return

    if not dates_with_labels:
        context.bot.answer_inline_query(
            inline_query.id,
            [InlineQueryResultArticle(
                id="no_match",
                title="📅 Расписание",
                description="Напишите: сегодня, завтра или дд.мм",
                input_message_content=InputTextMessageContent(
                    message_text="📅 Расписание СП ЦПСУ «Энергия»"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📄 Открыть в боте", url=bot_link),
                ]]),
            )],
            cache_time=120,
            switch_pm_text="📅 Открыть бота",
            switch_pm_parameter="",
        )
        return

    results = []
    pdf_base = (PUBLIC_BASE_URL or "").strip()
    use_document_url = pdf_base.startswith("https://")
    if not use_document_url:
        logger.info("Inline: PUBLIC_BASE_URL не задан или не https — в чат уйдёт кнопка, не PDF")
    for i, (target_date, label) in enumerate(dates_with_labels):
        date_str = target_date.strftime("%d.%m.%Y")
        iso = target_date.isoformat()
        try:
            has_file = get_schedule(target_date) is not None
        except Exception:
            has_file = False
        if use_document_url and has_file:
            document_url = f"{pdf_base}/schedule/{iso}.pdf"
            logger.info("Inline: отправка PDF в чат для %s → %s", date_str, document_url)
            results.append(InlineQueryResultDocument(
                id=f"doc_{iso}_{i}",
                title=f"📅 Расписание на {date_str}",
                document_url=document_url,
                mime_type="application/pdf",
                description="PDF отправится в чат",
            ))
        else:
            if use_document_url and not has_file:
                logger.info("Inline: на %s расписания нет в архиве — показываем кнопку", date_str)
            desc = "📄 Получить PDF в боте" if has_file else "📭 Пока не загружено"
            start_param = f"schedule_{iso}"
            results.append(InlineQueryResultArticle(
                id=f"sch_{iso}_{i}",
                title=f"📅 Расписание на {date_str}",
                description=desc,
                input_message_content=InputTextMessageContent(
                    message_text=f"📅 Расписание на {date_str}"
                ),
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("📄 Открыть в боте", url=f"{bot_link}?start={start_param}"),
                ]]),
            ))
    try:
        context.bot.answer_inline_query(
            inline_query.id,
            results,
            cache_time=120,
            switch_pm_text="📅 Открыть бота",
            switch_pm_parameter="",
        )
    except Exception as e:
        err_text = str(e).lower()
        logger.warning("answer_inline_query failed: %s", e)
        if "url" in err_text or "document" in err_text or "http" in err_text:
            logger.info("Возможно Telegram не смог забрать PDF по ссылке. Проверьте: %s/schedule/YYYY-MM-DD.pdf", pdf_base or "PUBLIC_BASE_URL")
        try:
            context.bot.answer_inline_query(
                inline_query.id,
                fallback_result("Нажмите, чтобы открыть бота"),
                cache_time=0,
            )
        except Exception:
            pass


def _slug(name: str) -> str:
    """Безопасное имя файла из фамилии."""
    s = re.sub(r"[^\w\s-]", "", name.strip(), flags=re.UNICODE)
    s = re.sub(r"[-\s]+", "_", s)
    return s[:50] or "teacher"


def document_handler(update: Update, context: CallbackContext) -> None:
    """Админ отправляет PDF с подписью (фамилия преподавателя) — добавляем в базу."""
    if not update.message or not update.message.document:
        return
    if not _is_admin(update.effective_chat.id):
        return
    doc = update.message.document
    filename = doc.file_name or ""
    if not filename.lower().endswith(".pdf"):
        update.message.reply_text("📎 Отправьте файл PDF.")
        return
    name = (update.message.caption or "").strip()
    if not name:
        update.message.reply_text(
            "📎 Добавьте подпись к файлу — фамилию преподавателя (и при необходимости группу, например: Иванова ИС-21)."
        )
        return
    try:
        os.makedirs(TEACHERS_DIR, exist_ok=True)
        file_id = doc.file_id
        tg_file = context.bot.get_file(file_id)
        safe_name = _slug(name) + "_" + str(int(datetime.utcnow().timestamp())) + ".pdf"
        local_path = os.path.join(TEACHERS_DIR, safe_name)
        tg_file.download(local_path)
        group_abbr = None
        if " " in name:
            parts = name.split(None, 1)
            if len(parts) == 2 and re.search(r"[\d\-]", parts[1]):
                group_abbr = parts[1].strip()
                name = parts[0].strip()
        add_teacher(name, local_path, group_abbr)
        update.message.reply_text(f"✅ Добавлен преподаватель: {name}" + (f" ({group_abbr})" if group_abbr else ""))
    except Exception as e:
        logger.exception("Add teacher failed")
        update.message.reply_text(f"Ошибка: {e}")


def ensure_schedules_parsed() -> None:
    """Парсит все сохранённые PDF расписаний, по которым ещё нет данных по группам/преподам."""
    from schedule_parser import parse_schedule_pdf
    from storage import get_available_dates_with_lessons
    schedules = list_schedules()
    parsed_dates = set(get_available_dates_with_lessons())
    for schedule_date, file_path in schedules:
        if schedule_date in parsed_dates:
            continue
        if not os.path.isfile(file_path):
            continue
        try:
            parsed_date, groups_lessons = parse_schedule_pdf(file_path)
            if parsed_date and groups_lessons:
                save_parsed_lessons(parsed_date, groups_lessons)
                logger.info("Parsed schedule for %s: %s groups", parsed_date, len(groups_lessons))
        except Exception as e:
            logger.warning("Parse %s failed: %s", file_path, e)


def check_mail_job(context: CallbackContext) -> None:
    """Проверка почты — без ограничений по времени, чтобы расписание приходило сразу."""
    logger.info("Checking mail for new schedules...")
    process_mail(context.bot)


def tomorrow_notify_job(context: CallbackContext) -> None:
    """Ежедневная проверка в 18:00: если расписание на завтра есть — напомнить подписчикам."""
    today = _today()
    tomorrow = _next_school_day(today)
    if tomorrow == today:
        return
    file_path = get_schedule(tomorrow)
    if not file_path:
        return
    text = f"🔔 Напоминание: расписание на {tomorrow.strftime('%d.%m.%Y')} уже доступно!\nИспользуйте кнопку 🌅 или /tomorrow"
    subscribers = get_subscribers()
    for chat_id in subscribers:
        _safe_send(context.bot, chat_id, "send_message", text=text)


def error_handler(update: object, context: CallbackContext) -> None:
    """Глобальный обработчик ошибок — ловит Unauthorized (бот заблокирован) и прочее."""
    err = context.error
    if err is None:
        return
    err_msg = str(err).lower()
    if "blocked" in err_msg or "deactivated" in err_msg or "kicked" in err_msg:
        chat_id = None
        if update and hasattr(update, "effective_chat") and update.effective_chat:
            chat_id = update.effective_chat.id
        if chat_id:
            remove_subscriber(chat_id)
            logger.info("Removed blocked subscriber %s", chat_id)
        return
    logger.error("Unhandled error: %s", err, exc_info=context.error)


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set. Fill it in .env before starting the bot.")

    _acquire_single_instance_lock()
    init_db()
    ensure_schedules_parsed()

    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_error_handler(error_handler)

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("group", group_command))
    dp.add_handler(CommandHandler("settings", settings_command))
    dp.add_handler(CommandHandler("notify_on", notify_on_command))
    dp.add_handler(CommandHandler("notify_off", notify_off_command))
    dp.add_handler(CommandHandler("today", today))
    dp.add_handler(CommandHandler("tomorrow", tomorrow))
    dp.add_handler(CommandHandler("yesterday", yesterday))
    dp.add_handler(CommandHandler("date", date_command))
    dp.add_handler(CommandHandler("list", list_command))
    dp.add_handler(CommandHandler("stats", stats_command))
    dp.add_handler(CommandHandler("broadcast", broadcast_command))
    dp.add_handler(CommandHandler("feedback", feedback_command))
    dp.add_handler(CommandHandler("checkmail", checkmail_command))
    dp.add_handler(CallbackQueryHandler(list_callback_handler, pattern=r"^schedule_"))
    dp.add_handler(MessageHandler(Filters.document, document_handler))
    dp.add_handler(InlineQueryHandler(inline_query_handler))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, text_buttons_handler))

    # Периодическая проверка почты
    job_queue = updater.job_queue
    job_queue.run_repeating(check_mail_job, interval=MAIL_CHECK_INTERVAL, first=10)

    # Ежедневное уведомление «расписание на завтра» в 18:00 МСК (15:00 UTC)
    job_queue.run_daily(tomorrow_notify_job, time=dtime(hour=18, minute=0, tzinfo=MSK))

    # Graceful shutdown
    def _shutdown(signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        updater.stop()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    updater.start_polling()
    logger.info("Bot started.")
    updater.idle()


if __name__ == "__main__":
    import sys
    import traceback
    print("Запуск бота...")
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        sys.exit(1)
