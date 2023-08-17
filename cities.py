from flask import Flask, render_template, request, jsonify
import pymysql

app = Flask(__name__)

# Параметры подключения к базе данных MySQL
db_params = {
    'host': 'localhost',
    'user': 'root',
    'password': 'Ose7vgt5',
    'db': 'rzd',
    'cursorclass': pymysql.cursors.DictCursor
}


@app.route('/')
def index():
    return render_template('cities.html')


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

@app.route('/submit', methods=['POST'])
def submit():
    city1_id = request.form.get('city1-id')  # Извлекаем значение из атрибута data-city-id
    city2_id = request.form.get('city2-id')  # Извлекаем значение из атрибута data-city-id

    print(city1_id, city2_id)

    return "City 1 ID: {}<br>City 2 ID: {}".format(city1_id, city2_id)



if __name__ == '__main__':
    app.run(port=5080)
