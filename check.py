"""Быстрая проверка разбора трат. Без интернета и без настоящей таблицы.
Запуск: .venv/bin/python check.py
"""
import os
import sys
import tempfile
from decimal import Decimal

import bot

# фраза → ожидаемые траты (сумма, валюта, категория)
CASES = {
    "500 кофе": [("500", "USD", "Еда")],
    "12.50 обед": [("12.50", "USD", "Еда")],
    "1 000 руб такси": [("1000", "RUB", "Транспорт")],
    "2 тыс. руб такси": [("2000", "RUB", "Транспорт")],
    "150k донг обед": [("150000", "VND", "Еда")],
    "1,5 латте": [("1.5", "USD", "Еда")],
    "маникюр 500000 донгов": [("500000", "VND", "Красота")],
    "кофе 5, такси 10 и обед 12": [("5", "USD", "Еда"), ("10", "USD", "Транспорт"), ("12", "USD", "Еда")],
    # голос без запятых
    "Еда 50 жилье 700 транспорт 100": [("50", "USD", "Еда"), ("700", "USD", "Жильё"), ("100", "USD", "Транспорт")],
    "50 еда 700 жилье 100 транспорт": [("50", "USD", "Еда"), ("700", "USD", "Жильё"), ("100", "USD", "Транспорт")],
    "обед 150 тысяч донгов такси 50 тысяч": [("150000", "VND", "Еда"), ("50000", "USD", "Транспорт")],
    # количество
    "две подписки по 22 бакса и 1 подписка за 2000 руб": [("44", "USD", "Подписки"), ("2000", "RUB", "Подписки")],
    "3 кофе по 2.5": [("7.5", "USD", "Еда")],
    "два обеда по 150 000 донгов": [("300000", "VND", "Еда")],
}

fails = 0
for text, expected in CASES.items():
    got = []
    for part in bot.split_expenses(text) or [text]:
        amount, currency, desc = bot.parse_expense(part)
        got.append((amount, currency, bot.guess_category(desc)))
    ok = len(got) == len(expected) and all(
        Decimal(e[0]) == g[0] and e[1] == g[1] and e[2] == g[2] for e, g in zip(expected, got))
    if not ok:
        fails += 1
        print(f"❌ «{text}»\n   ждали {expected}\n   вышло {[(str(a), c, k) for a, c, k in got]}")

# повтор одинаковой траты за 10 минут → предупреждение с кнопкой удаления
bot.DATA_FILE = os.path.join(tempfile.mkdtemp(), "expenses.csv")
sent = []
bot.send = lambda chat_id, text, buttons=None, keyboard=None: sent.append(buttons)
bot._save_expense(1, 1, "test", "кофе 5")
bot._save_expense(1, 1, "test", "кофе 5")
if not (sent[-1] and sent[-1][0][0]["callback_data"].startswith("del:")):
    fails += 1
    print("❌ повтор траты не распознан")

print("✅ всё ок" if not fails else f"\nОшибок: {fails}")
sys.exit(1 if fails else 0)
