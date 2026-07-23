"""Фоновая проверка подписок: ищет билеты по условиям и шлёт уведомления в Telegram."""
import hashlib
import html
import json
import time
from collections import defaultdict
from datetime import datetime, time as dtime, timedelta

import pymysql
import requests
from apscheduler.schedulers.blocking import BlockingScheduler

import tgbot
import rzd_links
from cities import db_params

RZD_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36'
    ),
    'host': 'ticket.rzd.ru',
}


def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if hasattr(value, 'year') and hasattr(value, 'month') and hasattr(value, 'day') and not isinstance(value, str):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def as_time(value, fallback=dtime(8, 0)):
    if value is None:
        return fallback
    if isinstance(value, timedelta):
        total = int(value.total_seconds()) % (24 * 3600)
        hours, rem = divmod(total, 3600)
        minutes = rem // 60
        return dtime(hours, minutes)
    if isinstance(value, dtime):
        return value.replace(second=0, microsecond=0)
    if isinstance(value, datetime):
        return value.time().replace(second=0, microsecond=0)
    text = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return fallback


def in_notify_window(sub, now=None):
    """True if current local time is inside subscription notify_from..notify_to."""
    now = now or datetime.now()
    current = now.time().replace(second=0, microsecond=0)
    start = as_time(sub.get("notify_from"), dtime(8, 0))
    end = as_time(sub.get("notify_to"), dtime(23, 0))
    if start == end:
        return True
    if start < end:
        return start <= current <= end
    # Overnight window, e.g. 22:00–06:00
    return current >= start or current <= end


def train_on_day(date, cityfrom, cityto):
    url = "https://ticket.rzd.ru/apib2b/p/Railway/V1/Search/TrainPricing?service_provider=B2B_RZD"
    payload = json.dumps({
        "Origin": str(cityfrom),
        "Destination": str(cityto),
        "DepartureDate": date,
        "TimeFrom": 0,
        "TimeTo": 24,
        "CarGrouping": "DontGroup",
        "GetByLocalTime": True,
        "SpecialPlacesDemand": "StandardPlacesAndForDisabledPersons",
    })
    response = requests.post(url, headers=RZD_HEADERS, data=payload, timeout=45)
    response.raise_for_status()
    return response.json()


def match_cars(trains_payload, car_type, place_type, price_min, price_max):
    """Фильтрует CarGroups по типу вагона, месту и цене."""
    if car_type == "СИД":
        place_type = "any"
    matches = []
    for item in trains_payload.get("Trains", []):
        for car in item.get("CarGroups", []):
            if car.get("HasPlacesForDisabledPersons"):
                continue
            if car_type not in ("ANY", "ЛЮБОЙ") and car.get("CarTypeName") != car_type:
                continue

            price = float(car.get("MinPrice") or 0)
            if price < float(price_min) or price > float(price_max):
                continue

            lower_qty = int(car.get("LowerPlaceQuantity") or 0)
            upper_qty = int(car.get("UpperPlaceQuantity") or 0)
            place_qty = int(car.get("PlaceQuantity") or 0)
            # сидячие и похожие: нет низа/верха, только PlaceQuantity
            no_berths = lower_qty == 0 and upper_qty == 0

            if place_type == "lower":
                if no_berths:
                    if place_qty <= 0:
                        continue
                elif lower_qty <= 0:
                    continue
            elif place_type == "upper":
                if no_berths:
                    if place_qty <= 0:
                        continue
                elif upper_qty <= 0:
                    continue
            elif place_type == "any":
                if (lower_qty + upper_qty + place_qty) <= 0:
                    continue

            matches.append({
                "train": item.get("DisplayTrainNumber"),
                "departure": item.get("DepartureDateTime"),
                "arrival": item.get("ArrivalDateTime"),
                "depstation": item.get("OriginName"),
                "arrstation": item.get("DestinationName"),
                "car_type": car.get("CarTypeName"),
                "place_type": place_type,
                "price": price,
                "lower": lower_qty,
                "upper": upper_qty,
                "places": place_qty,
            })
    return dedupe_matches(matches)


