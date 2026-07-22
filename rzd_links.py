"""Ссылки на поиск ticket.rzd.ru: expressCode → nodeId."""
import time

import pymysql
import requests

from cities import db_params

SUGGEST_URL = "https://ticket.rzd.ru/api/v1/suggests"
_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
    ),
}

# in-memory cache for one checker run
_node_cache = {}


def ensure_node_id_column():
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW COLUMNS FROM cities LIKE 'node_id'")
            if not cursor.fetchone():
                cursor.execute(
                    "ALTER TABLE cities ADD COLUMN node_id VARCHAR(32) NULL"
                )
                connection.commit()
    finally:
        connection.close()


def _get_cached_node_id(express_code):
    code = int(express_code)
    if code in _node_cache:
        return _node_cache[code]

    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT node_id, cyrname FROM cities WHERE id = %s LIMIT 1",
                (code,),
            )
            row = cursor.fetchone()
    finally:
        connection.close()

    if row and row.get("node_id"):
        _node_cache[code] = row["node_id"]
        return row["node_id"]

    query = (row.get("cyrname") if row else None) or str(code)
    node_id = _fetch_node_id_from_api(code, query)
    if node_id:
        _save_node_id(code, node_id)
        _node_cache[code] = node_id
    return node_id


def _save_node_id(express_code, node_id):
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE cities SET node_id = %s WHERE id = %s",
                (node_id, int(express_code)),
            )
        connection.commit()
    finally:
        connection.close()


def _fetch_node_id_from_api(express_code, query):
    try:
        response = requests.get(
            SUGGEST_URL,
            params={"Query": query, "TransportType": "rail"},
            headers=_HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        items = response.json()
    except Exception as exc:
        print(f"suggests error for {express_code}/{query}: {exc}")
        return None

    code = str(express_code)
    for item in items or []:
        if str(item.get("expressCode")) == code or str(item.get("foreignCode")) == code:
            return item.get("nodeId")

    # fallback: first city-level hit
    for item in items or []:
        if item.get("nodeType") == "city" and item.get("nodeId"):
            return item.get("nodeId")
    return None


def get_node_id(express_code):
    try:
        return _get_cached_node_id(express_code)
    except Exception as exc:
        print(f"node_id resolve failed for {express_code}: {exc}")
        return None


def build_search_url(dep_station, arr_station, departure_dt):
    """
    https://ticket.rzd.ru/searchresults/v/1/{from}/{to}/{yyyy-m-d}?adult=1
    дата без ведущих нулей, как на портале.
    """
    from_id = get_node_id(dep_station)
    to_id = get_node_id(arr_station)
    if not from_id or not to_id:
        return None

    if isinstance(departure_dt, str):
        try:
            departure_dt = __import__("datetime").datetime.strptime(
                departure_dt, "%Y-%m-%dT%H:%M:%S"
            )
        except ValueError:
            return None

    date_part = f"{departure_dt.year}-{departure_dt.month}-{departure_dt.day}"
    return (
        f"https://ticket.rzd.ru/searchresults/v/1/{from_id}/{to_id}/{date_part}?adult=1"
    )
