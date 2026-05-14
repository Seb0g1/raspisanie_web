# -*- coding: utf-8 -*-
"""
Парсинг PDF расписания (таблицы из PDF) в структурированные данные:
дата, группы, пары (номер, время, кабинет, дисциплина, преподаватель).
Использует pdfplumber extract_tables() для точного разбора табличной структуры.
"""
import logging
import re
from datetime import date
from typing import List, Tuple, Optional

logger = logging.getLogger(__name__)

MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}

GROUP_CODE_RE = re.compile(r"\d[А-Яа-яA-Za-z0-9]+Б$")
TIME_RE = re.compile(r"\d{1,2}:\d{2}-\d{1,2}:\d{2}")
TEACHER_RE = re.compile(r"[А-Яа-яЁё]+\s+[А-ЯЁ]\.[А-ЯЁ][.,]?\s*$")
ROOM_RE = re.compile(r"^\d{1,4}[а-яa-z]?$", re.IGNORECASE)


def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        import pdfplumber
    except ImportError:
        return ""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
    except Exception as e:
        logger.warning("PDF open error: %s", e)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def parse_date_from_text(text: str) -> Optional[date]:
    """Извлечь дату из заголовка: «13» февраля 2026г. / на 13 февраля 2026 г."""
    patterns = [
        r"на\s*[«\"]?\s*(\d{1,2})\s*[»\"]?\s*(\w+)\s+(\d{4})\s*г",
        r"(\d{1,2})\s+(\w+)\s+(\d{4})\s*г",
        r"«(\d{1,2})»\s*(\w+)\s+(\d{4})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if not m:
            continue
        day = int(m.group(1))
        month_name = m.group(2).lower().strip()
        year = int(m.group(3))
        month = MONTHS.get(month_name)
        if month is None:
            continue
        try:
            return date(year, month, day)
        except ValueError:
            continue
    return None


def _extract_group_code(cell_text: str) -> Optional[str]:
    """Извлечь код группы из ячейки (последняя строка вида 1И25Б)."""
    if not cell_text:
        return None
    lines = [ln.strip() for ln in cell_text.strip().split("\n") if ln.strip()]
    for line in reversed(lines):
        cleaned = line.replace("(", "").replace(")", "").strip()
        if GROUP_CODE_RE.search(cleaned):
            m = GROUP_CODE_RE.search(cleaned)
            return m.group(0) if m else None
    return None


def _is_skip_cell(txt):
    """Проверить, является ли текст служебным (номер урока, время, кабинет)."""
    if not txt:
        return True
    return (ROOM_RE.match(txt) or
            re.match(r"^[1-8]$", txt) or
            TIME_RE.match(txt))


def _parse_row(row):
    """Разобрать одну строку таблицы, находя поля по содержимому.
    Возвращает dict с найденными полями или None.

    Логика: находим время (якорь), номер урока слева от него,
    кабинет сразу справа, затем дисциплину и преподавателя —
    последние два значимых текстовых поля после кабинета.
    """
    ncols = len(row)
    time_col = None
    time_str = None

    # 1) Найти колонку времени (первое вхождение)
    for ci in range(ncols):
        cell = row[ci]
        if cell and TIME_RE.match(cell.strip()):
            time_col = ci
            time_str = cell.strip()
            break

    if time_col is None:
        return None

    # 2) Номер урока — ближайшая цифра 1-8 ЛЕВЕЕ времени
    lesson_num = None
    for ci in range(time_col - 1, -1, -1):
        cell = row[ci]
        if cell and re.match(r"^[1-8]$", cell.strip()):
            lesson_num = int(cell.strip())
            break

    if lesson_num is None:
        return None

    # 3) Кабинет — первое число 1-4 цифры ПРАВЕЕ времени (до 3 колонок)
    room = None
    room_col = None
    for ci in range(time_col + 1, min(time_col + 4, ncols)):
        cell = row[ci]
        if cell and ROOM_RE.match(cell.strip()):
            room = cell.strip()
            room_col = ci
            break

    # 4) Собираем все значимые текстовые ячейки ПРАВЕЕ кабинета (или времени)
    #    Пропускаем дубликаты (артефакты merged cells) и служебные значения.
    text_start = (room_col + 1) if room_col is not None else (time_col + 1)
    text_fields = []
    seen_texts = set()
    for ci in range(text_start, ncols):
        cell = row[ci]
        if not cell or not cell.strip():
            continue
        txt = cell.strip()
        # Пропускаем служебные ячейки
        if _is_skip_cell(txt):
            # Но если это кабинет и у нас его ещё нет — подхватим
            if room is None and ROOM_RE.match(txt):
                room = txt
            continue
        # Пропускаем дубликаты (merged cell artifacts)
        if txt in seen_texts:
            continue
        seen_texts.add(txt)
        text_fields.append(txt)

    # 5) Из text_fields определяем дисциплину и преподавателя.
    #    Преподаватель — это поле, соответствующее паттерну TEACHER_RE.
    #    Дисциплина — все остальные текстовые поля (объединяем).
    teacher = None
    discipline_parts = []
    for txt in text_fields:
        if TEACHER_RE.match(txt):
            teacher = txt.rstrip(",. ")
        else:
            discipline_parts.append(txt)

    discipline = " ".join(discipline_parts) if discipline_parts else ""

    time_parts = time_str.split("-")
    time_start = time_parts[0].strip() if len(time_parts) >= 1 else ""
    time_end = time_parts[1].strip() if len(time_parts) >= 2 else ""

    return {
        "num": lesson_num,
        "time_start": time_start,
        "time_end": time_end,
        "room": room,
        "discipline": discipline,
        "teacher": teacher or "",
    }


def _find_continuation_text(row, time_col_hint):
    """Для строки без номера урока/времени — найти текст дисциплины (продолжение)."""
    ncols = len(row)
    # Ищем любой значимый текст правее середины строки (где обычно дисциплина)
    start = max(time_col_hint, ncols // 3) if time_col_hint else ncols // 3
    parts = []
    seen = set()
    for ci in range(start, ncols):
        cell = row[ci]
        if not cell:
            continue
        txt = cell.strip()
        if not txt:
            continue
        # Пропускаем номера кабинетов и уроков
        if _is_skip_cell(txt):
            continue
        if TEACHER_RE.match(txt):
            continue
        if txt in seen:
            continue
        seen.add(txt)
        parts.append(txt)
    return " ".join(parts) if parts else None


def _scan_group_codes(table):
    """Пре-сканировать таблицу и найти все строки с кодами групп.
    Возвращает dict: row_index -> group_code."""
    groups = {}
    for ri, row in enumerate(table):
        if len(row) < 3:
            continue
        for check_col in range(min(3, len(row))):
            if row[check_col]:
                cell_text = row[check_col].strip()
                if re.match(r"^\d\s*КУРС$", cell_text, re.IGNORECASE):
                    continue
                group = _extract_group_code(cell_text)
                if group:
                    groups[ri] = group
                    break
    return groups


def _parse_table(table, carry_group=None, carry_pending=None) -> Tuple[List[Tuple[str, List[dict]]], Optional[str], list]:
    """Парсинг одной таблицы.
    Возвращает ([(group_code, lessons), ...], last_group_code, pending_lessons).
    carry_group — группа с предыдущей таблицы/страницы для продолжения.
    carry_pending — буфер уроков без группы с предыдущей таблицы."""
    if not table or len(table) < 2:
        return [], carry_group, carry_pending or []

    # Пре-сканируем все группы чтобы знать какие уроки кому принадлежат
    group_rows = _scan_group_codes(table)

    result = []
    current_group = carry_group
    current_lessons = []
    last_room = None
    last_time_col = None
    pending_lessons = list(carry_pending or [])

    for ri, row in enumerate(table):
        if len(row) < 3:
            continue

        # Проверяем наличие группы
        if ri in group_rows:
            new_group = group_rows[ri]
            # Сохраняем предыдущую группу
            if current_group and current_lessons:
                result.append((current_group, current_lessons))
            current_group = new_group
            # Присоединяем pending_lessons (уроки до кода группы на той же странице)
            current_lessons = list(pending_lessons)
            pending_lessons = []
            last_room = None

        # Пробуем распарсить строку как урок
        parsed = _parse_row(row)

        if parsed is None:
            # Может быть продолжение дисциплины
            target = current_lessons or pending_lessons
            if target:
                cont = _find_continuation_text(row, last_time_col)
                if cont:
                    target[-1]["discipline"] += " " + cont
            continue

        # Detect group boundary: if lesson numbers restart (e.g. after 6,7,8 comes 1)
        # this means a new group started even without explicit group code yet
        if current_group and current_lessons:
            last_num = current_lessons[-1]["num"]
            if parsed["num"] <= last_num and parsed["num"] <= 2:
                # Save current group, start buffering for new group
                result.append((current_group, current_lessons))
                current_group = None
                current_lessons = []
                last_room = None
                # Check if group code is ahead in this table
                found_ahead = False
                for look in range(ri + 1, min(ri + 8, len(table))):
                    if look in group_rows:
                        found_ahead = True
                        break
                if found_ahead:
                    pending_lessons = [parsed]
                    continue
                else:
                    # Group code might be on next page — buffer as pending
                    pending_lessons = [parsed]
                    continue

        # Если нет текущей группы — буферизуем урок (группа может быть впереди или на след. странице)
        if not current_group:
            pending_lessons.append(parsed)
            continue

        # Запоминаем позицию времени для продолжений
        for ci in range(len(row)):
            if row[ci] and TIME_RE.match(row[ci].strip()):
                last_time_col = ci
                break

        # Кабинет: если не найден, наследуем
        if parsed["room"]:
            last_room = parsed["room"]
        else:
            parsed["room"] = last_room

        # Пропускаем ПРАКТИКА
        if "ПРАКТИКА" in parsed["discipline"].upper():
            continue

        if parsed["discipline"] or parsed["teacher"]:
            current_lessons.append(parsed)

    if current_group and current_lessons:
        result.append((current_group, current_lessons))
        current_lessons = []

    return result, current_group, pending_lessons


def parse_schedule_pdf(pdf_path: str) -> Tuple[Optional[date], List[Tuple[str, List[dict]]]]:
    """Извлечь таблицы из PDF и распарсить расписание."""
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not installed")
        return None, []

    schedule_date = None
    all_groups = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            first_text = pdf.pages[0].extract_text() if pdf.pages else ""
            if first_text:
                schedule_date = parse_date_from_text(first_text)

            carry_group = None
            carry_pending = []
            for pi, page in enumerate(pdf.pages):
                tables = page.extract_tables()
                for ti, table in enumerate(tables):
                    if not table or len(table) < 3 or len(table[0]) < 5:
                        continue
                    try:
                        groups, carry_group, carry_pending = _parse_table(table, carry_group, carry_pending)
                        all_groups.extend(groups)
                    except Exception as e:
                        logger.warning("Parse table error page %d table %d: %s", pi, ti, e)

    except Exception as e:
        logger.warning("PDF parse error: %s", e)

    # Merge duplicates (group split across pages)
    merged = {}
    for group_code, lessons in all_groups:
        if group_code in merged:
            merged[group_code].extend(lessons)
        else:
            merged[group_code] = list(lessons)

    # Post-process: fill in missing rooms (merged cells — even lessons inherit from previous)
    for code in merged:
        lessons = merged[code]
        for i in range(1, len(lessons)):
            if not lessons[i]["room"] and lessons[i - 1]["room"]:
                lessons[i]["room"] = lessons[i - 1]["room"]

    result = [(code, lessons) for code, lessons in merged.items() if lessons]
    logger.info("Parsed %d groups from %s", len(result), pdf_path)
    return schedule_date, result


# Legacy compatibility
def parse_schedule_text(text: str) -> Tuple[Optional[date], List[Tuple[str, List[dict]]]]:
    """Fallback text parser (legacy). Prefer parse_schedule_pdf."""
    schedule_date = parse_date_from_text(text)
    return schedule_date, []
