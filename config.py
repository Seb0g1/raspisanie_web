import os

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# ID чатов администраторов (через запятую). Только они могут /broadcast и /stats
_admin = os.getenv("ADMIN_CHAT_IDS", "")
ADMIN_CHAT_IDS = []
for x in _admin.split(","):
    x = x.strip()
    if x:
        try:
            ADMIN_CHAT_IDS.append(int(x))
        except ValueError:
            pass

# Имя (логин) Gmail-аккаунта, с которого приходят письма
IMAP_EMAIL = os.getenv("IMAP_EMAIL")
IMAP_PASSWORD = os.getenv("IMAP_PASSWORD")  # пароль приложения, а не обычный пароль

# IMAP-сервер для Gmail
IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# От кого ждать письма с расписанием
ALLOWED_SENDER = os.getenv("ALLOWED_SENDER")

# Папка для временных Word-файлов
INCOMING_DIR = "incoming"

# Папка для архива PDF-расписаний
ARCHIVE_DIR = "archive"

# Путь к SQLite-базе
DB_PATH = "data/bot.db"

# Папка для PDF расписаний преподавателей (по фамилии)
TEACHERS_DIR = os.path.join(os.path.dirname(DB_PATH), "teachers")

# Период проверки почты (в секундах). 60 = 1 минута.
MAIL_CHECK_INTERVAL = 60

# Канал, на который нужно подписаться для пользования ботом (без @). Бот должен быть админом канала.
CHANNEL_USERNAME = (os.getenv("CHANNEL_USERNAME") or "energy_temnikovo").strip().lstrip("@")

# Веб-панель. По умолчанию 5001 (порт 5000 часто занят). Для nginx на 80 задайте WEB_PORT=5001 и proxy_pass на 5001.
try:
    WEB_PORT = int(str(os.getenv("WEB_PORT", "5001")).strip())
except (ValueError, AttributeError):
    WEB_PORT = 5001
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "admin")
# Слушать на всех интерфейсах (для доступа по IP сервера)
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")

# Публичный URL веб-сервера (https://...) для инлайн-режима: PDF по ссылке отправляется в чат.
# Без этого инлайн будет показывать только кнопку «Открыть в боте».
PUBLIC_BASE_URL = (os.getenv("PUBLIC_BASE_URL") or "").strip().rstrip("/")
