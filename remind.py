"""Напоминание о продлении бесплатного хостинга.

Бот вызывает check_once_a_day() после каждого сообщения: раз в сутки он узнаёт у PythonAnywhere
срок работы сайта и, если осталось 7 дней или меньше, пишет владельцу в Telegram.

Запуск вручную:  python remind.py         — показать срок
                 python remind.py --test  — прислать напоминание прямо сейчас (для проверки)
"""
import os
import sys
from datetime import date

import requests

import bot

LAST_CHECK_FILE = os.path.join(bot.BASE_DIR, ".last_reminder_check")


def _config():
    cfg = {}
    with open(os.path.join(bot.BASE_DIR, ".pythonanywhere"), encoding="utf-8") as f:
        for line in f:
            if "=" in line:
                k, v = line.strip().split("=", 1)
                cfg[k] = v
    return cfg


def check(force=False):
    cfg = _config()
    user = cfg["PA_USER"]
    info = requests.get(
        f"https://www.pythonanywhere.com/api/v0/user/{user}/webapps/{user}.pythonanywhere.com/",
        headers={"Authorization": f"Token {cfg['PA_TOKEN']}"}, timeout=30).json()
    expiry = date.fromisoformat(info["expiry"])
    days_left = (expiry - date.today()).days
    print("Сайт работает до", expiry, "— осталось дней:", days_left)
    if days_left <= 7 or force:
        owner_id = next(iter(bot.load_users()))
        bot.send(owner_id,
                 f"⏰ <b>Пора продлить бота!</b>\n\n"
                 f"Бесплатный хостинг выключится <b>{expiry:%d.%m.%Y}</b> "
                 f"(осталось дней: {days_left}).\n\n"
                 f"Как продлить (1 минута):\n"
                 f"1. Зайди на pythonanywhere.com под логином <b>{user}</b>\n"
                 f"2. Вверху вкладка <b>Web</b>\n"
                 f"3. Кнопка <b>«Run until 3 months from today»</b>\n\n"
                 f"Я буду напоминать каждый день, пока не продлишь.")


def check_once_a_day():
    today = date.today().isoformat()
    if os.path.exists(LAST_CHECK_FILE):
        with open(LAST_CHECK_FILE) as f:
            if f.read().strip() == today:
                return
    with open(LAST_CHECK_FILE, "w") as f:
        f.write(today)
    try:
        check()
    except Exception as e:
        print("Не удалось проверить срок хостинга:", repr(e))


if __name__ == "__main__":
    check(force="--test" in sys.argv)
