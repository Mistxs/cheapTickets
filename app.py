import json
from datetime import datetime, timedelta

import pymysql
import requests
from flask import Flask, render_template, request, jsonify, Response, send_from_directory

from cities import db_params


def ensure_subscriptions_table():
    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    tg_id VARCHAR(64) NOT NULL,
                    dep_station INT NOT NULL,
                    arr_station INT NOT NULL,
                    dep_name VARCHAR(255) DEFAULT NULL,
                    arr_name VARCHAR(255) DEFAULT NULL,
                    car_type VARCHAR(32) NOT NULL,
                    place_type VARCHAR(16) NOT NULL,
                    price_min FLOAT NOT NULL DEFAULT 0,
                    price_max FLOAT NOT NULL,
                    date_from DATE NOT NULL,
                    date_to DATE NOT NULL,
                    active TINYINT NOT NULL DEFAULT 1,
                    last_notify_signature VARCHAR(64) DEFAULT NULL,
                    last_notified_at DATETIME DEFAULT NULL,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_tg_id (tg_id),
                    INDEX idx_active (active)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
        connection.commit()
    finally:
        connection.close()


ALLOWED_CAR_TYPES = {"ПЛАЦ", "КУПЕ", "СИД", "ANY"}
ALLOWED_PLACE_TYPES = {"lower", "upper", "any"}


def normalize_tg_id(raw):
    if raw is None:
        return ""
    value = str(raw).strip()
    if value.startswith("@"):
        value = value[1:]
    return value


def parse_iso_date(value):
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"invalid date: {value}")


def subscription_payload_from_request(data, partial=False):
    """Собирает и валидирует поля подписки из JSON."""
    errors = []
    result = {}

    def need(key, transform=None):
        if key not in data or data[key] in (None, ""):
            if not partial:
                errors.append(f"missing:{key}")
            return
        value = data[key]
        if transform:
            try:
                value = transform(value)
            except Exception:
                errors.append(f"invalid:{key}")
                return
        result[key] = value

    need("tg_id", normalize_tg_id)
    need("dep_station", lambda v: int(v))
    need("arr_station", lambda v: int(v))
    need("dep_name", lambda v: str(v).strip())
    need("arr_name", lambda v: str(v).strip())
    need("car_type", lambda v: str(v).strip().upper())
    need("place_type", lambda v: str(v).strip().lower())
    need("price_min", lambda v: float(v))
    need("price_max", lambda v: float(v))
    need("date_from", parse_iso_date)
    need("date_to", parse_iso_date)

    if "car_type" in result and result["car_type"] not in ALLOWED_CAR_TYPES:
        errors.append("invalid:car_type")
    if "place_type" in result and result["place_type"] not in ALLOWED_PLACE_TYPES:
        errors.append("invalid:place_type")
    if result.get("car_type") == "СИД":
        result["place_type"] = "any"
    if "price_min" in result and "price_max" in result and result["price_min"] > result["price_max"]:
        errors.append("invalid:price_range")
    if "date_from" in result and "date_to" in result and result["date_from"] > result["date_to"]:
        errors.append("invalid:date_range")
    if "tg_id" in result and not result["tg_id"]:
        errors.append("invalid:tg_id")

    return result, errors


def rzdfind(date,cityfrom, cityto):
  url = "https://ticket.rzd.ru/apib2b/p/Railway/V1/Search/TrainPricing?service_provider=B2B_RZD"

  payload = json.dumps({
    "Origin": cityfrom,
    "Destination": cityto,
    "DepartureDate": date,
    "TimeFrom": 0,
    "TimeTo": 24,
    "CarGrouping": "DontGroup",
    "GetByLocalTime": True,
    "SpecialPlacesDemand": "StandardPlacesAndForDisabledPersons"
  })
  headers = {
    'sec-ch-ua': '"Not/A)Brand";v="99", "Google Chrome";v="115", "Chromium";v="115"',
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json',
    'sec-ch-ua-mobile': '?0',
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'sentry-trace': 'a77deacef2644df4a2669794039f9a4e-87b5ea91c660179e-1',
    'sec-ch-ua-platform': '"macOS"',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Dest': 'empty',
    'host': 'ticket.rzd.ru',
    'Cookie': 'session-cookie=177670e7b0b2a17dbd64334d6940ac72715fcb65feb24b902687c9746d324c6084e21755e85917975c092188951a8ad2'
  }

  response = requests.request("POST", url, headers=headers, data=payload).json()
  return response
