import logging
import requests
import time

from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

API_TOKEN = "8747779948:AAGXTBuDOmhM_X7dPBMRGUFCiL5Qj2_1wv0"
CRYPTO_TOKEN = "569144:AAs82ABvMXw8uTlYYfIrZOMWZA5C7bYhfdr"
ADMIN_ID = 105635005
BOT_USERNAME = "token"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN, parse_mode="HTML")
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# ================== ДАННЫЕ ==================
users = {}
products = {}
items = {}
payments = {}

stats = {
    "total_earned": 0,
    "total_sales": 0,
    "products": {}
}

# ================== FSM ==================
class AddProduct(StatesGroup):
    name = State()
    price = State()


class AddItem(StatesGroup):
    pid = State()
    data = State()

# ================== ERROR ==================
@dp.errors_handler()
async def errors_handler(update, exception):
    print("Ошибка:", exception)
    return True

# ================== MENU ==================
def main_menu(user_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🛒 Товары", callback_data="shop"),
        types.InlineKeyboardButton("💰 Баланс", callback_data="balance")
    )
    kb.add(types.InlineKeyboardButton("👥 Рефералка", callback_data="ref"))

    if user_id == ADMIN_ID:
        kb.add(types.InlineKeyboardButton("👑 Админ", callback_data="admin"))

    return kb

# ================== START ==================
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id

    if user_id not in users:
        users[user_id] = {"balance": 0, "ref": None}

    link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"

    await message.answer(
        f"🔥 Добро пожаловать\n\n👥 Реф ссылка:\n{link}",
        reply_markup=main_menu(user_id)
    )

# ================== SHOP ==================
@dp.callback_query_handler(lambda c: c.data == "shop")
async def shop(callback: types.CallbackQuery):
    kb = types.InlineKeyboardMarkup()

    for pid, p in products.items():
        kb.add(types.InlineKeyboardButton(
            f"{p['name']} | {p['price']} USDT",
            callback_data=f"product_{pid}"
        ))

    kb.add(types.InlineKeyboardButton("⬅ Назад", callback_data="menu"))

    await callback.message.edit_text("🛒 Товары:", reply_markup=kb)

# ================== PRODUCT ==================
@dp.callback_query_handler(lambda c: c.data.startswith("product_"))
async def product(callback: types.CallbackQuery):
    pid = int(callback.data.split("_")[1])
    p = products.get(pid)

    if not p:
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("💳 Купить", callback_data=f"buy_{pid}"))
    kb.add(types.InlineKeyboardButton("⬅ Назад", callback_data="shop"))

    await callback.message.edit_text(
        f"{p['name']}\n💰 {p['price']} USDT",
        reply_markup=kb
    )

# ================== BUY ==================
@dp.callback_query_handler(lambda c: c.data.startswith("buy_"))
async def buy(callback: types.CallbackQuery):
    try:
        pid = int(callback.data.split("_")[1])
        p = products.get(pid)

        if not p:
            return

        r = requests.post(
            "https://pay.crypt.bot/api/createCheck",
            headers={"Crypto-Pay-API-Token": CRYPTO_TOKEN},
            json={"asset": "USDT", "amount": p["price"]},
            timeout=10
        ).json()

        if not r.get("ok"):
            await callback.message.edit_text("❌ Ошибка оплаты")
            return

        check_id = r["result"]["check_id"]
        url = r["result"]["bot_check_url"]

        payments[check_id] = {
            "user_id": callback.from_user.id,
            "product_id": pid,
            "status": "pending"
        }

        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("💳 Оплатить", url=url))
        kb.add(types.InlineKeyboardButton("✅ Проверить", callback_data=f"check_{check_id}"))

        await callback.message.edit_text("💳 Оплата", reply_markup=kb)

    except Exception as e:
        print("Ошибка buy:", e)

