#!/usr/bin/env bash
# Перезапуск бота и веб-панели, затем показ статуса и логов веба
cd "$(dirname "$0")"

echo "=== Перезапуск сервисов ==="
sudo systemctl restart bot_rasp.service bot_rasp_web.service

echo ""
echo "=== Ждём 3 сек ==="
sleep 3

echo ""
echo "=== Статус ==="
sudo systemctl status bot_rasp.service bot_rasp_web.service --no-pager -l || true

echo ""
echo "=== Последние логи веб-панели ==="
sudo journalctl -u bot_rasp_web.service -n 50 --no-pager