def getprice(data, current_date_str):
    min_prices = {}
    for item in data["Trains"]:
      vagon = item["CarGroups"]
      for _ in vagon:
        date = current_date_str
        splitted = date.split("T")
        date = splitted[0]
        train = item["DisplayTrainNumber"]
        depstation = item["OriginName"]
        arrstation = item["DestinationName"]
        arrival = item["ArrivalDateTime"]
        departure = item["DepartureDateTime"]
        price = _['MinPrice']
        vagon_type = _['CarTypeName']
        disabledpersonflag = _["HasPlacesForDisabledPersons"]

        if date not in min_prices:
          min_prices[date] = {}

        if vagon_type not in min_prices[date]:
          min_prices[date][vagon_type] = {}


        if not disabledpersonflag and ("price" not in min_prices[date][vagon_type] or price < min_prices[date][vagon_type]["price"]):
            print(item)
            departure_datetime = datetime.strptime(departure, '%Y-%m-%dT%H:%M:%S')
            arrival_datetime = datetime.strptime(arrival, '%Y-%m-%dT%H:%M:%S')
            formatted_departure = departure_datetime.strftime('%d-%m-%Y %H:%M')
            formatted_arrival = arrival_datetime.strftime('%d-%m-%Y %H:%M')
            min_prices[date][vagon_type] = {
                "train": train,
                "vagon_type":vagon_type,
                "departure": departure,
                "arrival": arrival,
                "dep_normal": formatted_departure,
                "arr_normal": formatted_arrival,
                "depstation":depstation,
                "arrstation":arrstation,
                "price": price
            }
    # print(min_prices)
    return min_prices



app = Flask(__name__, static_url_path='/cheaptickets/static')

@app.route('/')
def index():
    return render_template('cheaptickets.html')

