import asyncio
import logging
import re
import os
import threading
from telethon import TelegramClient, events
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ==== Конфиг ====
API_ID = 26616230
API_HASH = "895c0f50a04747d3342b0b9ee83e19cd"
BOT_TOKEN = "8481160193:AAGbm3d_14WPqtb514yanSxNZsYJ30DCFdc"
USER_ID = 8139807344
SESSION_FILE = "session"

KEYWORDS = [
    "розыгрыш", "конкурс", "giveaway", "приз", "подарок",
    "выиграть", "участвуй", "раздача"
]

bot = telebot.TeleBot(BOT_TOKEN)

# ==== Глобальное состояние ====
monitoring = False
processed: set = set()
auth_data: dict = {}

# Единственный event loop — живёт в отдельном потоке навсегда
loop = asyncio.new_event_loop()

# Клиент создаётся ОДИН РАЗ с явной привязкой к loop
client = TelegramClient(SESSION_FILE, API_ID, API_HASH, loop=loop)

# Future для передачи кода из бота в корутину авторизации
code_future: asyncio.Future = None


# ==== Запуск фонового потока ====
def run_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=run_loop, daemon=True).start()


# ==== Утилиты ====
def send(text: str, markup=None):
    try:
        bot.send_message(USER_ID, text, reply_markup=markup)
    except Exception as e:
        log.error("send_message error: %s", e)


def run_async(coro):
    asyncio.run_coroutine_threadsafe(coro, loop)


def main_markup():
    m = InlineKeyboardMarkup()
    m.row(InlineKeyboardButton("📱 Войти", callback_data="login"))
    m.row(InlineKeyboardButton("📊 Статистика", callback_data="stats"))
    m.row(InlineKeyboardButton("🔄 Сброс сессии", callback_data="reset"))
    return m


# ==== Команды бота ====
@bot.message_handler(commands=["start"])
def cmd_start(message):
    if message.chat.id != USER_ID:
        return
    bot.send_message(
        message.chat.id,
        "🔍 Бот поиска розыгрышей\n\nНажми «Войти» и введи номер телефона.",
        reply_markup=main_markup(),
    )


@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    global monitoring, processed
    cid = call.message.chat.id
    mid = call.message.message_id

    if call.data == "login":
        auth_data.clear()
        auth_data["step"] = "phone"
        bot.edit_message_text("📱 Введи номер телефона (например: 89001234567):", cid, mid)

    elif call.data == "stats":
        status = "✅ Активен" if monitoring else "❌ Не активен"
        bot.edit_message_text(
            f"📊 Статистика:\nСтатус: {status}\nНайдено розыгрышей: {len(processed)}",
            cid, mid,
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("◀️ Назад", callback_data="back")
            )
        )

    elif call.data == "reset":
        auth_data.clear()
        monitoring = False
        processed = set()

        async def _reset():
            if client.is_connected():
                await client.disconnect()
            for ext in [".session", ".session-journal"]:
                try:
                    os.remove(SESSION_FILE + ext)
                except FileNotFoundError:
                    pass
        run_async(_reset())

        bot.edit_message_text(
            "✅ Сессия сброшена. Нажми «Войти» для повторного входа.",
            cid, mid,
            reply_markup=InlineKeyboardMarkup().add(
                InlineKeyboardButton("📱 Войти", callback_data="login")
            )
        )

    elif call.data == "back":
        bot.edit_message_text("🔍 Бот поиска розыгрышей", cid, mid, reply_markup=main_markup())


@bot.message_handler(func=lambda m: True)
def text_handler(message):
    if message.chat.id != USER_ID:
        return

    step = auth_data.get("step")

    if step == "phone":
        phone = re.sub(r"\D", "", message.text.strip())
        if len(phone) == 11:
            auth_data["phone"] = "+" + phone
            auth_data["step"] = "code"
            bot.reply_to(message, "✅ Номер принят. Отправляю запрос кода...")
            run_async(request_code(auth_data["phone"]))
        else:
            bot.reply_to(message, "❌ Неправильный номер. Пример: 89001234567")

    elif step == "code":
        code = message.text.strip()
        auth_data["step"] = "done"
        bot.reply_to(message, "✅ Код принят. Выполняю вход...")
        # Передаём код в ожидающую корутину через Future — БЕЗ пересоздания loop
        if code_future and not code_future.done():
            loop.call_soon_threadsafe(code_future.set_result, code)
        else:
            bot.send_message(USER_ID, "❌ Сессия ввода кода устарела. Начни заново через /start")


# ==== Авторизация — вся логика в одной корутине в одном loop ====
async def request_code(phone: str):
    """
    Ключевое исправление: send_code_request и sign_in выполняются
    в одной и той же корутине, в одном loop, без смены контекста.
    Код передаётся через asyncio.Future, а не через внешние переменные.
    """
    global code_future, monitoring

    try:
        if not client.is_connected():
            await client.connect()

        if await client.is_user_authorized():
            send("✅ Уже авторизован! Запускаю мониторинг...")
            monitoring = True
            await start_monitoring()
            return

        await client.send_code_request(phone)
        send("📨 Код отправлен в Telegram. Введи его сюда (у тебя 2 минуты):")

        # Создаём Future в текущем loop и ждём код от пользователя
        code_future = loop.create_future()
        try:
            code = await asyncio.wait_for(code_future, timeout=120)
        except asyncio.TimeoutError:
            send("❌ Время ввода кода истекло (2 минуты). Начни заново через /start")
            auth_data.clear()
            return

        # sign_in вызывается сразу после получения кода — код не успевает протухнуть
        await client.sign_in(phone=phone, code=code)
        send("✅ Вход выполнен! Начинаю мониторинг розыгрышей...", markup=main_markup())
        monitoring = True
        await start_monitoring()

    except Exception as e:
        log.error("Auth error: %s", e)
        send(f"❌ Ошибка авторизации: {e}")
        auth_data.clear()


# ==== Мониторинг ====
async def start_monitoring():
    @client.on(events.NewMessage())
    async def handler(event):
        if not monitoring or not event.is_channel:
            return

        try:
            msg_id = event.message.id
            if msg_id in processed:
                return

            text = event.message.message or ""
            if not any(k in text.lower() for k in KEYWORDS):
                return
            if not event.message.reply_markup:
                return

            processed.add(msg_id)
            chat = await event.get_chat()

            try:
                if getattr(chat, "username", None):
                    url = f"https://t.me/{chat.username}/{event.id}"
                else:
                    cid = str(event.chat_id).replace("-100", "")
                    url = f"https://t.me/c/{cid}/{event.id}"
            except Exception:
                url = None

            markup = None
            if url:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("👉 Перейти к розыгрышу", url=url))

            preview = text[:300] + ("..." if len(text) > 300 else "")
            title = getattr(chat, "title", "Неизвестный канал")
            send(f"🔔 РОЗЫГРЫШ!\n\n📢 {title}\n\n{preview}", markup=markup)

        except Exception as e:
            log.error("Handler error: %s", e)

    await client.run_until_disconnected()


# ==== Запуск ====
if __name__ == "__main__":
    log.info("🚀 Бот запущен")

    # Если сессия уже есть — автоматически восстанавливаем
    async def auto_connect():
        global monitoring
        try:
            await client.connect()
            if await client.is_user_authorized():
                log.info("Сессия найдена, запускаю мониторинг автоматически")
                send("✅ Сессия восстановлена. Мониторинг активен!", markup=main_markup())
                monitoring = True
                await start_monitoring()
        except Exception as e:
            log.warning("Auto-connect error: %s", e)

    run_async(auto_connect())
    bot.infinity_polling()
