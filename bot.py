"""
Telegram Burs Botu - 3 gunde bir burs ve kredi duyurularini kontrol eder.

Kullanim:
  1. .env dosyasina TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID ekleyin
  2. pip install -r requirements.txt
  3. python bot.py
"""

import asyncio
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from scraper import scrape_all, Scholarship

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CHECK_INTERVAL_DAYS = 3


def format_scholarship(s: Scholarship) -> str:
    """Tek bir burs bilgisini Telegram mesaji olarak formatlar."""
    lines = [
        f"{'=' * 30}",
        f"BURS ADI: {s.name}",
        f"SINIFLAR: {s.grades}",
        f"BOLUMLER: {s.departments}",
        f"LISANS BURS UCRETI: {s.amount}",
    ]
    if s.source_url:
        lines.append(f"DETAY: {s.source_url}")
    lines.append(f"{'=' * 30}")
    return "\n".join(lines)


def format_message(scholarships: list[Scholarship]) -> str:
    """Tum burslari tek bir mesajda formatlar."""
    header = (
        f"BURS VE KREDI DUYURULARI\n"
        f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n"
        f"Bulunan yeni burs/kredi sayisi: {len(scholarships)}\n"
    )

    body = "\n\n".join(format_scholarship(s) for s in scholarships)
    return f"{header}\n{body}"


async def check_and_notify(bot: Bot):
    """Burslari kontrol et ve yeni burs varsa bildirim gonder."""
    logger.info("Burs kontrolu baslatiliyor...")

    try:
        new_scholarships = scrape_all()
    except Exception as e:
        logger.error(f"Tarama sirasinda hata: {e}")
        return

    if not new_scholarships:
        logger.info("Yeni burs bulunamadi.")
        await bot.send_message(
            chat_id=CHAT_ID,
            text=(
                f"BURS KONTROLU - {datetime.now().strftime('%d.%m.%Y')}\n\n"
                "Yeni burs veya kredi duyurusu bulunamadi.\n"
                "Bir sonraki kontrol 3 gun sonra yapilacak."
            ),
        )
        return

    message = format_message(new_scholarships)

    # Telegram mesaj limiti 4096 karakter, uzun mesajlari bol
    if len(message) <= 4096:
        await bot.send_message(chat_id=CHAT_ID, text=message)
    else:
        # Mesaji parcalara bol
        chunks = []
        current = ""
        for line in message.split("\n"):
            if len(current) + len(line) + 1 > 4000:
                chunks.append(current)
                current = line
            else:
                current += "\n" + line if current else line
        if current:
            chunks.append(current)

        for chunk in chunks:
            await bot.send_message(chat_id=CHAT_ID, text=chunk)
            await asyncio.sleep(1)

    logger.info(f"{len(new_scholarships)} yeni burs bildirimi gonderildi.")


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot baslangic komutu."""
    await update.message.reply_text(
        "Burs Botu aktif!\n\n"
        "Komutlar:\n"
        "/start - Botu baslat\n"
        "/kontrol - Simdi burs kontrolu yap\n"
        "/durum - Bot durumunu goster\n\n"
        f"Otomatik kontrol her {CHECK_INTERVAL_DAYS} gunde bir yapilir."
    )
    # Chat ID'yi goster (ilk kurulum icin faydali)
    await update.message.reply_text(
        f"Chat ID'niz: {update.effective_chat.id}\n"
        "Bu ID'yi .env dosyaniza TELEGRAM_CHAT_ID olarak ekleyin."
    )


async def cmd_kontrol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manuel burs kontrolu komutu."""
    await update.message.reply_text("Burs kontrolu yapiliyor, lutfen bekleyin...")
    await check_and_notify(context.bot)


async def cmd_durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bot durum komutu."""
    from scraper import load_seen
    seen = load_seen()
    await update.message.reply_text(
        f"Bot Durumu\n"
        f"Aktif: Evet\n"
        f"Kontrol araligi: Her {CHECK_INTERVAL_DAYS} gun\n"
        f"Kayitli burs sayisi: {len(seen)}\n"
        f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )


async def cmd_sifirla(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Gorulen burslari sifirla (tekrar bildirim almak icin)."""
    from scraper import save_seen
    save_seen(set())
    await update.message.reply_text("Burs gecmisi sifirlandi. Bir sonraki kontrolde tum burslar yeni olarak gosterilecek.")


def main():
    if not BOT_TOKEN:
        print("HATA: TELEGRAM_BOT_TOKEN ayarlanmamis!")
        print(".env dosyasina TELEGRAM_BOT_TOKEN=your_token seklinde ekleyin.")
        print("Token almak icin Telegram'da @BotFather ile konusun.")
        sys.exit(1)

    if not CHAT_ID:
        print("UYARI: TELEGRAM_CHAT_ID ayarlanmamis!")
        print("Botu baslattiktan sonra /start komutu ile Chat ID'nizi ogrenin.")
        print("Ardindan .env dosyasina TELEGRAM_CHAT_ID=id seklinde ekleyin.")

    app = Application.builder().token(BOT_TOKEN).build()

    # Komut handlerlari
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("kontrol", cmd_kontrol))
    app.add_handler(CommandHandler("durum", cmd_durum))
    app.add_handler(CommandHandler("sifirla", cmd_sifirla))

    # 3 gunluk zamanlayici
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_notify,
        trigger="interval",
        days=CHECK_INTERVAL_DAYS,
        args=[app.bot],
        next_run_time=datetime.now(),  # Ilk calistirmada hemen kontrol et
    )

    async def post_init(application):
        scheduler.start()
        logger.info(f"Zamanlayici baslatildi: her {CHECK_INTERVAL_DAYS} gunde bir kontrol.")
        if CHAT_ID:
            try:
                await application.bot.send_message(
                    chat_id=CHAT_ID,
                    text=f"Burs Botu baslatildi! Her {CHECK_INTERVAL_DAYS} gunde bir burs kontrolu yapilacak.",
                )
            except Exception as e:
                logger.warning(f"Baslangic mesaji gonderilemedi: {e}")

    app.post_init = post_init

    logger.info("Bot baslatiliyor...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
