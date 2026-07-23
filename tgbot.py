import os

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
    text = str(value).strip()
    if len(text) >= 5 and text[2] == ":":
        return text[:5]
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

