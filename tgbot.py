import os
import re
from datetime import date, datetime, time, timedelta

import pymysql
import requests

from cities import db_params

BOT_TOKEN = '6746194766:AAFs7xjLRf_n2sWkww3VDrVVQ1F0qkRyz6E'
# sing-box-inna на spica: mixed inbound → VLESS inna
BOT_PROXY = os.environ.get('BOT_PROXY', 'http://127.0.0.1:10808')


def _proxies():
    if not BOT_PROXY:
        return None
    return {'http': BOT_PROXY, 'https': BOT_PROXY}


def ensure_tg_users_table():
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS tg_users (
                    username VARCHAR(64) NOT NULL,
                    chat_id BIGINT NOT NULL,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                        ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (username),
                    UNIQUE KEY uq_chat_id (chat_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
        connection.commit()
    finally:
        connection.close()


def normalize_username(raw):
    value = str(raw or '').strip()
    if value.startswith('@'):
        value = value[1:]
    return value.lower()


def upsert_tg_user(username, chat_id):
    username = normalize_username(username)
    if not username or not chat_id:
        return
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tg_users (username, chat_id)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE chat_id = VALUES(chat_id)
                """,
                (username, int(chat_id)),
            )
        connection.commit()
    finally:
        connection.close()


def lookup_chat_id(username):
    username = normalize_username(username)
    if not username:
        return None
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT chat_id FROM tg_users WHERE username = %s LIMIT 1",
                (username,),
            )
            row = cursor.fetchone()
            return str(row['chat_id']) if row else None
    finally:
        connection.close()


def harvest_bot_updates():
    """Забирает апдейты бота и сохраняет username → chat_id (/start и любые сообщения)."""
    ensure_tg_users_table()
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        response = requests.get(
            url,
            params={"timeout": 0, "limit": 100},
            proxies=_proxies(),
            timeout=30,
        )
        data = response.json()
    except Exception as exc:
        print(f"getUpdates failed: {exc}")
        return 0

    if not data.get("ok"):
        print(f"getUpdates error: {data}")
        return 0

    saved = 0
    max_update_id = None
    for update in data.get("result") or []:
        max_update_id = update.get("update_id", max_update_id)
        message = update.get("message") or update.get("edited_message") or {}
        user = message.get("from") or {}
        chat = message.get("chat") or {}
        username = user.get("username") or chat.get("username")
        chat_id = chat.get("id") or user.get("id")
        if username and chat_id:
            upsert_tg_user(username, chat_id)
            saved += 1

    # подтверждаем апдейты, чтобы не копить
    if max_update_id is not None:
        try:
            requests.get(
                url,
                params={"offset": int(max_update_id) + 1, "limit": 1},
                proxies=_proxies(),
                timeout=15,
            )
        except Exception:
            pass
    return saved


def resolve_chat_id(tg_id):
    """Числовой chat_id или ник → chat_id из tg_users."""
    value = str(tg_id or '').strip()
    if not value:
        return None
    if value.lstrip('-').isdigit():
        return value

    username = normalize_username(value)
    chat_id = lookup_chat_id(username)
    if chat_id:
        return chat_id

    # последняя попытка: как @username (для каналов; для личек обычно не работает)
    return '@' + username


def send_telegram_message(chat_id, message, token=None, parse_mode='HTML'):
    token = token or BOT_TOKEN
    ensure_tg_users_table()
    resolved = resolve_chat_id(chat_id)
    if not resolved:
        class _Resp:
            ok = False
            status_code = 400
            text = '{"ok":false,"description":"empty chat id"}'
        return _Resp()

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': resolved,
        'text': message,
        'disable_web_page_preview': True,
        'parse_mode': parse_mode,
    }
    response = requests.post(url, data=payload, timeout=30, proxies=_proxies())
    return response


def notify_tickets(chat_id, info):
    return send_telegram_message(chat_id, info)


def _escape_html(value):
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _car_label(car_type):
    return {
        "ПЛАЦ": "плацкарт",
        "КУПЕ": "купе",
        "СИД": "сидячее",
        "ANY": "любой вагон",
    }.get(str(car_type or "").upper(), str(car_type or "—"))


def _place_label(place_type):
    return {
        "lower": "нижнее",
        "upper": "верхнее",
        "any": "любое",
    }.get(str(place_type or "").lower(), str(place_type or "любое"))


def _hhmm(value, fallback="08:00"):
    if value is None:
        return fallback
    if isinstance(value, timedelta):
        total = int(value.total_seconds()) % (24 * 3600)
        hours, rem = divmod(total, 3600)
        minutes = rem // 60
        return f"{hours:02d}:{minutes:02d}"
    if isinstance(value, time):
        return f"{value.hour:02d}:{value.minute:02d}"
    if isinstance(value, datetime):
        return f"{value.hour:02d}:{value.minute:02d}"
    text = str(value).strip()
    # HH:MM or H:MM:SS
    m = re.match(r"^(\d{1,2}):(\d{2})", text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    return fallback


def _notify_window_label(notify_from, notify_to):
    start = _hhmm(notify_from, "08:00")
    end = _hhmm(notify_to, "23:00")
    if start == end:
        return "круглосуточно"
    if start < end:
        return f"{start}–{end} МСК"
    return f"{start} → ночь → {end} МСК"


def format_subscription_notice(sub, action="created"):
    """HTML-текст о создании/изменении подписки для Telegram."""
    title = {
        "created": "✅ Подписка создана",
        "updated": "✏️ Подписка обновлена",
        "deleted": "🗑 Подписка удалена",
    }.get(action, "✅ Подписка")

    route = (
        f"{_escape_html(sub.get('dep_name'))} → {_escape_html(sub.get('arr_name'))}"
    )
    date_from = _escape_html(sub.get("date_from") or "—")
    date_to = _escape_html(sub.get("date_to") or "—")
    price_min = sub.get("price_min")
    price_max = sub.get("price_max")
    try:
        price_line = f"{float(price_min):.0f}–{float(price_max):.0f} ₽"
    except Exception:
        price_line = f"{price_min}–{price_max} ₽"

    lines = [
        f"<b>{title}</b>",
    ]
    if sub.get("id") is not None:
        lines.append(f"№{_escape_html(sub.get('id'))}")
    lines.extend([
        f"<b>{route}</b>",
        "",
        f"Даты: {date_from} — {date_to}",
        f"Вагон: {_escape_html(_car_label(sub.get('car_type')))}",
        f"Место: {_escape_html(_place_label(sub.get('place_type')))}",
        f"Цена: {price_line}",
        f"Оповещения: {_escape_html(_notify_window_label(sub.get('notify_from'), sub.get('notify_to')))}",
        "",
        "<i>Бот будет искать билеты в этом окне и напишет, когда появятся подходящие.</i>",
    ])
    return "\n".join(lines)


def notify_subscription_change(sub, action="created"):
    """Шлёт пользователю сводку по подписке. Ошибки Telegram не пробрасывает."""
    try:
        text = format_subscription_notice(sub, action=action)
        resp = send_telegram_message(sub.get("tg_id"), text)
        if getattr(resp, "ok", None) is False or getattr(resp, "status_code", 500) >= 400:
            print(
                f"subscription {action} notify failed for {sub.get('tg_id')}: "
                f"{getattr(resp, 'status_code', '?')} {getattr(resp, 'text', '')[:200]}"
            )
        return resp
    except Exception as exc:
        print(f"subscription {action} notify error: {exc}")
        return None


# --- DB helpers for bot / shared use ---


def serialize_sub_row(row):
    """Нормализует строку subscriptions в dict для UI/notify."""
    if not row:
        return None

    def as_iso_date(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return str(value)[:10]

    return {
        "id": row.get("id"),
        "tg_id": row.get("tg_id"),
        "dep_station": row.get("dep_station"),
        "arr_station": row.get("arr_station"),
        "dep_name": row.get("dep_name"),
        "arr_name": row.get("arr_name"),
        "car_type": row.get("car_type"),
        "place_type": row.get("place_type"),
        "price_min": row.get("price_min"),
        "price_max": row.get("price_max"),
        "date_from": as_iso_date(row.get("date_from")),
        "date_to": as_iso_date(row.get("date_to")),
        "notify_from": _hhmm(row.get("notify_from"), "08:00"),
        "notify_to": _hhmm(row.get("notify_to"), "23:00"),
        "active": bool(row.get("active", 1)),
    }


def lookup_username_by_chat_id(chat_id):
    if not chat_id:
        return None
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT username FROM tg_users WHERE chat_id = %s LIMIT 1",
                (int(chat_id),),
            )
            row = cursor.fetchone()
            return row["username"] if row else None
    finally:
        connection.close()


def search_cities(query, limit=10):
    q = str(query or "").strip()
    if len(q) < 2:
        return []
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, cyrname
                FROM cities
                WHERE cyrname LIKE %s
                ORDER BY cyrname
                LIMIT %s
                """,
                (f"%{q}%", int(limit)),
            )
            return cursor.fetchall() or []
    finally:
        connection.close()


def get_city_by_id(city_id):
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, cyrname FROM cities WHERE id = %s LIMIT 1",
                (int(city_id),),
            )
            return cursor.fetchone()
    finally:
        connection.close()


