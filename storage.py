import os
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from typing import Optional, List, Tuple

from config import DB_PATH, ARCHIVE_DIR, TEACHERS_DIR


def ensure_dirs() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    os.makedirs(TEACHERS_DIR, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _get_conn():
    """Context manager: auto commit on success, rollback on error, always close."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with _get_conn() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_date DATE UNIQUE NOT NULL,
                file_path TEXT NOT NULL,
                email_date DATETIME NOT NULL,
                created_at DATETIME NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS subscribers (
                chat_id INTEGER PRIMARY KEY,
                first_seen DATETIME NOT NULL,
                last_activity DATETIME
            )
            """
        )
        try:
            cur.execute("ALTER TABLE subscribers ADD COLUMN last_activity DATETIME")
        except sqlite3.OperationalError:
            pass
        for sql in (
            "ALTER TABLE subscribers ADD COLUMN group_code TEXT",
            "ALTER TABLE subscribers ADD COLUMN notifications_enabled INTEGER NOT NULL DEFAULT 1",
            "ALTER TABLE subscribers ADD COLUMN group_missing_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE subscribers ADD COLUMN settings_updated_at DATETIME",
        ):
            try:
                cur.execute(sql)
            except sqlite3.OperationalError:
                pass

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_info TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                reply_text TEXT,
                replied_at DATETIME
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS teachers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                group_abbr TEXT,
                created_at DATETIME NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule_lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schedule_date DATE NOT NULL,
                group_code TEXT NOT NULL,
                lesson_num INTEGER NOT NULL,
                time_start TEXT NOT NULL,
                time_end TEXT NOT NULL,
                room TEXT,
                discipline TEXT NOT NULL,
                teacher TEXT NOT NULL
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_schedule_lessons_date ON schedule_lessons(schedule_date)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_schedule_lessons_group ON schedule_lessons(schedule_date, group_code)"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_schedule_lessons_teacher ON schedule_lessons(schedule_date, teacher)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_emails (
                message_id TEXT PRIMARY KEY,
                processed_at DATETIME NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS processed_updates (
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                processed_at DATETIME NOT NULL,
                PRIMARY KEY (chat_id, message_id)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS subscriber_group_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                old_group_code TEXT,
                new_group_code TEXT,
                changed_at DATETIME NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_schedule_notifications (
                chat_id INTEGER NOT NULL,
                schedule_date DATE NOT NULL,
                kind TEXT NOT NULL,
                sent_at DATETIME NOT NULL,
                PRIMARY KEY (chat_id, schedule_date, kind)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS mail_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message_id TEXT,
                subject TEXT,
                schedule_date DATE,
                detail TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_mail_events_created ON mail_events(created_at)"
        )


def save_schedule(schedule_date: date, file_path: str, email_date: datetime) -> None:
    with _get_conn() as conn:
        conn.cursor().execute(
            """
            INSERT INTO schedules (schedule_date, file_path, email_date, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(schedule_date) DO UPDATE SET
                file_path=excluded.file_path,
                email_date=excluded.email_date
            """,
            (
                schedule_date.isoformat(),
                file_path,
                email_date.isoformat(),
                datetime.utcnow().isoformat(),
            ),
        )


def get_schedule(schedule_date: date) -> Optional[str]:
    with _get_conn() as conn:
        row = conn.cursor().execute(
            "SELECT file_path FROM schedules WHERE schedule_date = ?",
            (schedule_date.isoformat(),),
        ).fetchone()
        return row["file_path"] if row else None


def list_schedules() -> List[Tuple[date, str]]:
    with _get_conn() as conn:
        rows = conn.cursor().execute(
            "SELECT schedule_date, file_path FROM schedules ORDER BY schedule_date DESC"
        ).fetchall()
        return [(date.fromisoformat(row["schedule_date"]), row["file_path"]) for row in rows]


def add_subscriber(chat_id: int) -> None:
    now = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        conn.cursor().execute(
            """
            INSERT INTO subscribers (chat_id, first_seen, last_activity)
            VALUES (?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET last_activity = excluded.last_activity
            """,
            (chat_id, now, now),
        )


def update_subscriber_activity(chat_id: int) -> None:
    """Обновить время последней активности подписчика."""
    with _get_conn() as conn:
        conn.cursor().execute(
            "UPDATE subscribers SET last_activity = ? WHERE chat_id = ?",
            (datetime.utcnow().isoformat(), chat_id),
        )


def get_subscribers() -> List[int]:
    with _get_conn() as conn:
        rows = conn.cursor().execute("SELECT chat_id FROM subscribers").fetchall()
        return [int(row["chat_id"]) for row in rows]


def get_subscribers_with_settings() -> List[dict]:
    with _get_conn() as conn:
        rows = conn.cursor().execute(
            """
            SELECT chat_id, group_code, notifications_enabled, group_missing_count
            FROM subscribers
            """
        ).fetchall()
        return [
            {
                "chat_id": int(row["chat_id"]),
                "group_code": row["group_code"],
                "notifications_enabled": bool(row["notifications_enabled"]),
                "group_missing_count": int(row["group_missing_count"] or 0),
            }
            for row in rows
        ]


def get_subscriber_settings(chat_id: int) -> dict:
    with _get_conn() as conn:
        row = conn.cursor().execute(
            """
            SELECT chat_id, group_code, notifications_enabled, group_missing_count
            FROM subscribers WHERE chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        if not row:
            return {
                "chat_id": chat_id,
                "group_code": None,
                "notifications_enabled": True,
                "group_missing_count": 0,
            }
        return {
            "chat_id": int(row["chat_id"]),
            "group_code": row["group_code"],
            "notifications_enabled": bool(row["notifications_enabled"]),
            "group_missing_count": int(row["group_missing_count"] or 0),
        }


def set_subscriber_group(chat_id: int, group_code: Optional[str]) -> None:
    add_subscriber(chat_id)
    new_group = group_code.strip().upper() if group_code and group_code.strip() else None
    now = datetime.utcnow().isoformat()
    with _get_conn() as conn:
        cur = conn.cursor()
        row = cur.execute(
            "SELECT group_code FROM subscribers WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        old_group = row["group_code"] if row else None
        cur.execute(
            """
            UPDATE subscribers
            SET group_code = ?, group_missing_count = 0, settings_updated_at = ?
            WHERE chat_id = ?
            """,
            (new_group, now, chat_id),
        )
        if old_group != new_group:
            cur.execute(
                """
                INSERT INTO subscriber_group_history
                (chat_id, old_group_code, new_group_code, changed_at)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, old_group, new_group, now),
            )


