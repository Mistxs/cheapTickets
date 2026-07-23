"""CheapTickets Telegram bot (aiogram 3): create/manage subscriptions."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

import tgbot

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cheaptickets-bot")

SITE_URL = "https://ct.spica.mistxs.ru"

BTN_NEW = "Новая подписка"
BTN_LIST = "Мои подписки"
BTN_SITE = "Сайт"
BTN_HELP = "Помощь"
BTN_CANCEL = "Отмена"

NOTIFY_PRESETS = {
    "08-23": ("08:00", "23:00", "08:00–23:00"),
    "09-21": ("09:00", "21:00", "09:00–21:00"),
    "10-22": ("10:00", "22:00", "10:00–22:00"),
    "16-11": ("16:00", "11:00", "16:00 → ночь → 11:00"),
    "24h": ("00:00", "00:00", "круглосуточно"),
}

router = Router()


class CreateSub(StatesGroup):
    dep_query = State()
    arr_query = State()
    dates = State()
    car = State()
    place = State()
    price_max = State()
    notify = State()
    confirm = State()


class EditPrice(StatesGroup):
    waiting = State()


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_NEW), KeyboardButton(text=BTN_LIST)],
            [KeyboardButton(text=BTN_SITE), KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
    )


def cancel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
    )


def require_username(message_or_user) -> str | None:
    user = getattr(message_or_user, "from_user", None) or message_or_user
    if not user or not user.username:
        return None
    return tgbot.normalize_username(user.username)


async def remember_user(message: Message) -> None:
    user = message.from_user
    if user and user.username:
        await asyncio.to_thread(tgbot.upsert_tg_user, user.username, user.id)


def short_sub_card(sub: dict, title: str | None = None) -> str:
    data = dict(sub)
    if title:
        # reuse formatter body without action title override
        text = tgbot.format_subscription_notice(data, action="created")
        lines = text.split("\n")
        lines[0] = f"<b>{title}</b>"
        return "\n".join(lines)
    return tgbot.format_subscription_notice(data, action="created")


def cities_keyboard(cities, prefix: str) -> InlineKeyboardMarkup:
    rows = []
    for city in cities:
        label = str(city["cyrname"])[:60]
        rows.append(
            [
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"{prefix}:{city['id']}",
                )
            ]
        )
    rows.append(
        [InlineKeyboardButton(text="Другой поиск", callback_data=f"{prefix}:retry")]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def car_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Плацкарт", callback_data="car:ПЛАЦ"),
                InlineKeyboardButton(text="Купе", callback_data="car:КУПЕ"),
            ],
            [
                InlineKeyboardButton(text="Сидячее", callback_data="car:СИД"),
                InlineKeyboardButton(text="Любой", callback_data="car:ANY"),
            ],
        ]
    )


def place_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Нижнее", callback_data="place:lower"),
                InlineKeyboardButton(text="Верхнее", callback_data="place:upper"),
            ],
            [InlineKeyboardButton(text="Любое", callback_data="place:any")],
        ]
    )


def notify_keyboard(prefix: str = "np") -> InlineKeyboardMarkup:
    rows = []
    for key, (_, _, label) in NOTIFY_PRESETS.items():
        rows.append(
            [InlineKeyboardButton(text=label, callback_data=f"{prefix}:{key}")]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def list_keyboard(subs: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"№{s['id']} {s.get('dep_name') or '?'} → {s.get('arr_name') or '?'}"[:64],
                callback_data=f"sub:{s['id']}",
            )
        ]
        for s in subs
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def detail_keyboard(sub_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Цена до", callback_data=f"ep:{sub_id}"),
                InlineKeyboardButton(text="Оповещения", callback_data=f"en:{sub_id}"),
            ],
            [
                InlineKeyboardButton(text="Удалить", callback_data=f"del:{sub_id}"),
                InlineKeyboardButton(text="К списку", callback_data="list"),
            ],
        ]
    )


def confirm_delete_keyboard(sub_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да, удалить", callback_data=f"delok:{sub_id}"),
                InlineKeyboardButton(text="Нет", callback_data=f"sub:{sub_id}"),
            ]
        ]
    )


def confirm_create_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Создать", callback_data="create:ok"),
                InlineKeyboardButton(text="Отмена", callback_data="create:cancel"),
            ]
        ]
    )


# --- Menu ---


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await remember_user(message)
    await state.clear()
    username = require_username(message)
    if not username:
        await message.answer(
            "Нужен публичный username в Telegram (Настройки → имя пользователя), "
            "иначе не смогу связать подписки.\n\n"
            f"Сайт: {SITE_URL}",
            reply_markup=main_keyboard(),
        )
        return
    await message.answer(
        f"Привет, @{username}!\n\n"
        "Здесь можно создать подписку на места или управлять уже существующими.\n"
        f"Сайт: {SITE_URL}",
        reply_markup=main_keyboard(),
    )


@router.message(Command("cancel"))
@router.message(F.text == BTN_CANCEL)
async def cmd_cancel(message: Message, state: FSMContext):
    await remember_user(message)
    await state.clear()
    await message.answer("Ок, отменил.", reply_markup=main_keyboard())


@router.message(F.text == BTN_HELP)
async def cmd_help(message: Message, state: FSMContext):
    await remember_user(message)
    await state.clear()
    await message.answer(
        "<b>Помощь</b>\n\n"
        "• <b>Новая подписка</b> — мастер: станции, даты, вагон, цена, окно оповещений\n"
        "• <b>Мои подписки</b> — список, смена цены/окна, удаление\n"
        f"• Сайт: {SITE_URL}\n\n"
        "Нужен username в Telegram и /start боту.",
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML,
    )


@router.message(F.text == BTN_SITE)
async def cmd_site(message: Message, state: FSMContext):
    await remember_user(message)
    await message.answer(f"Веб-версия: {SITE_URL}", reply_markup=main_keyboard())


# --- List / manage ---


@router.message(F.text == BTN_LIST)
@router.callback_query(F.data == "list")
async def show_list(event: Message | CallbackQuery, state: FSMContext):
    if isinstance(event, CallbackQuery):
        await event.answer()
        message = event.message
        user = event.from_user
    else:
        message = event
        user = event.from_user
        await remember_user(event)

    await state.clear()
    username = require_username(user)
    if not username:
        await message.answer(
            "Сначала укажите username в Telegram и нажмите /start.",
            reply_markup=main_keyboard(),
        )
        return

    subs = await asyncio.to_thread(tgbot.list_subscriptions_for_user, username)
    if not subs:
        await message.answer(
            "Активных подписок нет. Создайте через «Новая подписка» или на сайте.",
            reply_markup=main_keyboard(),
        )
        return

    await message.answer(
        f"Ваши подписки ({len(subs)}):",
        reply_markup=list_keyboard(subs),
    )


@router.callback_query(F.data.startswith("sub:"))
async def show_sub(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    username = require_username(callback.from_user)
    if not username:
        await callback.message.answer("Нужен username в Telegram.")
        return
    sub_id = int(callback.data.split(":")[1])
    sub = await asyncio.to_thread(tgbot.get_subscription_for_user, sub_id, username)
    if not sub:
        await callback.message.answer("Подписка не найдена.", reply_markup=main_keyboard())
        return
    await callback.message.answer(
        short_sub_card(sub, title="Подписка"),
        reply_markup=detail_keyboard(sub_id),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data.startswith("del:"))
async def ask_delete(callback: CallbackQuery):
    await callback.answer()
    sub_id = int(callback.data.split(":")[1])
    await callback.message.answer(
        f"Удалить подписку №{sub_id}?",
        reply_markup=confirm_delete_keyboard(sub_id),
    )


@router.callback_query(F.data.startswith("delok:"))
async def do_delete(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    username = require_username(callback.from_user)
    if not username:
        return
    sub_id = int(callback.data.split(":")[1])
    sub = await asyncio.to_thread(tgbot.get_subscription_for_user, sub_id, username)
    ok = await asyncio.to_thread(tgbot.soft_delete_subscription, sub_id, username)
    if ok and sub:
        await asyncio.to_thread(tgbot.notify_subscription_change, sub, "deleted")
        await callback.message.answer(
            f"Подписка №{sub_id} удалена.",
            reply_markup=main_keyboard(),
        )
    else:
        await callback.message.answer("Не удалось удалить.", reply_markup=main_keyboard())


@router.callback_query(F.data.startswith("ep:"))
async def edit_price_start(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    sub_id = int(callback.data.split(":")[1])
    await state.set_state(EditPrice.waiting)
    await state.update_data(edit_sub_id=sub_id)
    await callback.message.answer(
        "Введите новую максимальную цену (число, ₽):",
        reply_markup=cancel_keyboard(),
    )


@router.message(EditPrice.waiting)
async def edit_price_value(message: Message, state: FSMContext):
    await remember_user(message)
    username = require_username(message)
    if not username:
        await state.clear()
        await message.answer("Нужен username.", reply_markup=main_keyboard())
        return
    text = (message.text or "").strip().replace(" ", "").replace(",", ".")
    try:
        price = float(text)
        if price < 0:
            raise ValueError("negative")
    except ValueError:
        await message.answer("Нужно число, например 3500.")
        return

    data = await state.get_data()
    sub_id = data.get("edit_sub_id")
    sub = await asyncio.to_thread(
        tgbot.update_subscription_fields, sub_id, username, price_max=price
    )
    await state.clear()
    if not sub:
        await message.answer("Подписка не найдена.", reply_markup=main_keyboard())
        return
    await asyncio.to_thread(tgbot.notify_subscription_change, sub, "updated")
    await message.answer(
        short_sub_card(sub, title="Подписка обновлена"),
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data.startswith("en:"))
async def edit_notify_start(callback: CallbackQuery):
    await callback.answer()
    sub_id = int(callback.data.split(":")[1])
    await callback.message.answer(
        "Выберите окно оповещений:",
        reply_markup=notify_keyboard(prefix=f"enp:{sub_id}"),
    )


@router.callback_query(F.data.startswith("enp:"))
async def edit_notify_preset(callback: CallbackQuery):
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.message.answer("Некорректные данные.")
        return
    sub_id_s, key = parts[1], parts[2]
    preset = NOTIFY_PRESETS.get(key)
    if not preset:
        await callback.message.answer("Неизвестный пресет.")
        return
    username = require_username(callback.from_user)
    if not username:
        return
    nf, nt, _ = preset
    sub = await asyncio.to_thread(
        tgbot.update_subscription_fields,
        int(sub_id_s),
        username,
        notify_from=nf,
        notify_to=nt,
    )
    if not sub:
        await callback.message.answer("Подписка не найдена.", reply_markup=main_keyboard())
        return
    await asyncio.to_thread(tgbot.notify_subscription_change, sub, "updated")
    await callback.message.answer(
        short_sub_card(sub, title="Подписка обновлена"),
        reply_markup=detail_keyboard(sub["id"]),
        parse_mode=ParseMode.HTML,
    )


# --- Create wizard ---


@router.message(F.text == BTN_NEW)
async def create_start(message: Message, state: FSMContext):
    await remember_user(message)
    username = require_username(message)
    if not username:
        await message.answer(
            "Нужен публичный username в Telegram и /start.",
            reply_markup=main_keyboard(),
        )
        return
    await state.clear()
    await state.set_state(CreateSub.dep_query)
    await state.update_data(tg_id=username)
    await message.answer(
        "Откуда едем? Напишите город или станцию текстом (например: Саратов).",
        reply_markup=cancel_keyboard(),
    )


@router.message(CreateSub.dep_query)
async def create_dep_query(message: Message, state: FSMContext):
    await remember_user(message)
    cities = await asyncio.to_thread(tgbot.search_cities, message.text or "", 10)
    if not cities:
        await message.answer("Ничего не нашёл. Уточните название.")
        return
    await message.answer(
        "Выберите станцию отправления:",
        reply_markup=cities_keyboard(cities, "pick_dep"),
    )


@router.callback_query(F.data.startswith("pick_dep:"))
async def create_dep_pick(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    token = callback.data.split(":", 1)[1]
    if token == "retry":
        await state.set_state(CreateSub.dep_query)
        await callback.message.answer("Напишите станцию отправления ещё раз.")
        return
    city = await asyncio.to_thread(tgbot.get_city_by_id, int(token))
    if not city:
        await callback.message.answer("Станция не найдена, попробуйте ещё раз.")
        return
    await state.update_data(dep_station=city["id"], dep_name=city["cyrname"])
    await state.set_state(CreateSub.arr_query)
    await callback.message.answer(
        f"Откуда: <b>{tgbot._escape_html(city['cyrname'])}</b>\n\n"
        "Куда едем? Напишите город или станцию.",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )


@router.message(CreateSub.arr_query)
async def create_arr_query(message: Message, state: FSMContext):
    await remember_user(message)
    cities = await asyncio.to_thread(tgbot.search_cities, message.text or "", 10)
    if not cities:
        await message.answer("Ничего не нашёл. Уточните название.")
        return
    await message.answer(
        "Выберите станцию прибытия:",
        reply_markup=cities_keyboard(cities, "pick_arr"),
    )


@router.callback_query(F.data.startswith("pick_arr:"))
async def create_arr_pick(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    token = callback.data.split(":", 1)[1]
    if token == "retry":
        await state.set_state(CreateSub.arr_query)
        await callback.message.answer("Напишите станцию прибытия ещё раз.")
        return
    city = await asyncio.to_thread(tgbot.get_city_by_id, int(token))
    if not city:
        await callback.message.answer("Станция не найдена, попробуйте ещё раз.")
        return
    await state.update_data(arr_station=city["id"], arr_name=city["cyrname"])
    await state.set_state(CreateSub.dates)
    await callback.message.answer(
        f"Куда: <b>{tgbot._escape_html(city['cyrname'])}</b>\n\n"
        "Диапазон дат одним сообщением:\n"
        "<code>ДД-ММ-ГГГГ — ДД-ММ-ГГГГ</code>\n"
        "Например: <code>01-08-2026 — 15-08-2026</code>",
        parse_mode=ParseMode.HTML,
        reply_markup=cancel_keyboard(),
    )


@router.message(CreateSub.dates)
async def create_dates(message: Message, state: FSMContext):
    await remember_user(message)
    try:
        date_from, date_to = tgbot.parse_date_range_text(message.text or "")
        if date_from > date_to:
            raise ValueError("range")
    except ValueError:
        await message.answer(
            "Не разобрал даты. Формат: 01-08-2026 — 15-08-2026"
        )
        return
    await state.update_data(date_from=date_from, date_to=date_to)
    await state.set_state(CreateSub.car)
    await message.answer("Тип вагона:", reply_markup=car_keyboard())


@router.callback_query(F.data.startswith("car:"), CreateSub.car)
async def create_car(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    car = callback.data.split(":", 1)[1]
    await state.update_data(car_type=car)
    if car == "СИД":
        await state.update_data(place_type="any")
        await state.set_state(CreateSub.price_max)
        await callback.message.answer(
            "Максимальная цена (₽), число:",
            reply_markup=cancel_keyboard(),
        )
        return
    await state.set_state(CreateSub.place)
    await callback.message.answer("Тип места:", reply_markup=place_keyboard())


@router.callback_query(F.data.startswith("place:"), CreateSub.place)
async def create_place(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    place = callback.data.split(":", 1)[1]
    await state.update_data(place_type=place)
    await state.set_state(CreateSub.price_max)
    await callback.message.answer(
        "Максимальная цена (₽), число:",
        reply_markup=cancel_keyboard(),
    )


@router.message(CreateSub.price_max)
async def create_price(message: Message, state: FSMContext):
    await remember_user(message)
    text = (message.text or "").strip().replace(" ", "").replace(",", ".")
    try:
        price = float(text)
        if price < 0:
            raise ValueError("negative")
    except ValueError:
        await message.answer("Нужно число, например 3500.")
        return
    await state.update_data(price_min=0, price_max=price)
    await state.set_state(CreateSub.notify)
    await message.answer(
        "Окно оповещений (когда искать и писать):",
        reply_markup=notify_keyboard("cnp"),
    )


@router.callback_query(F.data.startswith("cnp:"), CreateSub.notify)
async def create_notify(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    key = callback.data.split(":", 1)[1]
    preset = NOTIFY_PRESETS.get(key)
    if not preset:
        await callback.message.answer("Неизвестный пресет.")
        return
    nf, nt, _ = preset
    await state.update_data(notify_from=nf, notify_to=nt)
    data = await state.get_data()
    preview = {
        "id": None,
        "tg_id": data.get("tg_id"),
        "dep_name": data.get("dep_name"),
        "arr_name": data.get("arr_name"),
        "car_type": data.get("car_type"),
        "place_type": data.get("place_type"),
        "price_min": data.get("price_min", 0),
        "price_max": data.get("price_max"),
        "date_from": data.get("date_from").isoformat()
        if hasattr(data.get("date_from"), "isoformat")
        else data.get("date_from"),
        "date_to": data.get("date_to").isoformat()
        if hasattr(data.get("date_to"), "isoformat")
        else data.get("date_to"),
        "notify_from": nf,
        "notify_to": nt,
    }
    await state.set_state(CreateSub.confirm)
    await callback.message.answer(
        short_sub_card(preview, title="Проверьте подписку"),
        reply_markup=confirm_create_keyboard(),
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "create:cancel", CreateSub.confirm)
async def create_abort(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.clear()
    await callback.message.answer("Создание отменено.", reply_markup=main_keyboard())


@router.callback_query(F.data == "create:ok", CreateSub.confirm)
async def create_commit(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    data = await state.get_data()
    username = data.get("tg_id") or require_username(callback.from_user)
    if not username:
        await state.clear()
        await callback.message.answer("Нужен username.", reply_markup=main_keyboard())
        return

    payload = {
        "tg_id": username,
        "dep_station": data["dep_station"],
        "arr_station": data["arr_station"],
        "dep_name": data["dep_name"],
        "arr_name": data["arr_name"],
        "car_type": data["car_type"],
        "place_type": data["place_type"],
        "price_min": data.get("price_min", 0),
        "price_max": data["price_max"],
        "date_from": data["date_from"],
        "date_to": data["date_to"],
        "notify_from": data.get("notify_from", "08:00"),
        "notify_to": data.get("notify_to", "23:00"),
    }
    try:
        sub = await asyncio.to_thread(tgbot.create_subscription_record, payload)
    except Exception as exc:
        log.exception("create failed")
        await callback.message.answer(
            f"Ошибка сохранения: {exc}",
            reply_markup=main_keyboard(),
        )
        await state.clear()
        return

    await state.clear()
    await asyncio.to_thread(tgbot.notify_subscription_change, sub, "created")
    await callback.message.answer(
        short_sub_card(sub, title="Подписка создана"),
        reply_markup=main_keyboard(),
        parse_mode=ParseMode.HTML,
    )


@router.message(StateFilter(None))
async def fallback(message: Message):
    await remember_user(message)
    await message.answer(
        "Выберите действие в меню ниже.",
        reply_markup=main_keyboard(),
    )


async def main() -> None:
    tgbot.ensure_tg_users_table()

    session = None
    if tgbot.BOT_PROXY:
        # aiogram 3 AiohttpSession accepts proxy=
        session = AiohttpSession(proxy=tgbot.BOT_PROXY)

    bot = Bot(token=tgbot.BOT_TOKEN, session=session)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    log.info("CheapTickets bot starting (proxy=%s)", bool(tgbot.BOT_PROXY))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
