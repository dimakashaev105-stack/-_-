import asyncio
import logging
import re
from datetime import datetime, timedelta
from telethon import TelegramClient, events
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ==== Логирование ====
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ==== Конфиг ====
# ⚠️ ВАЖНО: СРОЧНО ЗАМЕНИТЕ ТОКЕН! Он скомпрометирован
api_id = 26616230
api_hash = "895c0f50a04747d3342b0b9ee83e19cd"
session_name = "monitor_session"

# ⚠️ НЕМЕДЛЕННО ЗАМЕНИТЕ ЭТОТ ТОКЕН через @BotFather!
# Старый токен: 8481160193:AAGbm3d_14WPqtb514yanSxNZsYJ30DCFdc
BOT_TOKEN = "8481160193:AAGbm3d_14WPqtb514yanSxNZsYJ30DCFdc"  # ВСТАВЬТЕ НОВЫЙ ТОКЕН!
USER_ID = 8139807344  # Ваш ID

client = TelegramClient(session_name, api_id, api_hash)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Множество для отслеживания обработанных сообщений
processed_messages = set()

# ==== Функция определения даты ====
def extract_date_from_text(text: str):
    """Пытается определить дату окончания розыгрыша из текста."""
    today = datetime.now()
    text_lower = text.lower()

    # Простые случаи
    if "послезавтра" in text_lower:
        return today + timedelta(days=2), "послезавтра"
    if "завтра" in text_lower:
        return today + timedelta(days=1), "завтра"
    if "сегодня" in text_lower:
        return today, "сегодня"

    # Через X дней
    match = re.search(r"через\s+(\d+)\s*(день|дня|дней)", text_lower)
    if match:
        days = int(match.group(1))
        return today + timedelta(days=days), f"через {days} дн."

    # До конкретной даты
    months = {
        "января": 1, "февраля": 2, "марта": 3, "апреля": 4,
        "мая": 5, "июня": 6, "июля": 7, "августа": 8,
        "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12
    }
    
    for month_name, month_num in months.items():
        pattern = fr"до\s+(\d{{1,2}})\s+{month_name}"
        match = re.search(pattern, text_lower)
        if match:
            day = int(match.group(1))
            year = today.year
            if month_num < today.month or (month_num == today.month and day < today.day):
                year += 1
            try:
                date = datetime(year, month_num, day)
                return date, date.strftime("%d.%m.%Y")
            except:
                pass

    # Дни недели
    weekdays = {
        "понедельник": 0, "вторник": 1, "среда": 2,
        "четверг": 3, "пятница": 4, "суббота": 5, "воскресенье": 6
    }
    
    for day_name, day_num in weekdays.items():
        if day_name in text_lower:
            today_num = today.weekday()
            days_ahead = day_num - today_num
            if days_ahead <= 0:
                days_ahead += 7
            date = today + timedelta(days=days_ahead)
            return date, day_name

    return None, None

def format_date(date):
    """Форматирует дату для вывода."""
    if not date:
        return None
    
    today = datetime.now()
    days_left = (date.date() - today.date()).days
    
    if days_left > 0:
        return f"{date.strftime('%d.%m.%Y')} (через {days_left} дн.)"
    elif days_left == 0:
        return f"{date.strftime('%d.%m.%Y')} (сегодня)"
    else:
        return f"{date.strftime('%d.%m.%Y')} (просрочено)"

# ==== Основной обработчик Telethon ====
@client.on(events.NewMessage())
async def handler(event):
    global processed_messages
    
    if not event.is_channel or not event.message:
        return

    try:
        chat = await event.get_chat()
        chat_title = getattr(chat, 'title', str(event.chat_id))
        logger.info(f"📨 Новое сообщение в канале: {chat_title}")
    except Exception as e:
        logger.warning(f"Ошибка получения информации о чате: {e}")
        return

    # Получаем текст и ID сообщения
    text = event.message.message or ""
    message_id = event.message.id
    
    # Проверяем на дубликаты
    if message_id in processed_messages:
        return
    
    text_lower = text.lower()

    # Ключевые слова для поиска
    keywords = ["розыгрыш", "разыгрыва", "участву", "конкурс", "приз", "подарок"]
    excluded = ["чтобы писать в чат", "завершен", "итоги", "победитель"]
    
    # Проверяем наличие кнопок
    has_buttons = event.message.reply_markup is not None
    
    # Проверяем условия
    has_keyword = any(word in text_lower for word in keywords)
    has_excluded = any(bad in text_lower for bad in excluded)
    
    if has_keyword and not has_excluded and has_buttons:
        # Добавляем в обработанные
        processed_messages.add(message_id)
        if len(processed_messages) > 1000:
            processed_messages.clear()
        
        # Определяем дату
        date_guess, date_text = extract_date_from_text(text)
        date_str = format_date(date_guess) if date_guess else None
        
        # Формируем ссылку на пост
        post_url = None
        try:
            entity = await client.get_entity(event.chat_id)
            if hasattr(entity, 'username') and entity.username:
                post_url = f"https://t.me/{entity.username}/{event.id}"
            else:
                chat_id = str(event.chat_id).replace('-100', '')
                post_url = f"https://t.me/c/{chat_id}/{event.id}"
        except Exception as e:
            logger.error(f"Ошибка создания ссылки: {e}")
        
        # Создаем клавиатуру
        keyboard = None
        if post_url:
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🎉 Перейти к розыгрышу", url=post_url)]
                ]
            )
        
        # Формируем текст сообщения
        msg_text = (
            f"🔔 <b>НАЙДЕН РОЗЫГРЫШ!</b>\n\n"
            f"📢 Канал: <b>{chat_title}</b>\n"
            f"📝 Текст:\n<code>{text[:500]}...</code>\n"
        )
        
        if date_str:
            msg_text += f"\n⏰ Окончание: <b>{date_str}</b>"
        
        if post_url:
            msg_text += f"\n\n🔗 <a href='{post_url}'>Ссылка на пост</a>"
        
        # Отправляем уведомление
        try:
            await bot.send_message(
                USER_ID,
                msg_text,
                reply_markup=keyboard,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
            logger.info(f"✅ Уведомление отправлено: {post_url}")
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")

# ==== Команда /start ====
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await message.answer(
        "✅ <b>Бот мониторинга розыгрышей запущен!</b>\n\n"
        "Я буду отслеживать новые посты в каналах и присылать уведомления "
        "о найденных розыгрышах.\n\n"
        "📊 Статистика:\n"
        f"• Обработано сообщений: {len(processed_messages)}",
        parse_mode=ParseMode.HTML
    )

# ==== Команда /stats ====
@dp.message(Command("stats"))
async def stats_cmd(message: types.Message):
    await message.answer(
        f"📊 <b>Статистика работы:</b>\n\n"
        f"• Найдено розыгрышей: {len(processed_messages)}\n"
        f"• Бот активен",
        parse_mode=ParseMode.HTML
    )

# ==== Основной запуск ====
async def main():
    # Подключаемся
    await client.start()
    logger.info("✅ Telethon клиент запущен")
    logger.info(f"👤 Мониторинг для пользователя ID: {USER_ID}")
    
    # Запускаем бота и клиент
    await asyncio.gather(
        dp.start_polling(bot),
        client.run_until_disconnected()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("⏹ Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
