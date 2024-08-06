import requests

def send_telegram_message(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message
    }
    response = requests.post(url, data=payload)
    return response

# Ваш основной код
def check_tickets(info):
        token = '6746194766:AAFs7xjLRf_n2sWkww3VDrVVQ1F0qkRyz6E'
        chat_id = '6225487468'
        message = f"ЕСТЬ БИЛЕТЫ - {info}"
        send_telegram_message(token, chat_id, message)


