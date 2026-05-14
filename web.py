# -*- coding: utf-8 -*-
"""
Веб-панель управления ботом.
Запуск: python web.py
Доступ: http://IP_СЕРВЕРА:PORT (например http://81.17.154.153:5000)
"""
import os
from datetime import datetime

from flask import (
    Flask,
    redirect,
    render_template_string,
    request,
    session,
    url_for,
    flash,
)

# Загружаем .env если есть
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
)
from storage import (
    init_db,
    get_subscriber_count,
    get_new_subscribers_count,
    get_active_count,
    list_schedules,
    get_subscribers,
    get_feedback_list,
    set_feedback_replied,
)
from telegram import Bot

app = Flask(__name__)
app.secret_key = os.getenv("WEB_SECRET_KEY", WEB_PASSWORD or "change-me-in-production")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

bot = Bot(TELEGRAM_BOT_TOKEN) if TELEGRAM_BOT_TOKEN else None


def login_required(f):
    from functools import wraps
    @wraps(f)
    def inner(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return inner


BASE_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Панель бота{% endblock %}</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #1a1a2e; color: #eee; min-height: 100vh; }
        a { color: #7eb8da; text-decoration: none; }
        a:hover { text-decoration: underline; }
        .nav { margin-bottom: 24px; }
        .nav a { margin-right: 16px; }
        h1 { color: #e94560; margin-top: 0; }
        .card { background: #16213e; border-radius: 12px; padding: 20px; margin-bottom: 20px; max-width: 800px; }
        input[type="text"], input[type="password"], textarea { width: 100%; padding: 10px; border-radius: 8px; border: 1px solid #0f3460; background: #0f3460; color: #eee; margin: 8px 0; }
        button, .btn { display: inline-block; padding: 10px 20px; background: #e94560; color: #fff; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
        button:hover, .btn:hover { background: #c73e54; }
        .stats { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 16px; margin: 20px 0; }
        .stat { background: #0f3460; padding: 16px; border-radius: 8px; text-align: center; }
        .stat .n { font-size: 28px; font-weight: bold; color: #e94560; }
        .stat .l { font-size: 12px; color: #888; margin-top: 4px; }
        .feedback-item { border-bottom: 1px solid #0f3460; padding: 12px 0; }
        .feedback-item:last-child { border-bottom: none; }
        .feedback-meta { font-size: 12px; color: #888; margin-bottom: 6px; }
        .reply-form { margin-top: 10px; }
        .flash { padding: 12px; border-radius: 8px; margin-bottom: 16px; }
        .flash.success { background: #0d5c2e; }
        .flash.error { background: #8b2635; }
        .logout { float: right; }
    </style>
</head>
<body>
    {% if session.get('logged_in') %}
    <div class="nav">
        <a href="{{ url_for('dashboard') }}">Главная</a>
        <a href="{{ url_for('broadcast_page') }}">Рассылка</a>
        <a href="{{ url_for('feedback_page') }}">Обратная связь</a>
        <a href="{{ url_for('logout') }}" class="logout">Выход</a>
    </div>
    {% endif %}
    {% with messages = get_flashed_messages(with_categories=true) %}
        {% if messages %}
            {% for category, msg in messages %}
            <div class="flash {{ category }}">{{ msg }}</div>
            {% endfor %}
        {% endif %}
    {% endwith %}
    {% block content %}{% endblock %}
</body>
</html>
"""


@app.route("/", methods=["GET", "POST"])
def index():
    """Главная: форма входа или дашборд."""
    if request.method == "POST" and request.form.get("password") is not None:
        if request.form.get("password") == WEB_PASSWORD:
            session["logged_in"] = True
            return redirect(url_for("index"))
        flash("Неверный пароль.", "error")
    if not session.get("logged_in"):
        return render_template_string(
            BASE_HTML + """
            <div class="card">
                <h1>Вход в панель бота</h1>
                <form method="post" action="{{ url_for('index') }}">
                    <label>Пароль</label>
                    <input type="password" name="password" required autofocus>
                    <button type="submit">Войти</button>
                </form>
            </div>
            """,
            title="Вход",
        )
    total = get_subscriber_count()
    new_7 = get_new_subscribers_count(7)
    active_7 = get_active_count(7)
    schedules = list_schedules()
    return render_template_string(
        BASE_HTML + """
        <h1>Панель управления ботом</h1>
        <div class="card">
            <h2>Аналитика</h2>
            <div class="stats">
                <div class="stat"><span class="n">{{ total }}</span><div class="l">Подписчиков</div></div>
                <div class="stat"><span class="n">{{ new_7 }}</span><div class="l">Новых за 7 дней</div></div>
                <div class="stat"><span class="n">{{ active_7 }}</span><div class="l">Активных за 7 дней</div></div>
                <div class="stat"><span class="n">{{ schedules_count }}</span><div class="l">Расписаний в архиве</div></div>
            </div>
        </div>
        <div class="card">
            <p>Рассылка — без подписи «от администрации», сообщение уходит как есть.</p>
            <p>Ответы на обратную связь — пользователь получает только ваш текст, без подписи.</p>
            <form method="post" action="{{ url_for('checkmail') }}" style="margin-top:12px">
                <button type="submit">Проверить почту (расписания)</button>
            </form>
        </div>
        """,
        title="Главная",
        total=total,
        new_7=new_7,
        active_7=active_7,
        schedules_count=len(schedules),
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    """Редирект на главную для совместимости."""
    return redirect(url_for("index"))


@app.route("/logout")
def logout():
    session.pop("logged_in", None)
    return redirect(url_for("index"))


@app.route("/dashboard")
@login_required
def dashboard():
    """Главная (дашборд) — редирект на /."""
    return redirect(url_for("index"))


@app.route("/broadcast", methods=["GET", "POST"])
@login_required
def broadcast_page():
    if request.method == "POST":
        text = (request.form.get("message") or "").strip()
        if not text:
            flash("Введите текст сообщения.", "error")
            return redirect(url_for("broadcast_page"))
        if not bot:
            flash("Бот не настроен (нет токена).", "error")
            return redirect(url_for("broadcast_page"))
        subscribers = get_subscribers()
        sent, failed = 0, 0
        for chat_id in subscribers:
            try:
                bot.send_message(chat_id=chat_id, text=text)
                sent += 1
            except Exception:
                failed += 1
        flash(f"Разослано: {sent}, ошибок: {failed}.", "success")
        return redirect(url_for("broadcast_page"))
    return render_template_string(
        BASE_HTML + """
        <h1>Рассылка</h1>
        <div class="card">
            <p>Сообщение уйдёт всем подписчикам <strong>без подписи</strong> — только ваш текст.</p>
            <form method="post">
                <label>Текст сообщения</label>
                <textarea name="message" rows="5" required placeholder="Введите текст..."></textarea>
                <button type="submit">Отправить всем</button>
            </form>
        </div>
        """,
        title="Рассылка",
    )


@app.route("/feedback", methods=["GET"])
@login_required
def feedback_page():
    items = get_feedback_list()
    return render_template_string(
        BASE_HTML + """
        <h1>Обратная связь</h1>
        <div class="card">
            <p>Ответ пользователю отправляется <strong>без подписи</strong> — только ваш текст.</p>
            {% for f in items %}
            <div class="feedback-item">
                <div class="feedback-meta">#{{ f.id }} · {{ f.user_info }} · {{ f.created_at }}</div>
                <div>{{ f.text }}</div>
                {% if f.reply_text %}
                <div class="feedback-meta" style="margin-top:8px">Ответ: {{ f.reply_text[:100] }}{% if f.reply_text|length > 100 %}...{% endif %} ({{ f.replied_at }})</div>
                {% else %}
                <form class="reply-form" method="post" action="{{ url_for('feedback_reply') }}">
                    <input type="hidden" name="feedback_id" value="{{ f.id }}">
                    <input type="hidden" name="chat_id" value="{{ f.chat_id }}">
                    <textarea name="reply" rows="2" placeholder="Ответ (без подписи)" required></textarea>
                    <button type="submit">Ответить</button>
                </form>
                {% endif %}
            </div>
            {% endfor %}
            {% if not items %}
            <p>Пока нет обращений.</p>
            {% endif %}
        </div>
        """,
        title="Обратная связь",
        items=items,
    )


@app.route("/feedback/reply", methods=["POST"])
@login_required
def feedback_reply():
    feedback_id = request.form.get("feedback_id", type=int)
    chat_id = request.form.get("chat_id", type=int)
    reply = (request.form.get("reply") or "").strip()
    if not feedback_id or not reply:
        flash("Укажите обращение и текст ответа.", "error")
        return redirect(url_for("feedback_page"))
    if not bot:
        flash("Бот не настроен.", "error")
        return redirect(url_for("feedback_page"))
    try:
        bot.send_message(chat_id=chat_id, text=reply)
        set_feedback_replied(feedback_id, reply)
        flash("Ответ отправлен.", "success")
    except Exception as e:
        flash(f"Ошибка отправки: {e}", "error")
    return redirect(url_for("feedback_page"))


@app.route("/checkmail", methods=["POST"])
@login_required
def checkmail():
    if not bot:
        flash("Бот не настроен.", "error")
        return redirect(url_for("dashboard"))
    try:
        from mail_processor import process_mail
        process_mail(bot)
        flash("Проверка почты выполнена.", "success")
    except Exception as e:
        flash(f"Ошибка: {e}", "error")
    return redirect(url_for("dashboard"))


@app.route("/favicon.ico")
def favicon():
    return "", 204


@app.route("/<path:path>")
def catch_all(path):
    """Любой неизвестный путь — на главную."""
    return redirect(url_for("index"))


def main():
    init_db()
    if WEB_PORT == 80:
        print("Веб-панель: http://81.17.154.153 (порт 80)")
    else:
        print(f"Веб-панель: http://81.17.154.153:{WEB_PORT}")
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
