from telethon import TelegramClient, events

# Данные со скрина (my.telegram.org)
api_id = 23031681                          # <-- со скрина
api_hash = '71052a0b64e700f275c2957b2303ed62'  # <-- со скрина
phone = 'ВАШ_НОМЕР_ТЕЛЕФОНА'               # пример: +79161234567

# ID чатов (берутся именно так, с -100)
SOURCE_CHANNEL = -1002679107093
TARGET_GROUP = -1003944018782

client = TelegramClient('my_session', api_id, api_hash)

@client.on(events.NewMessage(chats=SOURCE_CHANNEL))
async def forward_handler(event):
    try:
        # Пересылаем сообщение в группу (сохраняется авторство и подпись "Forwarded from...")
        await event.message.forward_to(TARGET_GROUP)
        print(f"✅ Переслано сообщение {event.message.id}")
    except Exception as e:
        print(f"❌ Ошибка при пересылке: {e}")

def main():
    print("Запускаюсь...")
    client.start(phone=phone)
    print("Скрипт работает. Жду новые сообщения...")
    client.run_until_disconnected()

if __name__ == '__main__':
    main()