def dedupe_matches(matches):
    """Склеивает одинаковые поезд+время+тип+цену (разные CarGroups у одного рейса)."""
    merged = {}
    for m in matches:
        key = (
            m.get("train"),
            m.get("departure"),
            m.get("car_type"),
            round(float(m.get("price") or 0), 1),
            m.get("place_type"),
        )
        if key not in merged:
            merged[key] = dict(m)
            continue
        cur = merged[key]
        cur["lower"] = int(cur.get("lower") or 0) + int(m.get("lower") or 0)
        cur["upper"] = int(cur.get("upper") or 0) + int(m.get("upper") or 0)
        cur["places"] = int(cur.get("places") or 0) + int(m.get("places") or 0)
        # оставляем минимальную цену на всякий случай
        cur["price"] = min(float(cur.get("price") or 0), float(m.get("price") or 0))
    return list(merged.values())


def subscription_date_window(sub, today):
    date_from = as_date(sub["date_from"])
    date_to = as_date(sub["date_to"])
    if date_to < today:
        return None
    if date_from < today:
        date_from = today
    return date_from, date_to


def iter_dates(date_from, date_to):
    current = date_from
    while current <= date_to:
        yield current
        current += timedelta(days=1)


def matches_signature(matches):
    raw = "|".join(
        sorted(
            f"{m['train']}:{m['departure']}:{m['price']}:{m['lower']}:{m['upper']}"
            for m in matches
        )
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _escape(value):
    return html.escape(str(value if value is not None else ""), quote=False)


def _place_label(place_type, match):
    if place_type == "lower":
        return "Нижнее"
    if place_type == "upper":
        return "Верхнее"
    if match.get("lower") and not match.get("upper"):
        return "Нижнее"
    if match.get("upper") and not match.get("lower"):
        return "Верхнее"
    return "Любое"


def _car_label(car_type_name):
    mapping = {
        "ПЛАЦ": "Плацкарт",
        "КУПЕ": "Купе",
        "СИД": "Сидячее",
        "ANY": "Любой",
    }
    return mapping.get(car_type_name, car_type_name or "—")


def format_matches(sub, matches):
    route = f"{_escape(sub['dep_name'])} → {_escape(sub['arr_name'])}"
    blocks = [
        "<b>🎫 Есть билеты</b>",
        f"<b>{route}</b>",
        "",
    ]

    for m in matches[:8]:
        try:
            dep_dt = datetime.strptime(m["departure"], "%Y-%m-%dT%H:%M:%S")
            date_s = dep_dt.strftime("%d.%m.%Y")
            time_s = dep_dt.strftime("%H:%M")
        except Exception:
            dep_dt = None
            date_s = _escape(m.get("departure", "—"))
            time_s = "—"

        place = _place_label(sub["place_type"], m)
        car = _car_label(m.get("car_type") or sub["car_type"])
        qty_bits = []
        if m.get("lower"):
            qty_bits.append(f"↓{m['lower']}")
        if m.get("upper"):
            qty_bits.append(f"↑{m['upper']}")
        if not qty_bits and m.get("places"):
            qty_bits.append(f"×{m['places']}")
        qty = f" ({' '.join(qty_bits)})" if qty_bits else ""

        blocks.extend([
            f"<b>🗓️ Дата</b> — {date_s}",
            f"<b>🕗 Время</b> — {time_s}",
            f"<b>🚂 Поезд</b> — {_escape(m.get('train', '—'))}",
            "———",
            f"Место: {place} — {car}{qty}",
            f"Цена: <b>{m['price']:.0f}₽</b>",
        ])

        if dep_dt is not None:
            link = rzd_links.build_search_url(
                sub["dep_station"], sub["arr_station"], dep_dt
            )
            if link:
                blocks.append(f'<a href="{_escape(link)}">Открыть на РЖД</a>')

        blocks.append("")

    if len(matches) > 8:
        blocks.append(f"<i>…и ещё {len(matches) - 8}</i>")

    return "\n".join(blocks).rstrip()


def load_active_subscriptions():
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, tg_id, dep_station, arr_station, dep_name, arr_name,
                       car_type, place_type, price_min, price_max,
                       date_from, date_to, notify_from, notify_to,
                       last_notify_signature
                FROM subscriptions
                WHERE active = 1
                """
            )
            return cursor.fetchall()
    finally:
        connection.close()


def update_notify_signature(sub_id, signature):
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE subscriptions
                SET last_notify_signature = %s, last_notified_at = NOW()
                WHERE id = %s
                """,
                (signature, sub_id),
            )
        connection.commit()
    finally:
        connection.close()


