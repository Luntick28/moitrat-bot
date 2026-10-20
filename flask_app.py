"""Запуск бота на хостинге PythonAnywhere: Telegram сам присылает сюда сообщения."""
import traceback

from flask import Flask, request

import bot

app = Flask(__name__)


@app.route("/")
def index():
    return "Бот работает ✅"


@app.route(f"/webhook/{bot.WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    try:
        bot.handle_update(request.get_json(force=True, silent=True) or {})
    except Exception:
        traceback.print_exc()  # ошибку видно в журнале PythonAnywhere
    return "ok"
