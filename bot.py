"""
Telegram Burs Botu - Kullanici bolumunu yazar, bot internetten
o bolume uygun burs programlarini arar ve listeler.

Kullanim:
  1. .env dosyasina TELEGRAM_BOT_TOKEN ekleyin
  2. pip install -r requirements.txt
  3. python bot.py
"""

import asyncio
import logging
import os
import sys

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
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
    lines = [
        f"{i}. {s.name}",
        f"   {s.description[:300]}" if s.description else "",
        f"   Kaynak: {s.source_name}",
        f"   Link: {s.source_url}",
    ]
    return "\n".join(line for line in lines if line)


def format_header(department: str, count: int) -> str:
    return (
        f"== {department.upper()} - BURS SONUCLARI ==\n"
        f"{count} sonuc bulundu\n"
        f"(Bilinen burs siteleri + Google taramasi)"
    )


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

    entries = []
    for i, s in enumerate(scholarships, 1):
        entries.append(format_scholarship(i, s))

    message = header + "\n\n" + "\n\n".join(entries)

    # Telegram 4096 karakter limiti
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
            await asyncio.sleep(0.5)

    await update.message.reply_text("Başka bir bölüm aramak için /start yazın.")
    return ConversationHandler.END


async def cmd_iptal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "İşlem iptal edildi. /start ile tekrar başlayabilirsiniz.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


def main():
    if not BOT_TOKEN:
        print("HATA: TELEGRAM_BOT_TOKEN ayarlanmamis!")
        print(".env dosyasina TELEGRAM_BOT_TOKEN=your_token ekleyin.")
        sys.exit(1)

    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            BOLUM_SEC: [MessageHandler(filters.TEXT & ~filters.COMMAND, bolum_secildi)],
        },
        fallbacks=[CommandHandler("iptal", cmd_iptal)],
    )

    app.add_handler(conv_handler)

    logger.info("Bot baslatiliyor...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