def list_subscriptions_for_user(username):
    username = normalize_username(username)
    if not username:
        return []
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM subscriptions
                WHERE LOWER(tg_id) = %s AND active = 1
                ORDER BY id DESC
                """,
                (username,),
            )
            rows = cursor.fetchall() or []
    finally:
        connection.close()
    return [serialize_sub_row(r) for r in rows]


def get_subscription_for_user(sub_id, username):
    username = normalize_username(username)
    if not username:
        return None
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM subscriptions
                WHERE id = %s AND LOWER(tg_id) = %s AND active = 1
                LIMIT 1
                """,
                (int(sub_id), username),
            )
            row = cursor.fetchone()
    finally:
        connection.close()
    return serialize_sub_row(row)


def create_subscription_record(payload):
    """
    payload keys: tg_id, dep_station, arr_station, dep_name, arr_name,
    car_type, place_type, price_min, price_max, date_from, date_to,
    notify_from, notify_to
    date_* : date or 'YYYY-MM-DD'; notify_* : 'HH:MM' or time
    """
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO subscriptions (
                    tg_id, dep_station, arr_station, dep_name, arr_name,
                    car_type, place_type, price_min, price_max, date_from, date_to,
                    notify_from, notify_to, active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                """,
                (
                    normalize_username(payload["tg_id"]) or str(payload["tg_id"]).lstrip("@"),
                    int(payload["dep_station"]),
                    int(payload["arr_station"]),
                    payload.get("dep_name"),
                    payload.get("arr_name"),
                    payload["car_type"],
                    payload["place_type"],
                    float(payload.get("price_min") or 0),
                    float(payload["price_max"]),
                    payload["date_from"],
                    payload["date_to"],
                    payload.get("notify_from") or "08:00:00",
                    payload.get("notify_to") or "23:00:00",
                ),
            )
            new_id = cursor.lastrowid
        connection.commit()
        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM subscriptions WHERE id = %s", (new_id,))
            row = cursor.fetchone()
    finally:
        connection.close()
    return serialize_sub_row(row)


def update_subscription_fields(sub_id, username, **fields):
    """Обновляет разрешённые поля. fields: price_max, notify_from, notify_to, ..."""
    username = normalize_username(username)
    allowed = {
        "price_min",
        "price_max",
        "notify_from",
        "notify_to",
        "date_from",
        "date_to",
        "car_type",
        "place_type",
    }
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates or not username:
        return get_subscription_for_user(sub_id, username)

    sets = []
    values = []
    for key, value in updates.items():
        sets.append(f"{key} = %s")
        values.append(value)
    sets.append("last_notify_signature = NULL")
    values.extend([int(sub_id), username])

    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE subscriptions
                SET {', '.join(sets)}
                WHERE id = %s AND LOWER(tg_id) = %s AND active = 1
                """,
                tuple(values),
            )
        connection.commit()
    finally:
        connection.close()
    return get_subscription_for_user(sub_id, username)


def soft_delete_subscription(sub_id, username):
    username = normalize_username(username)
    if not username:
        return False
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE subscriptions
                SET active = 0
                WHERE id = %s AND LOWER(tg_id) = %s AND active = 1
                """,
                (int(sub_id), username),
            )
            changed = cursor.rowcount > 0
        connection.commit()
    finally:
        connection.close()
    return changed


def parse_dmy_date(text):
    text = str(text or "").strip()
    for fmt in ("%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"invalid date: {text}")


def parse_date_range_text(text):
    """'ДД-ММ-ГГГГ — ДД-ММ-ГГГГ' или через пробел/дефис."""
    raw = str(text or "").strip()
    for sep in ("—", "–", " - ", " — ", " to ", ",", ";"):
        if sep in raw:
            left, right = raw.split(sep, 1)
            return parse_dmy_date(left.strip()), parse_dmy_date(right.strip())
    parts = raw.split()
    if len(parts) == 2:
        return parse_dmy_date(parts[0]), parse_dmy_date(parts[1])
    raise ValueError("expected two dates")

