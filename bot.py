import logging
import os
import re
import subprocess
import tempfile
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8851907428:AAGMTf9Mz0XWKvH9cP-r7Oe4CE6Fdqgpdm8")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def is_youtube(url):
    return "youtube.com" in url or "youtu.be" in url

def is_instagram(url):
    return "instagram.com" in url

def is_tiktok(url):
    return "tiktok.com" in url or "vm.tiktok.com" in url

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 Salom! Men video yuklovchi botman!\n\n"
        "Quyidagi platformalardan video havolasini yuboring:\n"
        "📺 YouTube\n"
        "📸 Instagram\n"
        "🎵 TikTok\n\n"
        "Havola yuboring — men videoni yuklab beraman!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Qanday foydalanish:\n\n"
        "1. YouTube, Instagram yoki TikTok dan video havolasini nusxa oling\n"
        "2. Shu botga yuboring\n"
        "3. Video yuklab beriladi!\n\n"
        "⚠️ Eslatma: Maxfiy (private) videolar yuklab bo'lmaydi."
    )

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    if not (is_youtube(url) or is_instagram(url) or is_tiktok(url)):
        await update.message.reply_text(
            "❌ Noto'g'ri havola!\n\n"
            "Faqat YouTube, Instagram yoki TikTok havolalarini yuboring."
        )
        return
    
    platform = "YouTube" if is_youtube(url) else "Instagram" if is_instagram(url) else "TikTok"
    msg = await update.message.reply_text(f"⏳ {platform} dan video yuklanmoqda...")
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            output_template = os.path.join(tmpdir, "%(title)s.%(ext)s")
            
            cmd = [
                "yt-dlp",
                "--no-playlist",
                "-f", "best[ext=mp4]/best",
                "--merge-output-format", "mp4",
                "-o", output_template,
            ]
            
            if is_youtube(url):
                cmd += ["--extractor-args", "youtube:player_client=android"]
            
            cmd.append(url)
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                await msg.edit_text(
                    "❌ Video yuklab bo'lmadi.\n\n"
                    "Sabab: Video maxfiy yoki cheklangan bo'lishi mumkin."
                )
                return
            
            # Find downloaded file
            files = os.listdir(tmpdir)
            if not files:
                await msg.edit_text("❌ Fayl topilmadi.")
                return
            
            video_path = os.path.join(tmpdir, files[0])
            file_size = os.path.getsize(video_path)
            size_mb = file_size / (1024 * 1024)
            
            await msg.edit_text(f"📤 Video yuborilmoqda... ({size_mb:.1f} MB)")
            
            if file_size > 50 * 1024 * 1024:
                await msg.edit_text(
                    f"⚠️ Video hajmi juda katta ({size_mb:.1f} MB).\n"
                    "Telegram 50MB gacha qabul qiladi."
                )
                return
            
            with open(video_path, "rb") as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption=f"✅ {platform} dan yuklandi!"
                )
            
            await msg.delete()
            
    except subprocess.TimeoutExpired:
        await msg.edit_text("❌ Vaqt tugadi. Qaytadan urinib ko'ring.")
    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.edit_text("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))
    logger.info("Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
