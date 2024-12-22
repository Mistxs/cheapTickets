import logging

import pymysql
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command
from config import db_params


# Укажите здесь ваш токен
API_TOKEN = '6746194766:AAFs7xjLRf_n2sWkww3VDrVVQ1F0qkRyz6E'

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Создаем экземпляр бота
bot = Bot(token=API_TOKEN)

# Создаем диспетчер
dp = Dispatcher()

# Список для хранения chat_id
chat_ids = set()


def addchat(chat_ids):
    conn = pymysql.connect(**db_params)
    try:
        with conn.cursor() as cursor:
            query = f'''insert into tgchatids (chatids) VALUES ({chat_ids});'''
            cursor.execute(query)
        conn.commit()
    finally:
        conn.close()


# Хэндлер для команды /start
@dp.message(Command("start"))
async def start_handler(message: Message):
    chat_ids.add(message.chat.id)
    addchat(message.chat.id)
    await message.reply("Йоу! Теперь я буду тебе отправлять сообщения о билетах, как только они появятся. Твоя задача - быстро залететь на ржд и оформить его")



# Основной запуск бота
if __name__ == "__main__":
    dp.run_polling(bot)
