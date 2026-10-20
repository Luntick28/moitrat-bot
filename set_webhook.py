"""Говорит Telegram, куда присылать сообщения: python set_webhook.py https://ИМЯ.pythonanywhere.com"""
import sys

import bot

site = sys.argv[1].rstrip("/")
print(bot.tg("setWebhook", url=f"{site}/webhook/{bot.WEBHOOK_SECRET}",
             allowed_updates=["message", "callback_query"], drop_pending_updates=False))
