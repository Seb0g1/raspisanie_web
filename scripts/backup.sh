#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${BOT_RASP_ROOT:-/home/bot_rasp}"
BACKUP_DIR="${BOT_RASP_BACKUP_DIR:-/home/bot_rasp_backups}"
KEEP="${BOT_RASP_BACKUP_KEEP:-14}"
STAMP="$(date -u +%Y%m%d_%H%M%S)"
ARCHIVE_PATH="${BACKUP_DIR}/bot_rasp_${STAMP}.tar.gz"

mkdir -p "${BACKUP_DIR}"
cd "${ROOT_DIR}"

items=()
for item in data archive .env; do
  if [ -e "${item}" ]; then
    items+=("${item}")
  fi
done

if [ "${#items[@]}" -eq 0 ]; then
  echo "Nothing to back up in ${ROOT_DIR}"
  exit 0
fi

tar -czf "${ARCHIVE_PATH}" "${items[@]}"
echo "Created ${ARCHIVE_PATH}"

find "${BACKUP_DIR}" -maxdepth 1 -name 'bot_rasp_*.tar.gz' -type f \
  | sort -r \
  | tail -n +"$((KEEP + 1))" \
  | xargs -r rm -f