def set_notifications_enabled(chat_id: int, enabled: bool) -> None:
    add_subscriber(chat_id)
    with _get_conn() as conn:
        conn.cursor().execute(
            """
            UPDATE subscribers
            SET notifications_enabled = ?, settings_updated_at = ?
            WHERE chat_id = ?
            """,
            (1 if enabled else 0, datetime.utcnow().isoformat(), chat_id),
        )


def get_subscriber_count() -> int:
    with _get_conn() as conn:
        return conn.cursor().execute("SELECT COUNT(*) AS n FROM subscribers").fetchone()["n"]


def get_new_subscribers_count(days: int = 7) -> int:
    """Количество подписчиков, впервые зашедших за последние days дней."""
    with _get_conn() as conn:
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        return conn.cursor().execute(
            "SELECT COUNT(*) AS n FROM subscribers WHERE first_seen >= ?",
            (since,),
        ).fetchone()["n"]


def get_active_count(days: int = 7) -> int:
    """Количество подписчиков с активностью за последние days дней."""
    with _get_conn() as conn:
        since = (datetime.utcnow() - timedelta(days=days)).isoformat()
        return conn.cursor().execute(
            "SELECT COUNT(*) AS n FROM subscribers WHERE last_activity >= ?",
            (since,),
        ).fetchone()["n"]


def save_feedback(chat_id: int, user_info: str, text: str) -> int:
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO feedback (chat_id, user_info, text, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, user_info, text, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def get_feedback_list() -> List[dict]:
    with _get_conn() as conn:
        rows = conn.cursor().execute(
            """
            SELECT id, chat_id, user_info, text, created_at, reply_text, replied_at
            FROM feedback ORDER BY created_at DESC
            """
        ).fetchall()
        return [
            {
                "id": row["id"],
                "chat_id": row["chat_id"],
                "user_info": row["user_info"],
                "text": row["text"],
                "created_at": row["created_at"],
                "reply_text": row["reply_text"],
                "replied_at": row["replied_at"],
            }
            for row in rows
        ]


def set_feedback_replied(feedback_id: int, reply_text: str) -> bool:
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE feedback SET reply_text = ?, replied_at = ?
            WHERE id = ?
            """,
            (reply_text, datetime.utcnow().isoformat(), feedback_id),
        )
        return cur.rowcount > 0


def add_teacher(name: str, file_path: str, group_abbr: Optional[str] = None) -> int:
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO teachers (name, file_path, group_abbr, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (name.strip(), file_path, group_abbr.strip() if group_abbr else None, datetime.utcnow().isoformat()),
        )
        return cur.lastrowid


def save_parsed_lessons(schedule_date: date, groups_lessons: List[Tuple[str, List[dict]]]) -> None:
    """Сохранить распарсенное расписание (удаляет старые данные на эту дату)."""
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM schedule_lessons WHERE schedule_date = ?", (schedule_date.isoformat(),))
        for group_code, lessons in groups_lessons:
            for les in lessons:
                cur.execute(
                    """
                    INSERT INTO schedule_lessons
                    (schedule_date, group_code, lesson_num, time_start, time_end, room, discipline, teacher)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        schedule_date.isoformat(),
                        group_code,
                        les.get("num", 0),
                        les.get("time_start", ""),
                        les.get("time_end", ""),
                        les.get("room"),
                        les.get("discipline", ""),
                        les.get("teacher", ""),
                    ),
                )


