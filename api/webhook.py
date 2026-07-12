"""
Vercel serverless function - Telegram webhook endpoint.
"""

import os
import json
import asyncio
import logging

from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

from scraper import search_scholarships, Scholarship

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

BOLUM_SEC = 0

POPULAR_DEPARTMENTS = [
    ["Bilgisayar Mühendisliği", "Elektrik-Elektronik Müh."],
    ["Makine Mühendisliği", "İnşaat Mühendisliği"],
    ["Tıp", "Hukuk"],
    ["İşletme", "İktisat"],
    ["Eğitim", "Mimarlık"],
]


def format_scholarship(i: int, s: Scholarship) -> str:
    return f"{i}. {s.name}\n   {s.source_url}"


def format_header(department: str, count: int) -> str:
    return f"{department} - {count} burs bulundu:"


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    reply_keyboard = ReplyKeyboardMarkup(
        POPULAR_DEPARTMENTS,
        one_time_keyboard=True,
        resize_keyboard=True,
        input_field_placeholder="Bölümünüzü yazın...",
    )
    await update.message.reply_text(
        "Burs Botu'na hoşgeldiniz!\n\n"
        "Bölümünüzü yazın veya listeden seçin.\n"
        "İnternetten o bölüme uygun burs programlarını bulacağım.",
        reply_markup=reply_keyboard,
    )
    return BOLUM_SEC


async def bolum_secildi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    department = update.message.text.strip()
    await update.message.reply_text(
        f"\"{department}\" için internet taranıyor, bu biraz zaman alabilir...",
        reply_markup=ReplyKeyboardRemove(),
    )

    try:
        scholarships = await asyncio.to_thread(search_scholarships, department)
    except Exception as e:
        logger.error(f"Burs arama hatasi: {e}")
        await update.message.reply_text(
            "Arama sırasında bir hata oluştu. Lütfen tekrar deneyin.\n/start"
        )
        return ConversationHandler.END

    if not scholarships:
        await update.message.reply_text(
            f"\"{department}\" için burs sonucu bulunamadı.\n\n"
            "Farklı bir bölüm adı ile tekrar denemek için /start yazın."
        )
        return ConversationHandler.END

    header = format_header(department, len(scholarships))
    entries = [format_scholarship(i, s) for i, s in enumerate(scholarships, 1)]
    message = header + "\n\n" + "\n\n".join(entries)

    if len(message) <= 4096:
        await update.message.reply_text(message, disable_web_page_preview=True)
    else:
        chunks = [header]
        for entry in entries:
            if len(chunks[-1]) + len(entry) + 2 > 4000:
                chunks.append("")
            chunks[-1] += "\n\n" + entry
        for chunk in chunks:
            await update.message.reply_text(chunk.strip(), disable_web_page_preview=True)

    await update.message.reply_text("Başka bir bölüm aramak için /start yazın.")
    return ConversationHandler.END


async def cmd_iptal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "İşlem iptal edildi. /start ile tekrar başlayabilirsiniz.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# Application singleton
app = Application.builder().token(BOT_TOKEN).build()

conv_handler = ConversationHandler(
    entry_points=[CommandHandler("start", cmd_start)],
    states={
        BOLUM_SEC: [MessageHandler(filters.TEXT & ~filters.COMMAND, bolum_secildi)],
    },
    fallbacks=[CommandHandler("iptal", cmd_iptal)],
)
app.add_handler(conv_handler)


async def process_update(event_body: dict):
    async with app:
        update = Update.de_json(event_body, app.bot)
        await app.process_update(update)


from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length))
        asyncio.run(process_update(body))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running")
