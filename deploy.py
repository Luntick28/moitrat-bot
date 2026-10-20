"""Загружает бота на PythonAnywhere и подключает к нему Telegram.

Запуск:  python deploy.py           — обновить код бота на хостинге
         python deploy.py --data    — то же + перенести таблицу трат и список пользователей
"""
import os
import sys

import requests

import bot

BASE = os.path.dirname(os.path.abspath(__file__))
cfg = {}
with open(os.path.join(BASE, ".pythonanywhere"), encoding="utf-8") as f:
    for line in f:
        if "=" in line:
            k, v = line.strip().split("=", 1)
            cfg[k] = v

USER = cfg["PA_USER"]
API = f"https://www.pythonanywhere.com/api/v0/user/{USER}"
HEADERS = {"Authorization": f"Token {cfg['PA_TOKEN']}"}
DOMAIN = f"{USER}.pythonanywhere.com"
REMOTE_DIR = f"/home/{USER}/moitrat"
PYTHON = "python310"

WSGI = f'''import sys
path = "{REMOTE_DIR}"
if path not in sys.path:
    sys.path.insert(0, path)
from flask_app import app as application
'''


def upload(remote_path, content):
    r = requests.post(f"{API}/files/path{remote_path}", headers=HEADERS,
                      files={"content": content}, timeout=60)
    print(f"  {remote_path}: {'ok' if r.status_code in (200, 201) else r.text}")
    r.raise_for_status()


print("1. Сайт на хостинге")
apps = requests.get(f"{API}/webapps/", headers=HEADERS, timeout=30).json()
if not any(a["domain_name"] == DOMAIN for a in apps):
    r = requests.post(f"{API}/webapps/", headers=HEADERS,
                      data={"domain_name": DOMAIN, "python_version": PYTHON}, timeout=60)
    print("  создан:", r.status_code, r.text[:200])
    r.raise_for_status()
else:
    print("  уже есть")

print("2. Загружаю файлы")
files = ["bot.py", "flask_app.py", "remind.py", ".env", ".pythonanywhere"]
if "--data" in sys.argv:
    files += ["expenses.csv", "allowed_users.txt"]
for name in files:
    path = os.path.join(BASE, name)
    if os.path.exists(path):
        with open(path, "rb") as f:
            upload(f"{REMOTE_DIR}/{name}", f.read())
upload(f"/var/www/{USER}_pythonanywhere_com_wsgi.py", WSGI.encode())

print("3. Перезапускаю сайт")
r = requests.post(f"{API}/webapps/{DOMAIN}/reload/", headers=HEADERS, timeout=120)
print("  ", r.status_code, r.text[:200])

print("4. Проверяю, что сайт отвечает")
r = requests.get(f"https://{DOMAIN}/", timeout=30)
print("  ", r.status_code, r.text[:100])

print("5. Подключаю Telegram")
print("  ", bot.tg("setWebhook", url=f"https://{DOMAIN}/webhook/{bot.WEBHOOK_SECRET}",
                   allowed_updates=["message", "callback_query"]))

print("6. Меню команд в Telegram")
print("  ", bot.tg("setMyCommands", commands=[
    {"command": "today", "description": "Траты за сегодня"},
    {"command": "week", "description": "Траты за неделю"},
    {"command": "report", "description": "Траты за месяц"},
    {"command": "export", "description": "Таблица Excel"},
    {"command": "undo", "description": "Удалить последнюю трату"},
    {"command": "help", "description": "Подсказка"},
]))