@app.route('/cheaptickets/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)

@app.route('/autocomplete', methods=['GET'])
def autocomplete():
    search = request.args.get('search')

    connection = pymysql.connect(**db_params)
    with connection.cursor() as cursor:
        sql = "SELECT cyrname, id FROM cities WHERE cyrname LIKE %s LIMIT 10"
        cursor.execute(sql, f"%{search}%")
        result = cursor.fetchall()

    connection.close()

    city_list = [{'label': city['cyrname'], 'value': city['id']} for city in result]
    return jsonify(city_list)

@app.route('/predata')
def predata():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    cityfrom = request.args.get('city1')
    cityto = request.args.get('city2')

    iso_start_date = datetime.strptime(start_date, "%d-%m-%Y")
    iso_end_date = datetime.strptime(end_date, "%d-%m-%Y")
    initial_train_data = get_train_data(iso_start_date, iso_end_date, cityfrom, cityto)
    return jsonify(initial_train_data)


@app.route('/search')
def search():
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    cityfrom = request.args.get('city1')
    cityto = request.args.get('city2')

    iso_start_date = datetime.strptime(start_date, "%d-%m-%Y")
    iso_end_date = datetime.strptime(end_date, "%d-%m-%Y")

    return Response(event_stream(iso_start_date, iso_end_date, cityfrom, cityto), content_type="text/event-stream")


def event_stream(start_date, end_date, cityfrom, cityto):
    total_days = (end_date - start_date).days+1
    min_prices_cal = {}
    current_date = start_date

    while current_date <= end_date:
        current_date_str = current_date.strftime("%Y-%m-%dT%H:%M:%S")
        data = rzdfind(current_date_str,cityfrom,cityto)
        min_prices_cal.update(getprice(data, current_date_str))
        current_date += timedelta(days=1)
        days_passed = (current_date - start_date).days
        progress = (days_passed / total_days) * 100
        progress_data = {
            'progress': progress,
            'data': min_prices_cal
        }

        yield f"data: {json.dumps(progress_data)}\n\n"

    save_tickets_to_db(min_prices_cal, cityfrom, cityto)




def get_train_data(datefrom, dateto, cityfrom, cityto):
    connection = pymysql.connect(**db_params)
    cursor = connection.cursor()

    cursor.execute('''
        select
    train_number as 'train',
    category as 'vagon_type',
    dep_date as 'departure',
    arr_date as 'arrival',
    dep_name as 'depstation',
    arr_name as 'arrstation',
    ticket_price as 'price'
        from ticket_info
        where
          actual = 1
          and dep_station = %s
          and arr_station = %s
          and date(dep_date) between %s and %s
    ''', (cityfrom, cityto, datefrom, dateto))

    train_data = cursor.fetchall()

    cursor.close()
    connection.close()

    json_data = {}
    for item in train_data:
        train = item['train']
        vagon_type = item['vagon_type']
        departure = item['departure'].strftime('%Y-%m-%dT%H:%M:%S')
        arrival = item['arrival'].strftime('%Y-%m-%dT%H:%M:%S')
        depstation = item['depstation']
        arrstation = item['arrstation']
        price = item['price']

        date = departure.split('T')[0]
        if date not in json_data:
            json_data[date] = {}

        json_data[date][vagon_type] = {
            'train': train,
            'vagon_type': vagon_type,
            'departure': departure,
            'arrival': arrival,
            'dep_normal': item['departure'].strftime('%d-%m-%Y %H:%M'),
            'arr_normal': item['arrival'].strftime('%d-%m-%Y %H:%M'),
            'depstation': depstation,
            'arrstation': arrstation,
            'price': price
        }
    print(json_data)
    return json_data

def save_tickets_to_db(min_prices_cal, departure_station_id, arrival_station_id):
    connection = pymysql.connect(**db_params)
    cursor = connection.cursor()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M")

    for date, ticket_data in min_prices_cal.items():
        for category, ticket_info in ticket_data.items():
            train_number = ticket_info.get('train',"none")
            departure_date = ticket_info.get('departure',"1970-01-01")
            arrival_date = ticket_info.get('arrival',"1970-01-01")
            depstation = ticket_info.get('depstation',0)
            arrstation = ticket_info.get('arrstation',0)
            price = ticket_info.get('price',0.0)

            # Помечаем все билеты для данной даты и категории как неактуальные
            cursor.execute(
                '''UPDATE ticket_info SET actual = 0 
                   WHERE category = %s
                   AND dep_station = %s
                   AND arr_station = %s
                   AND DATE(dep_date) = %s''',
                (category, departure_station_id, arrival_station_id, date))

            # Проверяем, существует ли уже запись с такими же параметрами
            cursor.execute(
                '''SELECT id, ticket_price FROM ticket_info
                    WHERE
                    train_number = %s
                    AND category = %s
                    AND dep_station = %s
                    AND arr_station = %s
                    AND dep_date = %s
                    AND arr_date = %s''',
                (train_number, category, departure_station_id, arrival_station_id, departure_date, arrival_date))
            result = cursor.fetchone()

            if result:
                # Если билет уже есть в базе, обновляем цену и актуальность
                ticket_id = result['id']

                cursor.execute(
                        '''UPDATE ticket_info SET ticket_price = %s, actual = 1
                            WHERE id = %s''',
                        (price, ticket_id))
            else:
                # Если билета нет в базе, добавляем новую запись
                cursor.execute(
                    '''INSERT INTO ticket_info (train_number, category, ticket_price, request_date, dep_station, arr_station, dep_date, arr_date, actual, dep_name, arr_name) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,  %s, %s)''',
                    (train_number, category, price, current_time, departure_station_id, arrival_station_id, departure_date, arrival_date, 1, depstation, arrstation))

    connection.commit()
    cursor.close()
    connection.close()


def serialize_subscription(row):
    return {
        "id": row["id"],
        "tg_id": row["tg_id"],
        "dep_station": row["dep_station"],
        "arr_station": row["arr_station"],
        "dep_name": row["dep_name"],
        "arr_name": row["arr_name"],
        "car_type": row["car_type"],
        "place_type": row["place_type"],
        "price_min": row["price_min"],
        "price_max": row["price_max"],
        "date_from": row["date_from"].strftime("%Y-%m-%d") if row["date_from"] else None,
        "date_to": row["date_to"].strftime("%Y-%m-%d") if row["date_to"] else None,
        "active": bool(row["active"]),
        "created_at": row["created_at"].strftime("%Y-%m-%d %H:%M") if row.get("created_at") else None,
        "updated_at": row["updated_at"].strftime("%Y-%m-%d %H:%M") if row.get("updated_at") else None,
    }


@app.route('/api/subscriptions', methods=['GET'])
def list_subscriptions():
    tg_id = normalize_tg_id(request.args.get('tg_id'))
    if not tg_id:
        return jsonify({"error": "tg_id required"}), 400

    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM subscriptions
                WHERE tg_id = %s AND active = 1
                ORDER BY id DESC
                """,
                (tg_id,),
            )
            rows = cursor.fetchall()
    finally:
        connection.close()

    return jsonify([serialize_subscription(row) for row in rows])


@app.route('/api/subscriptions', methods=['POST'])
def create_subscription():
    data = request.get_json(silent=True) or {}
    payload, errors = subscription_payload_from_request(data)
    if errors:
        return jsonify({"error": "validation", "details": errors}), 400

    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO subscriptions (
                    tg_id, dep_station, arr_station, dep_name, arr_name,
                    car_type, place_type, price_min, price_max, date_from, date_to, active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                """,
                (
                    payload["tg_id"],
                    payload["dep_station"],
                    payload["arr_station"],
                    payload.get("dep_name"),
                    payload.get("arr_name"),
                    payload["car_type"],
                    payload["place_type"],
                    payload["price_min"],
                    payload["price_max"],
                    payload["date_from"],
                    payload["date_to"],
                ),
            )
            new_id = cursor.lastrowid
        connection.commit()

        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM subscriptions WHERE id = %s", (new_id,))
            row = cursor.fetchone()
    finally:
        connection.close()

    return jsonify(serialize_subscription(row)), 201


