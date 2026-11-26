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
    "500 кофе": [("500", "USD", "Продукты")],
    "12.50 обед": [("12.50", "USD", "Продукты")],
    "1 000 руб такси": [("1000", "RUB", "Транспорт")],
    "2 тыс. руб такси": [("2000", "RUB", "Транспорт")],
    "150k донг обед": [("150000", "VND", "Продукты")],
    "1,5 латте": [("1.5", "USD", "Продукты")],
    "маникюр 500000 донгов": [("500000", "VND", "Красота")],
    "визаран автобус 30": [("30", "USD", "Визаран")],
    "визаран отель 40": [("40", "USD", "Визаран")],
    "виза 25": [("25", "USD", "Визаран")],
    "футболка 300000 донгов": [("300000", "VND", "Одежда")],
    "кроссовки 50 баксов": [("50", "USD", "Одежда")],
    "кофе 5, такси 10 и обед 12": [("5", "USD", "Продукты"), ("10", "USD", "Транспорт"), ("12", "USD", "Продукты")],
    # голос без запятых
    "Еда 50 жилье 700 транспорт 100": [("50", "USD", "Продукты"), ("700", "USD", "Жильё"), ("100", "USD", "Транспорт")],
    "50 еда 700 жилье 100 транспорт": [("50", "USD", "Продукты"), ("700", "USD", "Жильё"), ("100", "USD", "Транспорт")],
    "обед 150 тысяч донгов такси 50 тысяч": [("150000", "VND", "Продукты"), ("50000", "USD", "Транспорт")],
    # количество
    "две подписки по 22 бакса и 1 подписка за 2000 руб": [("44", "USD", "Подписки"), ("2000", "RUB", "Подписки")],
    "3 кофе по 2.5": [("7.5", "USD", "Продукты")],
    "два обеда по 150 000 донгов": [("300000", "VND", "Продукты")],
    # здоровье, доставка еды
    "стоматолог 4000000 донгов": [("4000000", "VND", "Здоровье")],
    "таблетки 330000 донгов": [("330000", "VND", "Здоровье")],
    "аптека 5": [("5", "USD", "Здоровье")],
    "доставка еды 6.25": [("6.25", "USD", "Доставка еды")],
    "граб фуд 200000 донгов": [("200000", "VND", "Доставка еды")],
    "grab food 8": [("8", "USD", "Доставка еды")],
    "кфс 180000 донгов": [("180000", "VND", "Доставка еды")],
    "grab 5": [("5", "USD", "Транспорт")],
    "барбер 8": [("8", "USD", "Красота")],
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

# кнопка «прошлый месяц»: из ноября — октябрь, из января — декабрь прошлого года
from datetime import datetime
for now, want in ((datetime(2026, 11, 1, tzinfo=bot.TZ), "month:2026-10"),
                  (datetime(2027, 1, 15, tzinfo=bot.TZ), "month:2026-12")):
    if bot.month_buttons(now)[0][0]["callback_data"] != want:
        fails += 1
        print(f"❌ кнопка прошлого месяца для {now:%m.%Y}")
# у прошлого месяца есть «▶️ следующий», у текущего — нет
if len(bot.month_buttons(datetime(2026, 9, 1, tzinfo=bot.TZ))[0]) != 2 or \
        len(bot.month_buttons(datetime.now(bot.TZ))[0]) != 1:
    fails += 1
    print("❌ кнопка следующего месяца")

# отчёт: обычно только доллары по курсу, «Подробно» — по каждой валюте
bot.get_rates = lambda: {"USD": 1, "VND": 25000, "RUB": 80}
rows = [{"amount": "5", "currency": "USD", "category": "Продукты", "user_name": "t"},
        {"amount": "250000", "currency": "VND", "category": "Здоровье", "user_name": "t"}]
brief, full = bot.build_report(rows, "т"), bot.build_report(rows, "т", detailed=True)
if "Донги" in brief or "Всего ≈ $15" not in brief or "Донги" not in full:
    fails += 1
    print("❌ краткий/подробный отчёт\n", brief, "\n---\n", full)
now = datetime(2026, 11, 20, tzinfo=bot.TZ)
b = bot.report_buttons("month", now)
if b[0][0]["callback_data"] != "detail:month:2026-11" or not b[1][0]["callback_data"].startswith("month:") or \
        bot.report_buttons("today", now, True)[0][0]["callback_data"] != "brief:today:2026-11-20":
    fails += 1
    print("❌ кнопки отчёта", b)

# /emoji: премиум-эмодзи по строкам; позиции Telegram считает в UTF-16 (обычный эмодзи = 2)
bot.CUSTOM_EMOJI_FILE = os.path.join(tempfile.mkdtemp(), "custom_emoji.json")
text = "/emoji\n🙂 Продукты 🥦\nДоставка еды 🛵"
def _u16(s):
    return len(s.encode("utf-16-le")) // 2
ents = [{"type": "custom_emoji", "offset": _u16(text[:text.index("🥦")]), "length": 2, "custom_emoji_id": "111"},
        {"type": "custom_emoji", "offset": _u16(text[:text.index("🛵")]), "length": 2, "custom_emoji_id": "222"}]
bot.set_custom_emoji(text, ents)
if bot.custom_emoji() != {"Продукты": "111", "Доставка еды": "222"}:
    fails += 1
    print("❌ /emoji сохранил", bot.custom_emoji())
# один эмодзи без названий → подбор из всего набора
real_tg = bot.tg
bot.tg = lambda method, **p: {"result": [{"set_name": "pack"}]} if method == "getCustomEmojiStickers" else \
    {"result": {"stickers": [{"emoji": "💊", "custom_emoji_id": "333"}, {"emoji": "🏠", "custom_emoji_id": "444"}]}}
bot.set_custom_emoji("/emoji 🙂", [{"type": "custom_emoji", "offset": 7, "length": 2, "custom_emoji_id": "999"}])
bot.tg = real_tg
if bot.custom_emoji().get("Здоровье") != "333" or bot.custom_emoji().get("Жильё") != "444":
    fails += 1
    print("❌ подбор из набора", bot.custom_emoji())
btn = next(b for row in bot.category_buttons("x") for b in row if b["text"] == "Продукты")
if bot.category_buttons("x")[0][0]["callback_data"] != "cat:x:2":  # первой в кнопках — «Жильё»
    fails += 1
    print("❌ порядок кнопок категорий")
if btn.get("icon_custom_emoji_id") != "111" or 'emoji-id="111"' not in bot.cat_icon("Продукты"):
    fails += 1
    print("❌ премиум-эмодзи не попали в кнопку или текст", btn)

print("✅ всё ок" if not fails else f"\nОшибок: {fails}")
sys.exit(1 if fails else 0)
