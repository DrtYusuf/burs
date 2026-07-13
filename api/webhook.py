"""
Vercel serverless function - Telegram webhook endpoint.
"""

import os
import json
import logging
from http.server import BaseHTTPRequestHandler
from concurrent.futures import ThreadPoolExecutor

import requests as req

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

POPULAR_DEPARTMENTS = [
    ["Bilgisayar Mühendisliği", "Elektrik-Elektronik Müh."],
    ["Makine Mühendisliği", "İnşaat Mühendisliği"],
    ["Tıp", "Hukuk"],
    ["İşletme", "İktisat"],
    ["Eğitim", "Mimarlık"],
]


def send_message(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    req.post(f"{API_URL}/sendMessage", json=payload)


def format_scholarship(i, s):
    return f"{i}. {s.name}\n   {s.source_url}"


def handle_update(body):
    message = body.get("message")
    if not message:
        return

    text = message.get("text", "")
    chat_id = message["chat"]["id"]

    if text == "/start":
        reply_markup = {
            "keyboard": POPULAR_DEPARTMENTS,
            "one_time_keyboard": True,
            "resize_keyboard": True,
            "input_field_placeholder": "Bölümünüzü yazın...",
        }
        send_message(
            chat_id,
            "Burs Botu'na hoşgeldiniz!\n\n"
            "Bölümünüzü yazın veya listeden seçin.\n"
            "İnternetten o bölüme uygun burs programlarını bulacağım.",
            reply_markup=reply_markup,
        )
        return

    if text == "/iptal":
        send_message(chat_id, "İşlem iptal edildi. /start ile tekrar başlayabilirsiniz.",
                     reply_markup={"remove_keyboard": True})
        return

    department = text.strip()
    send_message(chat_id, f"\"{department}\" için internet taranıyor, bu biraz zaman alabilir...",
                 reply_markup={"remove_keyboard": True})

    try:
        from scraper import search_scholarships
        scholarships = search_scholarships(department)
    except Exception as e:
        logger.error(f"Burs arama hatasi: {e}")
        send_message(chat_id, "Arama sırasında bir hata oluştu. Lütfen tekrar deneyin.\n/start")
        return

    if not scholarships:
        send_message(chat_id, f"\"{department}\" için burs sonucu bulunamadı.\n\n"
                     "Farklı bir bölüm adı ile tekrar denemek için /start yazın.")
        return

    header = f"{department} - {len(scholarships)} burs bulundu:"
    entries = [format_scholarship(i, s) for i, s in enumerate(scholarships, 1)]
    msg = header + "\n\n" + "\n\n".join(entries)

    if len(msg) <= 4096:
        send_message(chat_id, msg)
    else:
        chunks = [header]
        for entry in entries:
            if len(chunks[-1]) + len(entry) + 2 > 4000:
                chunks.append("")
            chunks[-1] += "\n\n" + entry
        for chunk in chunks:
            send_message(chat_id, chunk.strip())

    send_message(chat_id, "Başka bir bölüm aramak için /start yazın.")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length))
        handle_update(body)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