def get_lessons_by_group(schedule_date: date, group_query: str) -> Optional[Tuple[str, List[dict]]]:
    """Найти группу по запросу (регистронезависимо, LIKE) и вернуть (group_code, lessons)."""
    with _get_conn() as conn:
        cur = conn.cursor()
        q = f"%{group_query.strip()}%"
        row = cur.execute(
            """
            SELECT DISTINCT group_code FROM schedule_lessons
            WHERE schedule_date = ? AND LOWER(group_code) LIKE LOWER(?)
            """,
            (schedule_date.isoformat(), q),
        ).fetchone()
        if not row:
            return None
        group_code = row["group_code"]
        lessons = [
            {
                "num": r["lesson_num"],
                "time_start": r["time_start"],
                "time_end": r["time_end"],
                "room": r["room"],
                "discipline": r["discipline"],
                "teacher": r["teacher"],
            }
            for r in cur.execute(
                """
                SELECT lesson_num, time_start, time_end, room, discipline, teacher
                FROM schedule_lessons
                WHERE schedule_date = ? AND group_code = ?
                ORDER BY lesson_num
                """,
                (schedule_date.isoformat(), group_code),
            ).fetchall()
        ]
        return (group_code, lessons)


def get_lessons_by_teacher(schedule_date: date, teacher_query: str) -> Optional[List[Tuple[str, List[dict]]]]:
    """Найти все пары преподавателя по запросу (фамилия). Возвращает [(group_code, lessons), ...]."""
    with _get_conn() as conn:
        cur = conn.cursor()
        q = f"%{teacher_query.strip()}%"
        groups = [r["group_code"] for r in cur.execute(
            """
            SELECT DISTINCT group_code FROM schedule_lessons
            WHERE schedule_date = ? AND (LOWER(teacher) LIKE LOWER(?) OR teacher LIKE ?)
            ORDER BY group_code
            """,
            (schedule_date.isoformat(), q, q),
        ).fetchall()]
        if not groups:
            return None
        result = []
        for group_code in groups:
            lessons = [
                {
                    "num": r["lesson_num"],
                    "time_start": r["time_start"],
                    "time_end": r["time_end"],
                    "room": r["room"],
                    "discipline": r["discipline"],
                    "teacher": r["teacher"],
                }
                for r in cur.execute(
                    """
                    SELECT lesson_num, time_start, time_end, room, discipline, teacher
                    FROM schedule_lessons
                    WHERE schedule_date = ? AND group_code = ? AND (LOWER(teacher) LIKE LOWER(?) OR teacher LIKE ?)
                    ORDER BY lesson_num
                    """,
                    (schedule_date.isoformat(), group_code, q, q),
                ).fetchall()
            ]
            if lessons:
                result.append((group_code, lessons))
        return result if result else None


def get_available_dates_with_lessons() -> List[date]:
    """Даты, по которым есть распарсенное расписание."""
    with _get_conn() as conn:
        rows = conn.cursor().execute(
            "SELECT DISTINCT schedule_date FROM schedule_lessons ORDER BY schedule_date DESC"
        ).fetchall()
        return [date.fromisoformat(r["schedule_date"]) for r in rows]


def get_groups_for_date(schedule_date: date) -> List[str]:
    with _get_conn() as conn:
        rows = conn.cursor().execute(
            """
            SELECT DISTINCT group_code
            FROM schedule_lessons
            WHERE schedule_date = ?
            ORDER BY group_code
            """,
            (schedule_date.isoformat(),),
        ).fetchall()
        return [row["group_code"] for row in rows]