@app.route('/api/subscriptions/<int:sub_id>', methods=['PUT'])
def update_subscription(sub_id):
    data = request.get_json(silent=True) or {}
    tg_id = normalize_tg_id(data.get("tg_id"))
    if not tg_id:
        return jsonify({"error": "tg_id required"}), 400

    payload, errors = subscription_payload_from_request(data, partial=False)
    if errors:
        return jsonify({"error": "validation", "details": errors}), 400

    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM subscriptions WHERE id = %s AND tg_id = %s AND active = 1",
                (sub_id, tg_id),
            )
            if not cursor.fetchone():
                return jsonify({"error": "not_found"}), 404

            cursor.execute(
                """
                UPDATE subscriptions SET
                    dep_station = %s,
                    arr_station = %s,
                    dep_name = %s,
                    arr_name = %s,
                    car_type = %s,
                    place_type = %s,
                    price_min = %s,
                    price_max = %s,
                    date_from = %s,
                    date_to = %s,
                    last_notify_signature = NULL
                WHERE id = %s AND tg_id = %s
                """,
                (
                    payload["dep_station"],
                    payload["arr_station"],
                    payload.get("dep_name"),
                    payload.get("arr_name"),
                    payload["car_type"],
                    payload["place_type"],
                    payload["price_min"],
                    payload["price_max"],
                    payload["date_from"],
                    payload["date_to"],
                    sub_id,
                    tg_id,
                ),
            )
        connection.commit()

        with connection.cursor() as cursor:
            cursor.execute("SELECT * FROM subscriptions WHERE id = %s", (sub_id,))
            row = cursor.fetchone()
    finally:
        connection.close()

    return jsonify(serialize_subscription(row))


@app.route('/api/subscriptions/<int:sub_id>', methods=['DELETE'])
def delete_subscription(sub_id):
    tg_id = normalize_tg_id(request.args.get('tg_id') or (request.get_json(silent=True) or {}).get('tg_id'))
    if not tg_id:
        return jsonify({"error": "tg_id required"}), 400

    connection = pymysql.connect(**db_params)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE subscriptions SET active = 0
                WHERE id = %s AND tg_id = %s AND active = 1
                """,
                (sub_id, tg_id),
            )
            if cursor.rowcount == 0:
                return jsonify({"error": "not_found"}), 404
        connection.commit()
    finally:
        connection.close()

    return jsonify({"ok": True})


if __name__ == '__main__':
    ensure_subscriptions_table()
    app.run(port=5070)