# ================== CHECK ==================
@dp.callback_query_handler(lambda c: c.data.startswith("check_"))
async def check(callback: types.CallbackQuery):
    try:
        check_id = callback.data.split("_")[1]
        pay = payments.get(check_id)

        if not pay or pay["status"] == "paid":
            return

        r = requests.get(
            f"https://pay.crypt.bot/api/getChecks?check_ids={check_id}",
            headers={"Crypto-Pay-API-Token": CRYPTO_TOKEN},
            timeout=10
        ).json()

        if not r.get("ok"):
            return

        if r["result"]["items"][0]["status"] != "paid":
            await callback.answer("❌ Не оплачено", show_alert=True)
            return

        user_id = pay["user_id"]
        pid = pay["product_id"]
        price = products[pid]["price"]

        users[user_id]["balance"] += price

        stats["total_earned"] += price
        stats["total_sales"] += 1

        if pid not in stats["products"]:
            stats["products"][pid] = {"name": products[pid]["name"], "count": 0, "earned": 0}

        stats["products"][pid]["count"] += 1
        stats["products"][pid]["earned"] += price

        item = None
        if items.get(pid):
            item = items[pid].pop(0)

        pay["status"] = "paid"

        text = f"✅ Оплата прошла\n💰 Начислено: {price}"

        if item:
            text += f"\n\n📦 Товар:\n{item}"

        await callback.message.edit_text(text)

    except Exception as e:
        print("Ошибка check:", e)

# ================== ADMIN ==================
@dp.callback_query_handler(lambda c: c.data == "admin")
async def admin(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("➕ Добавить товар", callback_data="add_product"))
    kb.add(types.InlineKeyboardButton("📦 Добавить аккаунты", callback_data="add_item"))
    kb.add(types.InlineKeyboardButton("📊 Статистика", callback_data="stats"))
    kb.add(types.InlineKeyboardButton("⬅ Назад", callback_data="menu"))

    await callback.message.edit_text("👑 Админ панель", reply_markup=kb)

# ================== ADD PRODUCT ==================
@dp.callback_query_handler(lambda c: c.data == "add_product")
async def add_product_start(callback: types.CallbackQuery):
    await callback.message.answer("Введите название товара:")
    await AddProduct.name.set()

@dp.message_handler(state=AddProduct.name)
async def add_product_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Введите цену:")
    await AddProduct.price.set()

@dp.message_handler(state=AddProduct.price)
async def add_product_price(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pid = max(products.keys(), default=0) + 1

    products[pid] = {
        "name": data["name"],
        "price": float(message.text)
    }

    items[pid] = []

    await message.answer(f"✅ Товар добавлен (ID: {pid})")
    await state.finish()

# ================== ADD ITEM ==================
@dp.callback_query_handler(lambda c: c.data == "add_item")
async def add_item_start(callback: types.CallbackQuery):
    await callback.message.answer("Введите ID товара:")
    await AddItem.pid.set()

@dp.message_handler(state=AddItem.pid)
async def add_item_pid(message: types.Message, state: FSMContext):
    pid = int(message.text)

    if pid not in products:
        await message.answer("❌ Товар не найден")
        return

    await state.update_data(pid=pid)
    await message.answer("Введи данные (каждый с новой строки):")
    await AddItem.data.set()

@dp.message_handler(state=AddItem.data)
async def add_item_data(message: types.Message, state: FSMContext):
    data = await state.get_data()
    pid = data["pid"]

    items[pid].extend(message.text.split("\n"))

    await message.answer("✅ Добавлено")
    await state.finish()

# ================== STATS ==================
@dp.callback_query_handler(lambda c: c.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    text = f"📊 Статистика\n\n💰 Заработано: {stats['total_earned']}\n📦 Продаж: {stats['total_sales']}\n\n"

    for pid, d in stats["products"].items():
        text += f"{d['name']} | {d['count']} | {d['earned']}\n"

    await callback.message.edit_text(text)

# ================== BALANCE ==================
@dp.callback_query_handler(lambda c: c.data == "balance")
async def balance(callback: types.CallbackQuery):
    bal = users.get(callback.from_user.id, {}).get("balance", 0)
    await callback.message.edit_text(f"💰 Баланс: {bal}", reply_markup=main_menu(callback.from_user.id))

# ================== REF ==================
@dp.callback_query_handler(lambda c: c.data == "ref")
async def ref(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"
    await callback.message.edit_text(link, reply_markup=main_menu(user_id))

# ================== MENU ==================
@dp.callback_query_handler(lambda c: c.data == "menu")
async def menu(callback: types.CallbackQuery):
    await callback.message.edit_text("🏠 Меню", reply_markup=main_menu(callback.from_user.id))

# ================== ANTI-CRASH ==================
if __name__ == "__main__":
    while True:
        try:
            print("🚀 Запуск бота...")
            executor.start_polling(dp, skip_updates=True)
        except Exception as e:
            print("❌ Краш:", e)
            time.sleep(5)