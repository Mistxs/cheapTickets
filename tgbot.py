import html
import os

import requests

BOT_TOKEN = '6746194766:AAFs7xjLRf_n2sWkww3VDrVVQ1F0qkRyz6E'
# sing-box-inna на spica: mixed inbound → VLESS inna
BOT_PROXY = os.environ.get('BOT_PROXY', 'http://127.0.0.1:10808')


def _proxies():
    if not BOT_PROXY:
        return None
    return {'http': BOT_PROXY, 'https': BOT_PROXY}


def send_telegram_message(chat_id, message, token=None, parse_mode='HTML'):
    token = token or BOT_TOKEN
    chat_id = str(chat_id).strip()
    if chat_id and not chat_id.lstrip('-').isdigit() and not chat_id.startswith('@'):
        chat_id = '@' + chat_id
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'disable_web_page_preview': True,
        'parse_mode': parse_mode,
    }
    response = requests.post(url, data=payload, timeout=30, proxies=_proxies())
    return response


def notify_tickets(chat_id, info):
    return send_telegram_message(chat_id, info)
