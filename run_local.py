"""Запуск бота на компьютере (для проверки). Остановить — Ctrl+C."""
import time

import requests

import bot

if not bot.TOKEN:
    raise SystemExit("Нет токена: впиши BOT_TOKEN=... в файл .env")

bot.tg("deleteWebhook")  # если бот был на хостинге — временно забираем его себе
me = bot.tg("getMe")["result"]
print(f"Бот @{me['username']} запущен. Остановить — Ctrl+C")
offset = 0
while True:
    try:
        resp = requests.get(f"{bot.API}/getUpdates",
                            params={"offset": offset, "timeout": 30}, timeout=40).json()
        for update in resp.get("result", []):
            offset = update["update_id"] + 1
            try:
                bot.handle_update(update)
            except Exception as e:
                print("Ошибка:", repr(e))
    except requests.RequestException as e:
        print("Нет связи, пробую снова:", repr(e))
        time.sleep(5)