def fetch_direction_days(dep_station, arr_station, dates):
    """Один запрос РЖД на день для направления; результат кэшируется в dict."""
    cache = {}
    for day in sorted(dates):
        date_str = day.strftime("%Y-%m-%dT00:00:00")
        try:
            cache[day] = train_on_day(date_str, dep_station, arr_station)
            print(f"  rzd {dep_station}->{arr_station} {day}: ok")
        except Exception as exc:
            print(f"  rzd {dep_station}->{arr_station} {day}: {exc}")
            cache[day] = {"Trains": []}
        time.sleep(0.4)
    return cache


def match_subscription_from_cache(sub, window, day_cache):
    date_from, date_to = window
    matches = []
    for day in iter_dates(date_from, date_to):
        payload = day_cache.get(day) or {"Trains": []}
        matches.extend(
            match_cars(
                payload,
                sub["car_type"],
                sub["place_type"],
                sub["price_min"],
                sub["price_max"],
            )
        )
    return matches


def notify_subscription(sub, matches):
    if not matches:
        print(f"  sub#{sub['id']}: no matches")
        return

    signature = matches_signature(matches)
    if signature == (sub.get("last_notify_signature") or ""):
        print(f"  sub#{sub['id']}: same matches, skip notify")
        return

    text = format_matches(sub, matches)
    try:
        resp = tgbot.notify_tickets(sub["tg_id"], text)
        print(f"  sub#{sub['id']}: notify {resp.status_code} → {sub['tg_id']}")
        if resp.ok:
            update_notify_signature(sub["id"], signature)
        else:
            print(f"  telegram error: {resp.text[:300]}")
    except Exception as exc:
        print(f"  notify failed: {exc}")


def run():
    print(f"[{datetime.now()}] checking subscriptions…")
    try:
        rzd_links.ensure_node_id_column()
        subs = load_active_subscriptions()
    except Exception as exc:
        print(f"DB error: {exc}")
        return

    if not subs:
        print("no active subscriptions")
        return

    now = datetime.now()
    today = now.date()
    current = []
    expired = 0
    outside_hours = 0
    for sub in subs:
        if not in_notify_window(sub, now):
            outside_hours += 1
            continue
        window = subscription_date_window(sub, today)
        if window is None:
            expired += 1
            continue
        current.append((sub, window))

    print(
        f"active: {len(subs)}, current: {len(current)}, "
        f"outside hours: {outside_hours}, expired: {expired}"
    )
    if not current:
        print("nothing to check right now — skip RZD")
        return

    by_direction = defaultdict(list)
    for sub, window in current:
        key = (int(sub["dep_station"]), int(sub["arr_station"]))
        by_direction[key].append((sub, window))

    for (dep, arr), group in by_direction.items():
        dates_needed = set()
        for _, window in group:
            dates_needed.update(iter_dates(window[0], window[1]))

        print(
            f"direction {dep}->{arr}: "
            f"{len(group)} subs, {len(dates_needed)} days"
        )
        day_cache = fetch_direction_days(dep, arr, dates_needed)
        for sub, window in group:
            matches = match_subscription_from_cache(sub, window, day_cache)
            notify_subscription(sub, matches)


if __name__ == "__main__":
    import sys

    if "--once" in sys.argv:
        run()
    else:
        scheduler = BlockingScheduler()
        scheduler.add_job(run, "interval", minutes=20, next_run_time=datetime.now())
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            pass
