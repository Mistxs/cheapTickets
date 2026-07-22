"""Фоновая проверка подписок: ищет билеты по условиям и шлёт уведомления в Telegram."""
import hashlib
import json
import time
from datetime import datetime, timedelta

import pymysql
import requests
from apscheduler.schedulers.blocking import BlockingScheduler

import tgbot
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

            if place_type == "lower" and lower_qty <= 0:
                continue
            if place_type == "upper" and upper_qty <= 0:
                continue
            if place_type == "any" and (lower_qty + upper_qty + place_qty) <= 0:
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
            })
    return matches


def find_matches_for_subscription(sub):
    date_from = sub["date_from"]
    date_to = sub["date_to"]
    if isinstance(date_from, str):
        date_from = datetime.strptime(date_from, "%Y-%m-%d").date()
    if isinstance(date_to, str):
        date_to = datetime.strptime(date_to, "%Y-%m-%d").date()

    today = datetime.now().date()
    if date_to < today:
        return []
    if date_from < today:
        date_from = today

    all_matches = []
    current = date_from
    while current <= date_to:
        date_str = current.strftime("%Y-%m-%dT00:00:00")
        try:
            payload = train_on_day(date_str, sub["dep_station"], sub["arr_station"])
            day_matches = match_cars(
                payload,
                sub["car_type"],
                sub["place_type"],
                sub["price_min"],
                sub["price_max"],
            )
            all_matches.extend(day_matches)
        except Exception as exc:
            print(f"[sub {sub['id']}] RZD error on {date_str}: {exc}")
        time.sleep(0.4)
        current += timedelta(days=1)
    return all_matches


def matches_signature(matches):
    raw = "|".join(
        sorted(
            f"{m['train']}:{m['departure']}:{m['price']}:{m['lower']}:{m['upper']}"
            for m in matches
        )
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def format_matches(sub, matches):
    place_labels = {"lower": "нижнее", "upper": "верхнее", "any": "любое"}
    car_labels = {"ANY": "любой вагон", "ПЛАЦ": "плацкарт", "КУПЕ": "купе", "СИД": "сидячее"}
    place = place_labels.get(sub["place_type"], sub["place_type"])
    car = car_labels.get(sub["car_type"], sub["car_type"])
    lines = [
        f"{sub['dep_name']} → {sub['arr_name']}",
        f"{car}, место: {place}, до {sub['price_max']:.0f} ₽",
        "",
    ]
    for m in matches[:12]:
        dep = m["departure"].replace("T", " ")
        lines.append(
            f"#{m['train']} {dep} — {m['price']:.0f} ₽ "
            f"(↓{m['lower']} ↑{m['upper']})"
        )
    if len(matches) > 12:
        lines.append(f"…и ещё {len(matches) - 12}")
    return "\n".join(lines)


def load_active_subscriptions():
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, tg_id, dep_station, arr_station, dep_name, arr_name,
                       car_type, place_type, price_min, price_max,
                       date_from, date_to, last_notify_signature
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


def run():
    print(f"[{datetime.now()}] checking subscriptions…")
    try:
        subs = load_active_subscriptions()
    except Exception as exc:
        print(f"DB error: {exc}")
        return

    if not subs:
        print("no active subscriptions")
        return

    print(f"active: {len(subs)}")
    for sub in subs:
        matches = find_matches_for_subscription(sub)
        if not matches:
            print(f"  sub#{sub['id']}: no matches")
            continue

        signature = matches_signature(matches)
        if signature == (sub.get("last_notify_signature") or ""):
            print(f"  sub#{sub['id']}: same matches, skip notify")
            continue

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
