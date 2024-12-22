import pymysql
import requests
from config import db_params


def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message
    }
    response = requests.post(url, data=payload)
    return response


def getchatids():
    conn = pymysql.connect(**db_params)
    try:
        with conn.cursor() as cursor:
            query = f'''select chatids from tgchatids;'''
            cursor.execute(query)
        conn.commit()
        result = cursor.fetchall()
        return result
    finally:
        conn.close()

# Ваш основной код
def check_tickets(info):
        token = '6746194766:AAFs7xjLRf_n2sWkww3VDrVVQ1F0qkRyz6E'
        chat_ids = getchatids()
        for chat_id in chat_ids:
            message = f"ЕСТЬ БИЛЕТЫ - {info}"
            send_telegram_message(token, chat_id, message)

