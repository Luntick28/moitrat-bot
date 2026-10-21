"""Логика бота: разбор трат, хранение в таблице, отчёты.

Этот файл не запускается сам. Его используют:
  - run_local.py   — запуск на компьютере для проверки;
  - flask_app.py   — запуск на хостинге PythonAnywhere.
"""
import csv
import hashlib
import io
import os
import re
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "expenses.csv")
USERS_FILE = os.path.join(BASE_DIR, "allowed_users.txt")
ENV_FILE = os.path.join(BASE_DIR, ".env")


def _load_env():
    """Читает настройки (токен и т.п.) из файла .env."""
    if not os.path.exists(ENV_FILE):
        return
    with open(ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


_load_env()
TOKEN = os.environ.get("BOT_TOKEN", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")  # ключ сервиса распознавания голоса
TZ = ZoneInfo(os.environ.get("TIMEZONE", "Asia/Ho_Chi_Minh"))
API = f"https://api.telegram.org/bot{TOKEN}"
# Секретная часть адреса, по которому Telegram присылает сообщения на хостинг
WEBHOOK_SECRET = hashlib.sha256(TOKEN.encode()).hexdigest()[:32]

# ---------------------------------------------------------------- категории

CATEGORIES = ["Еда", "Транспорт", "Жильё", "Подписки", "Развлечения", "Другое", "Красота", "Спорт"]
EMOJI = {
    "Еда": "🍔",
    "Транспорт": "🚕",
    "Жильё": "🏠",
    "Подписки": "📱",
    "Развлечения": "🎉",
    "Красота": "💅",
    "Спорт": "🏋️",
    "Другое": "📦",
}
# Слова, по которым бот угадывает категорию (достаточно начала слова)
KEYWORDS = {
    "Еда": [
        "еда", "продукт", "кофе", "капучино", "латте", "супермаркет", "магазин",
        "обед", "завтрак", "ужин", "перекус", "вода", "фрукт", "овощ", "хлеб",
        "молоко", "мясо", "доставк", "grab food", "grabfood", "shopee food",
        "food", "coffee", "pho", "фо бо", "banh mi", "бань ми", "лавка", "пятёрочк", "пятерочк", "вкусвилл",
    ],
    "Транспорт": [
        "транспорт", "такси", "grab", "грэб", "грab", "gojek", "uber", "убер",
        "yandex go", "яндекс go", "бензин", "топливо", "заправк", "метро",
        "автобус", "байк", "bike", "мопед", "скутер", "парковк", "самолет",
        "самолёт", "авиа", "билет", "поезд", "электричк", "xanh", "xanhsm",
    ],
    "Жильё": [
        "жиль", "хат", "квартир", "аренда", "свет", "электричеств", "интернет",
        "коммунал", "жкх", "отель", "гостиниц", "airbnb", "букинг", "booking",
        "уборк", "хостел",
    ],
    "Подписки": [
        "подписк", "netflix", "нетфликс", "spotify", "спотифай", "youtube",
        "ютуб", "apple", "icloud", "chatgpt", "openai", "claude", "vpn", "впн",
        "яндекс плюс", "кинопоиск", "премиум", "premium", "telegram", "сотов",
        "связь", "мобильн",
    ],
    "Развлечения": [
        "развлеч", "ресторан", "кафе", "бар", "кино", "клуб", "пиво", "вино",
        "алкоголь", "коктейл", "кальян", "поход", "водопад", "пляж", "экскурс", "массаж", "спа",
        "концерт", "игр", "тусовк", "вечеринк", "караоке", "боулинг",
    ],
    "Красота": [
        "красот", "ногт", "ноготоч", "маникюр", "педикюр", "nail", "волос",
        "стрижк", "подстри", "барбер", "barber", "парикмах", "салон", "бров",
        "ресниц", "косметик", "окрашив", "укладк", "эпиляц", "депиляц", "шугар",
        "косметолог", "крем", "шампун",
    ],
    "Спорт": [
        "спорт", "зал", "тренаж", "фитнес", "gym", "джим", "тренер", "тренировк",
        "бассейн", "йог", "бокс", "муай", "тайск", "mma", "борьб", "джиу", "теннис",
        "падел", "padel", "футбол", "баскетбол", "волейбол", "сёрф", "серф", "surf",
        "протеин", "креатин", "спортпит", "кроссфит", "crossfit", "пробежк", "забег",
        "абонемент", "скалодр", "велосипед",
    ],
}
# Длинные слова проверяем первыми: «аренда байка» — это транспорт, а не жильё
_KEYWORD_LIST = sorted(
    ((kw, cat) for cat, kws in KEYWORDS.items() for kw in kws),
    key=lambda pair: -len(pair[0]),
)
_KEYWORD_LIST.insert(0, ("аренда байк", "Транспорт"))


def guess_category(description):
    text = description.lower()
    for kw, cat in _KEYWORD_LIST:
        if re.search(r"(?<!\w)" + re.escape(kw), text):
            return cat
    return None

# ------------------------------------------------------------------ валюты

CURRENCIES = {
    "USD": {"name": "Доллары", "icon": "💵"},
    "VND": {"name": "Донги", "icon": "🇻🇳"},
    "RUB": {"name": "Рубли", "icon": "🇷🇺"},
}
DEFAULT_CURRENCY = "USD"
CURRENCY_SYMBOLS = {"$": "USD", "₽": "RUB", "₫": "VND"}
CURRENCY_WORDS = {
    "USD": ["usd", "usdt", "дол", "долл", "доллар", "доллара", "долларов",
            "бакс", "бакса", "баксов", "юсдт", "уе"],
    "RUB": ["руб", "рубль", "рубля", "рублей", "р", "rub", "rur"],
    "VND": ["vnd", "донг", "донга", "донгов", "dong", "đ", "д"],
}
_WORD_TO_CURRENCY = {w: c for c, ws in CURRENCY_WORDS.items() for w in ws}

# Число: «500», «12.50», «1 000», «150.000», «150k», «1,5к»
_NUM_RE = re.compile(
    r"(?<!\w)(?P<int>\d{1,3}(?:[  .,]\d{3})+(?!\d)|\d+)"
    r"(?:[.,](?P<frac>\d{1,2})(?!\d))?"
    r"(?P<k>[kк](?![a-zа-яё])|\s*тыс[а-яё]*\.?)?"
    r"(?P<m>\s*(?:млн|миллион[а-яё]*)\.?)?",
    re.IGNORECASE,
)


def parse_expense(text):
    """Разбирает «500 кофе» → (сумма, валюта, описание). Если суммы нет — None."""
    match = _NUM_RE.search(text)
    if not match:
        return None
    digits = re.sub(r"[  .,]", "", match.group("int"))
    if match.group("frac"):
        digits += "." + match.group("frac")
    try:
        amount = Decimal(digits)
    except InvalidOperation:
        return None
    if match.group("k"):
        amount *= 1000
    if match.group("m"):
        amount *= 1000000
    if amount <= 0:
        return None

    rest = (text[: match.start()] + " " + text[match.end():]).lower()

    currency = None
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in rest:
            currency = code
            rest = rest.replace(symbol, " ")
            break
    if currency is None:
        for word in re.findall(r"[a-zа-яёđ]+", rest):
            if word in _WORD_TO_CURRENCY:
                currency = _WORD_TO_CURRENCY[word]
                rest = re.sub(r"(?<![a-zа-яёđ])" + re.escape(word) + r"(?![a-zа-яёđ])", " ", rest, count=1)
                break
    description = re.sub(r"\s+", " ", rest).strip(" .,-:;")
    return amount, currency or DEFAULT_CURRENCY, description


def fmt_money(amount, currency):
    amount = Decimal(amount)
    if currency == "USD" and amount != amount.to_integral_value():
        number = f"{amount:,.2f}"
    else:
        number = f"{amount:,.0f}"
    number = number.replace(",", " ")
    return {"USD": f"${number}", "RUB": f"{number} ₽", "VND": f"{number} ₫"}[currency]

# ----------------------------------------------------------------- таблица

FIELDS = ["id", "date", "user_id", "user_name", "amount", "currency", "category", "description"]


def read_rows():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_rows(rows):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, DATA_FILE)


def add_row(row):
    is_new = not os.path.exists(DATA_FILE)
    with open(DATA_FILE, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if is_new:
            writer.writeheader()
        writer.writerow(row)

# ------------------------------------------------------------ пользователи


def load_users():
    """Возвращает {id: имя}. Первый в списке — владелец."""
    users = {}
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, encoding="utf-8") as f:
            for line in f:
                if ";" in line:
                    uid, name = line.strip().split(";", 1)
                    users[int(uid)] = name
    return users


def add_user(uid, name):
    with open(USERS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{uid};{name}\n")

# ----------------------------------------------------------------- отчёты

MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль",
          "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]


RATES_FILE = os.path.join(BASE_DIR, "rates.json")


def get_rates():
    """Курсы валют к доллару {"RUB": 82.8, "VND": 25858, ...}. Обновляются раз в 12 часов.
    Если сервис курсов недоступен — берём последние сохранённые; если их нет — None."""
    import json
    cached = None
    if os.path.exists(RATES_FILE):
        with open(RATES_FILE, encoding="utf-8") as f:
            cached = json.load(f)
        if time.time() - cached["saved_at"] < 12 * 3600:
            return cached["rates"]
    try:
        data = requests.get("https://open.er-api.com/v6/latest/USD", timeout=15).json()
        rates = {code: data["rates"][code] for code in CURRENCIES}
        with open(RATES_FILE, "w", encoding="utf-8") as f:
            json.dump({"saved_at": time.time(), "rates": rates}, f)
        return rates
    except Exception as e:
        print("Не удалось получить курсы:", repr(e))
        return cached["rates"] if cached else None


def _total_in_usd(rows):
    """Общий итог всех валют в долларах по курсу (только если валют больше одной)."""
    if len({r["currency"] for r in rows}) < 2:
        return []
    rates = get_rates()
    if not rates:
        return []
    by_cat = {}
    for r in rows:
        usd = Decimal(r["amount"]) / Decimal(str(rates[r["currency"]]))
        by_cat[r["category"]] = by_cat.get(r["category"], Decimal(0)) + usd
    total = sum(by_cat.values())
    lines = ["", f"💰 <b>Всего ≈ {fmt_money(round(total), 'USD')}</b> (всё в долларах по курсу)"]
    for cat, amount in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        lines.append(f"   {EMOJI.get(cat, '•')} {cat}: ≈ {fmt_money(round(amount), 'USD')} ({round(amount * 100 / total)}%)")
    others = [f"{fmt_money(round(Decimal(str(rates[c]))), c)}" for c in CURRENCIES if c != "USD"]
    lines.append(f"<i>Курс: $1 = {' = '.join(others)}</i>")
    return lines


def build_report(rows, title):
    """Сводка по списку трат: итог по каждой валюте и разбивка по категориям."""
    title = f"📊 <b>Траты {title}</b>"
    if not rows:
        return title + "\n\nПока пусто. Напиши трату, например: <code>12 кофе</code>"

    lines = [title]
    for code, info in CURRENCIES.items():
        cur_rows = [r for r in rows if r["currency"] == code]
        if not cur_rows:
            continue
        total = sum(Decimal(r["amount"]) for r in cur_rows)
        by_cat = {}
        for r in cur_rows:
            by_cat[r["category"]] = by_cat.get(r["category"], Decimal(0)) + Decimal(r["amount"])
        lines.append("")
        lines.append(f"{info['icon']} <b>{info['name']}: {fmt_money(total, code)}</b>")
        for cat, amount in sorted(by_cat.items(), key=lambda kv: -kv[1]):
            percent = round(amount * 100 / total)
            lines.append(f"   {EMOJI.get(cat, '•')} {cat}: {fmt_money(amount, code)} ({percent}%)")

    lines += _total_in_usd(rows)

    counts = {}
    for r in rows:
        counts[r["user_name"]] = counts.get(r["user_name"], 0) + 1
    who = ", ".join(f"{name} — {n}" for name, n in counts.items())
    lines.append("")
    lines.append(f"Записей: {len(rows)} ({who})")
    return "\n".join(lines)


def month_report(now=None):
    now = now or datetime.now(TZ)
    rows = [r for r in read_rows() if r["date"].startswith(now.strftime("%Y-%m"))]
    return build_report(rows, f"за {MONTHS[now.month - 1]} {now.year}")


def week_report(now=None):
    """Последние 7 дней, включая сегодня."""
    now = now or datetime.now(TZ)
    start = now - timedelta(days=6)
    rows = [r for r in read_rows() if r["date"][:10] >= start.strftime("%Y-%m-%d")]
    return build_report(rows, f"за неделю ({start:%d.%m} – {now:%d.%m})")


def today_report(now=None):
    now = now or datetime.now(TZ)
    rows = [r for r in read_rows() if r["date"].startswith(now.strftime("%Y-%m-%d"))]
    return build_report(rows, f"за сегодня ({now:%d.%m})")


def build_excel():
    """Собирает все траты в файл Excel и возвращает его байты."""
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Траты"
    ws.append(["Дата", "Кто", "Сумма", "Валюта", "Категория", "Описание"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for r in read_rows():
        ws.append([r["date"], r["user_name"], float(r["amount"]), r["currency"],
                   r["category"], r["description"]])
    for col, width in zip("ABCDEF", [18, 12, 12, 9, 14, 30]):
        ws.column_dimensions[col].width = width
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

# --------------------------------------------------------------- Telegram


def _post(url, **kwargs):
    """Запрос с повторами: на бесплатном хостинге связь иногда мигает на секунду."""
    for attempt in range(4):
        try:
            return requests.post(url, **kwargs)
        except requests.RequestException as e:
            if attempt == 3:
                raise
            print(f"Связь мигнула ({e.__class__.__name__}), повторяю...")
            time.sleep(1 + attempt * 2)


def tg(method, **params):
    return _post(f"{API}/{method}", json=params, timeout=20).json()


# Кнопки, которые всегда видны внизу чата
MENU_BUTTONS = {"📅 Сегодня": "/today", "📊 Неделя": "/week", "🗓 Месяц": "/report"}
MENU_KEYBOARD = {"keyboard": [[{"text": t} for t in MENU_BUTTONS]],
                 "resize_keyboard": True, "is_persistent": True}


def send(chat_id, text, buttons=None, keyboard=None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if buttons:
        params["reply_markup"] = {"inline_keyboard": buttons}
    elif keyboard:
        params["reply_markup"] = keyboard
    return tg("sendMessage", **params)


def category_buttons(row_id):
    order = [c for c in CATEGORIES if c != "Другое"] + ["Другое"]
    btns = [{"text": f"{EMOJI[c]} {c}", "callback_data": f"cat:{row_id}:{CATEGORIES.index(c)}"}
            for c in order]
    return [btns[i:i + 2] for i in range(0, len(btns), 2)]


def _esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _saved_text(row):
    desc = f" ({_esc(row['description'])})" if row["description"] else ""
    return (f"✅ Записал: {EMOJI[row['category']]} {row['category']} — "
            f"{fmt_money(row['amount'], row['currency'])}{desc}")


HELP = (
    "👋 Я считаю ваши траты.\n\n"
    "<b>Как записать трату</b> — просто напиши сумму и на что:\n"
    "<code>12 кофе</code> — $12 (доллары по умолчанию)\n"
    "<code>150k донг обед</code> — 150 000 донгов\n"
    "<code>1000 руб такси</code> — 1 000 рублей\n\n"
    "Категорию я угадываю сам, а если не угадаю — покажу кнопки.\n\n"
    "<b>Отчёты</b> — кнопки внизу чата или команды:\n"
    "/today — траты за сегодня\n"
    "/week — за последние 7 дней\n"
    "/report — за этот месяц\n\n"
    "<b>Другое</b>\n"
    "/export — вся таблица файлом Excel\n"
    "/undo — удалить твою последнюю трату\n"
    "/reset — стереть все траты и начать с нуля (только владелец)\n"
    "/help — эта подсказка"
)


def handle_update(update):
    """Главная функция: получает одно событие от Telegram и отвечает на него."""
    if "callback_query" in update:
        _handle_button(update["callback_query"])
        return
    msg = update.get("message")
    if not msg:
        return
    if "voice" in msg or "audio" in msg:
        _handle_voice(msg)
        return
    if "text" not in msg:
        return

    chat_id = msg["chat"]["id"]
    user = msg["from"]
    uid = user["id"]
    name = user.get("first_name") or user.get("username") or str(uid)
    text = msg["text"].strip()
    text = MENU_BUTTONS.get(text, text)  # нажатая кнопка внизу = команда

    users = load_users()
    if not users:
        add_user(uid, name)  # самый первый, кто написал боту, становится владельцем
        users = load_users()
        send(chat_id, f"🔑 {_esc(name)}, ты владелец бота. Чужим я отвечать не буду.")
    if uid not in users:
        _ask_owner(users, uid, name)
        send(chat_id, "🔒 Это личный бот. Я отправил владельцу запрос на доступ — подожди, пока он разрешит.")
        return

    command = text.split()[0].split("@")[0].lower() if text.startswith("/") else None
    if command in ("/start", "/help"):
        send(chat_id, HELP, keyboard=MENU_KEYBOARD)
    elif command == "/report":
        send(chat_id, month_report())
    elif command == "/week":
        send(chat_id, week_report())
    elif command == "/today":
        send(chat_id, today_report())
    elif command == "/export":
        if not read_rows():
            send(chat_id, "Пока нечего выгружать — трат ещё нет.")
            return
        filename = f"траты_{datetime.now(TZ):%Y-%m-%d}.xlsx"
        _post(f"{API}/sendDocument", data={"chat_id": chat_id},
                      files={"document": (filename, build_excel())}, timeout=60)
    elif command == "/undo":
        _undo(chat_id, uid)
    elif command == "/reset":
        if uid != next(iter(users)):
            send(chat_id, "Обнулить траты может только владелец бота.")
            return
        count = len(read_rows())
        send(chat_id, f"⚠️ Стереть <b>все траты</b> (записей: {count}) и начать с нуля?\n"
                      f"На всякий случай я сохраню копию на хостинге.",
             [[{"text": "🗑 Да, стереть всё", "callback_data": "reset:yes"},
               {"text": "Отмена", "callback_data": "reset:no"}]])
    elif command:
        send(chat_id, "Не знаю такую команду. /help — список команд.")
    else:
        _save_expense(chat_id, uid, users[uid], text)

    if os.path.exists(os.path.join(BASE_DIR, ".pythonanywhere")):
        import remind  # только на хостинге: раз в день проверяем, не пора ли продлить
        remind.check_once_a_day()


def _save_expense(chat_id, uid, name, text):
    parsed = parse_expense(text)
    if not parsed:
        send(chat_id, "🤔 Не вижу суммы. Напиши, например: <code>12 кофе</code>\n/help — подсказка")
        return
    amount, currency, description = parsed
    category = guess_category(description)
    row = {
        "id": uuid.uuid4().hex[:8],
        "date": datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
        "user_id": uid,
        "user_name": name,
        "amount": str(amount),
        "currency": currency,
        "category": category or "Другое",
        "description": description,
    }
    add_row(row)
    if category:
        buttons = [[{"text": "✏️ Другая категория", "callback_data": f"edit:{row['id']}"}]]
        send(chat_id, _saved_text(row), buttons)
    else:
        send(chat_id, _saved_text(row) + "\n\nНе понял категорию — выбери:", category_buttons(row["id"]))


def transcribe(file_id):
    """Скачивает голосовое из Telegram и превращает его в текст через Groq."""
    file_path = tg("getFile", file_id=file_id)["result"]["file_path"]
    audio = requests.get(f"https://api.telegram.org/file/bot{TOKEN}/{file_path}", timeout=60).content
    resp = requests.post(
        "https://api.groq.com/openai/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {GROQ_KEY}"},
        files={"file": ("voice.ogg", audio)},
        data={"model": "whisper-large-v3-turbo", "language": "ru", "response_format": "json"},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["text"].strip()


def split_expenses(text):
    """«кофе 5, такси 10 и обед 12» → ["кофе 5", "такси 10", "обед 12"]."""
    parts = re.split(r"[;\n]|,\s|(?<!тыс)(?<!млн)(?<!руб)(?<!дол)\.\s|(?<!\w)(?:и|а ещё|а еще|плюс|потом)(?!\w)", text)
    result = []
    for p in parts:
        result += _split_by_numbers(p)
    return [p.strip(" .,") for p in result if p.strip(" .,") and _NUM_RE.search(p)]


def _split_by_numbers(text):
    """Голос часто приходит без запятых: «еда 50 жилье 700 долларов такси 100».
    Если чисел несколько — режем так, чтобы на каждый кусок пришлось одно число."""
    nums = list(_NUM_RE.finditer(text))
    if len(nums) < 2:
        return [text]
    words_first = bool(re.search(r"[a-zа-яё]", text[: nums[0].start()], re.IGNORECASE))
    cuts = []
    for num in nums[:-1] if words_first else nums[1:]:
        if not words_first:
            cuts.append(num.start())
            continue
        end = num.end()  # «еда 50 долларов | жилье…» — валюту оставляем при своей сумме
        after = re.match(r"\s*([a-zа-яёđ]+|[$₽₫])", text[end:], re.IGNORECASE)
        if after and (after.group(1).lower() in _WORD_TO_CURRENCY or after.group(1) in CURRENCY_SYMBOLS):
            end += after.end()
        cuts.append(end)
    bounds = [0] + cuts + [len(text)]
    return [text[a:b] for a, b in zip(bounds, bounds[1:])]


def _handle_voice(msg):
    chat_id = msg["chat"]["id"]
    uid = msg["from"]["id"]
    users = load_users()
    if uid not in users:
        return
    if not GROQ_KEY:
        send(chat_id, "🎤 Голосовые я пока не понимаю — напиши, пожалуйста, текстом, например: <code>12 кофе</code>")
        return
    file_id = (msg.get("voice") or msg.get("audio"))["file_id"]
    try:
        text = transcribe(file_id)
    except Exception as e:
        print("Ошибка распознавания:", repr(e))
        send(chat_id, "😕 Не получилось разобрать голосовое. Попробуй ещё раз или напиши текстом.")
        return
    parts = split_expenses(text)
    if not parts:
        send(chat_id, f"🎤 Услышал: «{_esc(text)}»\n\n🤔 Но не понял сумму. Скажи, например: «пять долларов кофе».")
        return
    send(chat_id, f"🎤 Услышал: «{_esc(text)}»")
    for part in parts:
        _save_expense(chat_id, uid, users[uid], part)


def _undo(chat_id, uid):
    rows = read_rows()
    for i in range(len(rows) - 1, -1, -1):
        if rows[i]["user_id"] == str(uid):
            removed = rows.pop(i)
            write_rows(rows)
            send(chat_id, "🗑 Удалил: " + _saved_text(removed)[len("✅ Записал: "):])
            return
    send(chat_id, "У тебя пока нет записанных трат.")


def _ask_owner(users, uid, name):
    owner_id = next(iter(users))
    data = f"allow:{uid}:"
    short = name.encode("utf-8")[: 64 - len(data.encode())].decode("utf-8", "ignore")
    send(owner_id, f"🙋 {_esc(name)} просит доступ к боту. Разрешить?",
         [[{"text": f"✅ Разрешить {name}", "callback_data": data + short}]])


def _handle_button(query):
    uid = query["from"]["id"]
    data = query.get("data", "")
    msg = query.get("message", {})
    chat_id = msg.get("chat", {}).get("id")
    users = load_users()
    tg("answerCallbackQuery", callback_query_id=query["id"])
    if uid not in users:
        return

    if data.startswith("allow:"):
        _, new_id, new_name = data.split(":", 2)
        if int(new_id) not in users:
            add_user(int(new_id), new_name)
            send(int(new_id), "🎉 Доступ открыт!\n\n" + HELP, keyboard=MENU_KEYBOARD)
        tg("editMessageText", chat_id=chat_id, message_id=msg["message_id"],
           text=f"✅ {_esc(new_name)} теперь может пользоваться ботом.")
        return

    if data.startswith("reset:"):
        if data == "reset:yes" and uid == next(iter(users)):
            rows = read_rows()
            if rows:
                backup = os.path.join(BASE_DIR, f"backup_{datetime.now(TZ):%Y-%m-%d_%H-%M}.csv")
                os.replace(DATA_FILE, backup)
            text = f"✅ Всё обнулено (стёрто записей: {len(rows)}). Считаем с чистого листа!"
        else:
            text = "Отменено, ничего не стёрто."
        tg("editMessageText", chat_id=chat_id, message_id=msg["message_id"], text=text)
        return

    if data.startswith("edit:"):
        row_id = data.split(":", 1)[1]
        tg("editMessageReplyMarkup", chat_id=chat_id, message_id=msg["message_id"],
           reply_markup={"inline_keyboard": category_buttons(row_id)})
        return

    if data.startswith("cat:"):
        _, row_id, idx = data.split(":")
        rows = read_rows()
        for row in rows:
            if row["id"] == row_id:
                row["category"] = CATEGORIES[int(idx)]
                write_rows(rows)
                tg("editMessageText", chat_id=chat_id, message_id=msg["message_id"],
                   text=_saved_text(row), parse_mode="HTML")
                return
        tg("editMessageText", chat_id=chat_id, message_id=msg["message_id"],
           text="Эта трата уже удалена.")
