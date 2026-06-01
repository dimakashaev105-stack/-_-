import os
import sys
import logging
import asyncio
from telethon import TelegramClient, events
from telethon.errors import RpcCallFailError, FloodWaitError

# ---------- НАСТРОЙКИ ----------
api_id = 23031681
api_hash = '71052a0b64e700f275c2957b2303ed62'

SOURCE_CHANNEL = -1002679107093
TARGET_GROUP = -1003944018782

# Номер телефона можно задать тут или через переменную окружения PHONE
phone = os.environ.get('PHONE', '+ВАШ_НОМЕР')  # <-- впиши свой номер с +, например +79991234567

# Логи в файл (чтобы потом смотреть через SSH)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('forwarder.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

client = TelegramClient('my_session', api_id, api_hash)

@client.on(events.NewMessage(chats=SOURCE_CHANNEL))
async def handler(event):
    try:
        await event.message.forward_to(TARGET_GROUP)
        logger.info(f"Переслано сообщение id={event.message.id}")
    except FloodWaitError as e:
        logger.warning(f"FloodWait: сплю {e.seconds} сек...")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        logger.error(f"Ошибка пересылки: {e}")

async def main():
    logger.info("Запускаю клиент...")
    await client.start(phone=phone)
    me = await client.get_me()
    logger.info(f"Авторизован как {me.first_name} (@{me.username})")
    logger.info("Ожидаю новые сообщения...")
    await client.run_until_disconnected()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Остановлен вручную (Ctrl+C)")
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}")