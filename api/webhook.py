"""
Vercel serverless function - Telegram webhook endpoint.
"""

import os
import asyncio
import logging
import json

from dotenv import load_dotenv
from telegram import Update, Bot, ReplyKeyboardMarkup, ReplyKeyboardRemove

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = Bot(token=BOT_TOKEN)

POPULAR_DEPARTMENTS = [
    ["Bilgisayar Mühendisliği", "Elektrik-Elektronik Müh."],
    ["Makine Mühendisliği", "İnşaat Mühendisliği"],
    ["Tıp", "Hukuk"],
    ["İşletme", "İktisat"],
    ["Eğitim", "Mimarlık"],
]


def format_scholarship(i, s):
    return f"{i}. {s.name}\n   {s.source_url}"


async def handle_message(update_data: dict):
    update = Update.de_json(update_data, bot)

    if not update.message:
        return

    text = update.message.text or ""
    chat_id = update.message.chat_id

    if text == "/start":
        keyboard = [[btn for btn in row] for row in POPULAR_DEPARTMENTS]
        reply_markup = ReplyKeyboardMarkup(
            keyboard,
            one_time_keyboard=True,
            resize_keyboard=True,
            input_field_placeholder="Bölümünüzü yazın...",
        )
        await bot.send_message(
            chat_id=chat_id,
            text="Burs Botu'na hoşgeldiniz!\n\n"
                 "Bölümünüzü yazın veya listeden seçin.\n"
                 "İnternetten o bölüme uygun burs programlarını bulacağım.",
            reply_markup=reply_markup,
        )
        return

    if text == "/iptal":
        await bot.send_message(
            chat_id=chat_id,
            text="İşlem iptal edildi. /start ile tekrar başlayabilirsiniz.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    # Bolum secildi
    department = text.strip()
    await bot.send_message(
        chat_id=chat_id,
        text=f"\"{department}\" için internet taranıyor, bu biraz zaman alabilir...",
        reply_markup=ReplyKeyboardRemove(),
    )

    try:
        from scraper import search_scholarships
        scholarships = await asyncio.to_thread(search_scholarships, department)
    except Exception as e:
        logger.error(f"Burs arama hatasi: {e}")
        await bot.send_message(
            chat_id=chat_id,
            text="Arama sırasında bir hata oluştu. Lütfen tekrar deneyin.\n/start",
        )
        return

    if not scholarships:
        await bot.send_message(
            chat_id=chat_id,
            text=f"\"{department}\" için burs sonucu bulunamadı.\n\n"
                 "Farklı bir bölüm adı ile tekrar denemek için /start yazın.",
        )
        return

    header = f"{department} - {len(scholarships)} burs bulundu:"
    entries = [format_scholarship(i, s) for i, s in enumerate(scholarships, 1)]
    message = header + "\n\n" + "\n\n".join(entries)

    if len(message) <= 4096:
        await bot.send_message(chat_id=chat_id, text=message, disable_web_page_preview=True)
    else:
        chunks = [header]
        for entry in entries:
            if len(chunks[-1]) + len(entry) + 2 > 4000:
                chunks.append("")
            chunks[-1] += "\n\n" + entry
        for chunk in chunks:
            await bot.send_message(chat_id=chat_id, text=chunk.strip(), disable_web_page_preview=True)

    await bot.send_message(chat_id=chat_id, text="Başka bir bölüm aramak için /start yazın.")


from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length))
        asyncio.run(handle_message(body))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
