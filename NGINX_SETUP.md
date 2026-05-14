# Настройка Nginx для бота расписания

Пошаговая настройка Nginx на сервере: панель по IP, поддомен **bot.sebog1.ru** с HTTPS для инлайн-PDF.

---

## Что должно получиться

| Адрес | Назначение |
|-------|------------|
| `http://81.17.154.153` | Панель бота (логин, рассылка, обратная связь) |
| `https://bot.sebog1.ru` | То же по домену с HTTPS (нужно для отправки PDF в чат через инлайн) |
| `https://bot.sebog1.ru/schedule/2026-02-16.pdf` | Прямая ссылка на PDF расписания на дату |

---

## 1. Подключение к серверу

```bash
ssh root@81.17.154.153
```

(или ваш пользователь, если не root)

---

## 2. Установка Nginx и Certbot (если ещё не стоят)

```bash
# Nginx
sudo apt update
sudo apt install -y nginx

# Certbot для бесплатного SSL (Let's Encrypt)
sudo apt install -y certbot python3-certbot-nginx
```

Проверка, что Nginx запущен:

```bash
sudo systemctl status nginx
```

---

## 3. DNS: запись для поддомена

В панели, где управляете доменом **sebog1.ru** (рег.ру, nic.ru, Cloudflare и т.д.):

1. Откройте раздел DNS / Управление зоной.
2. Добавьте **A-запись**:
   - **Имя/хост:** `bot` (получится bot.sebog1.ru)
   - **Тип:** A
   - **Значение/IP:** `81.17.154.153`
   - TTL: 300–3600 (по умолчанию)

Сохраните и подождите 5–15 минут. Проверка с вашего ПК:

```bash
ping bot.sebog1.ru
```

Должен отвечать IP 81.17.154.153.

---

## 4. Конфиг Nginx на сервере

Перейдите в каталог бота и скопируйте пример конфига:

```bash
cd /home/bot_rasp
sudo cp nginx_bot_rasp.conf.example /etc/nginx/sites-available/bot_rasp
```

Откройте конфиг для правки:

```bash
sudo nano /etc/nginx/sites-available/bot_rasp
```

**Вариант А — только по IP (без HTTPS поддомена)**  
Оставьте файл как есть (один блок `server` с `server_name 81.17.154.153`). Сохраните: `Ctrl+O`, Enter, `Ctrl+X`.

**Вариант Б — поддомен bot.sebog1.ru с HTTPS**  
Раскомментируйте второй и третий блоки `server` (уберите `#` в начале строк). Должно получиться так:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name 81.17.154.153;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    listen [::]:80;
    server_name bot.sebog1.ru;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name bot.sebog1.ru;

    ssl_certificate     /etc/letsencrypt/live/bot.sebog1.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bot.sebog1.ru/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Сохраните файл.

---

## 5. Включение сайта и проверка Nginx

```bash
sudo ln -sf /etc/nginx/sites-available/bot_rasp /etc/nginx/sites-enabled/
sudo nginx -t
```

Должно быть: `syntax is ok` и `test is successful`. Затем:

```bash
sudo systemctl reload nginx
```

Проверьте в браузере:

- http://81.17.154.153 — должна открыться панель входа бота.

Если вы включили блоки для bot.sebog1.ru, но **ещё не получали сертификат**, Nginx может ругаться на отсутствие файлов SSL. Тогда временно закомментируйте блок с `listen 443` и оставьте только редирект с 80 на https (блок с `return 301`). Либо переходите к шагу 6 — Certbot сам создаст конфиг для SSL.

---

## 6. Сертификат SSL для bot.sebog1.ru

Выполняйте **после** того, как DNS для bot.sebog1.ru указывает на 81.17.154.153:

```bash
sudo certbot --nginx -d bot.sebog1.ru
```

- Введите email для уведомлений Let's Encrypt.
- Согласитесь с условиями (Y).
- Certbot сам настроит Nginx и создаст/обновит блок с `listen 443`. Если вы вручную уже добавили блок с `ssl_certificate`, certbot может подставить свои пути — проверьте конфиг после:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Проверка:

- https://bot.sebog1.ru — панель по HTTPS.
- https://bot.sebog1.ru/schedule/2026-02-16.pdf — если есть расписание на эту дату, откроется/скачается PDF.

---

## 7. Переменная окружения для инлайн-PDF

В каталоге бота отредактируйте `.env`:

```bash
cd /home/bot_rasp
nano .env
```

Добавьте или измените (при работе за Nginx порт должен быть 5001, не 80):

```env
WEB_PORT=5001
PUBLIC_BASE_URL=https://bot.sebog1.ru
```