def get_latest_groups() -> List[str]:
    dates = get_available_dates_with_lessons()
    if not dates:
        return []
    return get_groups_for_date(dates[0])


def find_teachers_by_name(query: str) -> List[dict]:
    """Поиск преподавателей по фамилии (или части имени). Регистронезависимый."""
    if not query or not query.strip():
        return []
    q = "%" + query.strip() + "%"
    with _get_conn() as conn:
        rows = conn.cursor().execute(
            """
            SELECT id, name, file_path, group_abbr
            FROM teachers
            WHERE LOWER(name) LIKE LOWER(?)
            ORDER BY name
            """,
            (q,),
        ).fetchall()
        return [
            {"id": row["id"], "name": row["name"], "file_path": row["file_path"], "group_abbr": row["group_abbr"]}
            for row in rows
        ]


def remove_subscriber(chat_id: int) -> None:
    """Удалить подписчика (например, если бот заблокирован)."""
    with _get_conn() as conn:
        conn.cursor().execute("DELETE FROM subscribers WHERE chat_id = ?", (chat_id,))


def is_email_processed(message_id: str) -> bool:
    """Проверить, было ли письмо уже обработано."""
    with _get_conn() as conn:
        row = conn.cursor().execute(
            "SELECT 1 FROM processed_emails WHERE message_id = ?", (message_id,)
        ).fetchone()
        return row is not None


def mark_email_processed(message_id: str) -> None:
    """Пометить письмо как обработанное."""
    with _get_conn() as conn:
        conn.cursor().execute(
            "INSERT OR IGNORE INTO processed_emails (message_id, processed_at) VALUES (?, ?)",
            (message_id, datetime.utcnow().isoformat()),
        )


def mark_update_processed(chat_id: int, message_id: int) -> bool:
    """Return True when the update is new, False when it was already processed."""
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO processed_updates (chat_id, message_id, processed_at)
            VALUES (?, ?, ?)
            """,
            (chat_id, message_id, datetime.utcnow().isoformat()),
        )
        return cur.rowcount > 0


def was_schedule_notification_sent(chat_id: int, schedule_date: date, kind: str) -> bool:
    with _get_conn() as conn:
        row = conn.cursor().execute(
            """
            SELECT 1 FROM sent_schedule_notifications
            WHERE chat_id = ? AND schedule_date = ? AND kind = ?
            """,
            (chat_id, schedule_date.isoformat(), kind),
        ).fetchone()
        return row is not None


def mark_schedule_notification_sent(chat_id: int, schedule_date: date, kind: str) -> None:
    with _get_conn() as conn:
        conn.cursor().execute(
            """
            INSERT OR IGNORE INTO sent_schedule_notifications
            (chat_id, schedule_date, kind, sent_at)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, schedule_date.isoformat(), kind, datetime.utcnow().isoformat()),
        )


def bump_group_missing_count(chat_id: int) -> int:
    add_subscriber(chat_id)
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE subscribers
            SET group_missing_count = COALESCE(group_missing_count, 0) + 1
            WHERE chat_id = ?
            """,
            (chat_id,),
        )
        row = cur.execute(
            "SELECT group_missing_count FROM subscribers WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        return int(row["group_missing_count"] or 0) if row else 0


def reset_group_missing_count(chat_id: int) -> None:
    with _get_conn() as conn:
        conn.cursor().execute(
            "UPDATE subscribers SET group_missing_count = 0 WHERE chat_id = ?",
            (chat_id,),
        )


def add_mail_event(
    level: str,
    event_type: str,
    detail: str,
    message_id: Optional[str] = None,
    subject: Optional[str] = None,
    schedule_date: Optional[date] = None,
) -> None:
    with _get_conn() as conn:
        conn.cursor().execute(
            """
            INSERT INTO mail_events
            (level, event_type, message_id, subject, schedule_date, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                level,
                event_type,
                message_id,
                subject,
                schedule_date.isoformat() if schedule_date else None,
                detail,
                datetime.utcnow().isoformat(),
            ),
        )


def list_mail_events(limit: int = 50) -> List[dict]:
    limit = max(1, min(int(limit or 50), 200))
    with _get_conn() as conn:
        rows = conn.cursor().execute(
            """
            SELECT id, level, event_type, message_id, subject, schedule_date, detail, created_at
            FROM mail_events
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "level": row["level"],
                "event_type": row["event_type"],
                "message_id": row["message_id"],
                "subject": row["subject"],
                "schedule_date": row["schedule_date"],
                "detail": row["detail"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

