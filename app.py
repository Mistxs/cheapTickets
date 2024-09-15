import json
import time
from datetime import datetime, timedelta

import pymysql
import requests
from flask import Flask, render_template, request, jsonify, Response, send_from_directory
from apscheduler.schedulers.blocking import BlockingScheduler

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




# Параметры подключения к базе данных MySQL
db_params = {
        'host': 'localhost',
        'user': 'root',
        'password': 'Ose7vgt5!',
        'db': 'rzd',
        'cursorclass': pymysql.cursors.DictCursor
}

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


if __name__ == '__main__':
    app.run(port=5070)