Сохраните файл и перезапустите веб-сервис бота:

```bash
sudo systemctl restart bot_rasp_web
```

Проверьте статус:

```bash
sudo systemctl status bot_rasp_web
```

---

## 8. Итоговая проверка

1. **По IP:** http://81.17.154.153 — панель входа.
2. **По домену:** https://bot.sebog1.ru — та же панель по HTTPS.
3. **PDF:** откройте в браузере ссылку вида  
   `https://bot.sebog1.ru/schedule/2026-02-16.pdf`  
   (подставьте дату, на которую есть расписание).
4. **Инлайн в Telegram:** в любом чате введите `@raspisaniecpsu_bot завтра`, выберите «Расписание на …» — в чат должен отправиться PDF.

---

## Сайт не открывается («как будто не запущен»)

По шагам проверьте следующее.

### 1. Запущен ли сервис панели

На сервере выполните:

```bash
sudo systemctl status bot_rasp_web
```

- Если **inactive (dead)** или **failed** — запустите и включите автозапуск:

```bash
sudo systemctl start bot_rasp_web
sudo systemctl enable bot_rasp_web
```

- Если сервис падает сразу после старта — смотрите логи (шаг 3).

### 2. Установлен ли сервис

Если команда `status` пишет «Unit bot_rasp_web.service could not be found»:

```bash
# Скопировать unit-файл (путь — где лежит проект на сервере)
sudo cp /home/bot_rasp/bot_rasp_web.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start bot_rasp_web
sudo systemctl enable bot_rasp_web
```

Проверьте, что в файле `/etc/systemd/system/bot_rasp_web.service` указаны правильные пути:
- `WorkingDirectory=/home/bot_rasp`
- `ExecStart=/home/bot_rasp/venv/bin/python api.py`
- `EnvironmentFile=/home/bot_rasp/.env`

### 3. Порт в .env и в Nginx

Панель должна слушать **внутренний** порт (не 80). В `.env` на сервере должно быть:

```env
WEB_PORT=5001
```

Не ставьте `WEB_PORT=80` — порт 80 занимает Nginx. Nginx проксирует запросы на `127.0.0.1:5001`.

В конфиге Nginx в `proxy_pass` должен быть тот же порт:

```nginx
proxy_pass http://127.0.0.1:5001;
```

После смены `.env` перезапустите панель:

```bash
sudo systemctl restart bot_rasp_web
```

### 4. Логи панели

Чтобы увидеть ошибки при старте:

```bash
sudo journalctl -u bot_rasp_web -n 80 --no-pager
```

Или в реальном времени:

```bash
sudo journalctl -u bot_rasp_web -f
```

Типичные причины сбоя: нет файла `.env`, неправильный путь к `venv`, ошибка в коде (импорт, база данных). Текст ошибки в логах подскажет, что править.

### 5. Проверка без Nginx

Убедиться, что панель сама по себе поднимается:

```bash
cd /home/bot_rasp
source venv/bin/activate
python api.py
```

В браузере откройте `http://81.17.154.153:5001`. Если страница открывается — панель работает, проблема в Nginx или в том, что вы открываете порт 80 без прокси. Остановите проверку: `Ctrl+C`, снова запустите сервис: `sudo systemctl start bot_rasp_web`.

---

## Частые проблемы

**Nginx не стартует после правок**  
Проверьте синтаксис: `sudo nginx -t`. Смотрите логи: `sudo journalctl -u nginx -n 50 --no-pager`.

**502 Bad Gateway**  
Панель бота не запущена. Проверьте: `sudo systemctl status bot_rasp_web` и при необходимости запустите/перезапустите сервис.

**Certbot: «Connection refused» или «Domain not found»**  
Убедитесь, что DNS для bot.sebog1.ru указывает на 81.17.154.153 и что Nginx слушает 80 порт для этого домена. Временно отключите блок с 443, оставьте только 80, снова запустите certbot.

**PDF в инлайне не отправляется в чат**  
Проверьте, что в `.env` задан `PUBLIC_BASE_URL=https://bot.sebog1.ru` (именно HTTPS), перезапущен `bot_rasp_web`, и что ссылка вида  
`https://bot.sebog1.ru/schedule/2026-02-16.pdf` открывается в браузере.

**Обновление сертификата**  
Let's Encrypt выдаёт сертификат на 90 дней. Обычно стоит таймер certbot:

```bash
sudo systemctl status certbot.timer
```

При необходимости обновить вручную:

```bash
sudo certbot renew --nginx
```

---

Готовый пример конфига лежит в проекте: `nginx_bot_rasp.conf.example`.
