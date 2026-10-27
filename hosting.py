"""Таблица трат на хостинге PythonAnywhere — посмотреть и поправить без ручной возни.

  .venv/bin/python hosting.py status            — бот отвечает? есть ли застрявшие сообщения
  .venv/bin/python hosting.py today             — траты за сегодня (с id)
  .venv/bin/python hosting.py last [N]          — последние N трат (по умолчанию 15)
  .venv/bin/python hosting.py delete ID [ID…]   — удалить траты (перед этим копия в backups/)
  .venv/bin/python hosting.py set ID поле=значение …  — поправить трату (amount, currency, category, description)
  .venv/bin/python hosting.py log [N]           — последние строки журнала ошибок
"""
import csv
import io
import os
import sys
from datetime import datetime

import requests

import bot

BASE = os.path.dirname(os.path.abspath(__file__))
cfg = dict(l.strip().split("=", 1) for l in open(os.path.join(BASE, ".pythonanywhere")) if "=" in l)
USER = cfg["PA_USER"]
HEADERS = {"Authorization": f"Token {cfg['PA_TOKEN']}"}
FILES = f"https://www.pythonanywhere.com/api/v0/user/{USER}/files/path"
CSV_URL = f"{FILES}/home/{USER}/moitrat/expenses.csv"


def load():
    r = requests.get(CSV_URL, headers=HEADERS, timeout=30)
    r.raise_for_status()
    return r.text, list(csv.DictReader(io.StringIO(r.text)))


def save(original, rows):
    os.makedirs(os.path.join(BASE, "backups"), exist_ok=True)
    backup = os.path.join(BASE, "backups", f"expenses_{datetime.now():%Y-%m-%d_%H-%M-%S}.csv")
    open(backup, "w", encoding="utf-8").write(original)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=bot.FIELDS)
    w.writeheader()
    w.writerows(rows)
    requests.post(CSV_URL, headers=HEADERS, files={"content": buf.getvalue().encode()}, timeout=60).raise_for_status()
    print(f"Сохранено. Копия до правки: {backup}")


def show(rows):
    for r in rows:
        print(f"{r['id']}  {r['date']}  {bot.fmt_money(r['amount'], r['currency']):>14}  "
              f"{r['category']:<12} {r['description']}  ({r['user_name']})")


def main(cmd="status", *args):
    if cmd == "status":
        site = requests.get(f"https://{USER}.pythonanywhere.com/", timeout=30)
        info = bot.tg("getWebhookInfo")["result"]
        print("Сайт:", site.status_code, site.text.strip())
        print("Застрявших сообщений в Telegram:", info.get("pending_update_count"))
        if info.get("last_error_message"):
            print("Последняя ошибка Telegram:", info["last_error_message"])
    elif cmd == "today":
        today = datetime.now(bot.TZ).strftime("%Y-%m-%d")
        show([r for r in load()[1] if r["date"].startswith(today)])
    elif cmd == "last":
        show(load()[1][-int(args[0] if args else 15):])
    elif cmd == "delete":
        original, rows = load()
        left = [r for r in rows if r["id"] not in args]
        missing = set(args) - {r["id"] for r in rows}
        if missing:
            sys.exit(f"Нет таких id: {', '.join(missing)} — ничего не удалено")
        show([r for r in rows if r["id"] in args])
        save(original, left)
    elif cmd == "set":
        row_id, changes = args[0], dict(a.split("=", 1) for a in args[1:])
        if not set(changes) <= {"amount", "currency", "category", "description"}:
            sys.exit("Можно менять только amount, currency, category, description")
        if "category" in changes and changes["category"] not in bot.CATEGORIES:
            sys.exit(f"Нет такой категории. Есть: {', '.join(bot.CATEGORIES)}")
        original, rows = load()
        row = next((r for r in rows if r["id"] == row_id), None)
        if not row:
            sys.exit(f"Нет траты с id {row_id}")
        row.update(changes)
        show([row])
        save(original, rows)
    elif cmd == "log":
        text = requests.get(f"{FILES}/var/log/{USER}.pythonanywhere.com.server.log", headers=HEADERS, timeout=30).text
        print("\n".join(text.splitlines()[-int(args[0] if args else 20):]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main(*sys.argv[1:])
