import logging
import os
import subprocess
import tempfile
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import BadRequest

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8851907428:AAGMTf9Mz0XWKvH9cP-r7Oe4CE6Fdqgpdm8")
CHANNEL_USERNAME = "@vakhidovv700"
CHANNEL_LINK = "https://t.me/vakhidovv700"

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

async def check_subscription(user_id, context):
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except BadRequest:
        return False
    except Exception as e:
        logger.error(f"Subscription check error: {e}")
        return False

def get_subscribe_keyboard():
    keyboard = [
        [InlineKeyboardButton("📢 Kanalga obuna bo'lish", url=CHANNEL_LINK)],
        [InlineKeyboardButton("✅ Obuna bo'ldim", callback_data="check_sub")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_subscribed = await check_subscription(user_id, context)
    
    if not is_subscribed:
        await update.message.reply_text(
            "👋 Salom! Botdan foydalanish uchun avval kanalimizga obuna bo'ling:\n\n"
            "Obuna bo'lgandan keyin '✅ Obuna bo'ldim' tugmasini bosing.",
            reply_markup=get_subscribe_keyboard()
        )
        return
    
    await update.message.reply_text(
        "🎬 Salom! Men video yuklovchi botman!\n\n"
        "Quyidagi platformalardan video havolasini yuboring:\n"
        "📺 YouTube\n"
        "📸 Instagram\n"
        "🎵 TikTok\n\n"
        "Men sizga videoni HAM, uning musiqasini (MP3) HAM yuborib beraman!"
    )

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    is_subscribed = await check_subscription(user_id, context)
    
    if is_subscribed:
        await query.edit_message_text(
            "✅ Rahmat! Endi botdan foydalanishingiz mumkin.\n\n"
            "🎬 YouTube, Instagram yoki TikTok havolasini yuboring!"
        )
    else:
        await query.answer("❌ Siz hali obuna bo'lmagansiz!", show_alert=True)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ Qanday foydalanish:\n\n"
        "1. YouTube, Instagram yoki TikTok dan video havolasini nusxa oling\n"
        "2. Shu botga yuboring\n"
        "3. Sizga video VA uning musiqasi (mp3) yuboriladi!\n\n"
        "⚠️ Eslatma: Maxfiy (private) videolar yuklab bo'lmaydi."
    )

async def download_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_subscribed = await check_subscription(user_id, context)
    
    if not is_subscribed:
        await update.message.reply_text(
            "❌ Botdan foydalanish uchun avval kanalimizga obuna bo'ling:",
            reply_markup=get_subscribe_keyboard()
        )
        return
    
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
            output_template = os.path.join(tmpdir, "media.%(ext)s")
            
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
            
            files = [f for f in os.listdir(tmpdir) if f.startswith("media.")]
            if not files:
                await msg.edit_text("❌ Fayl topilmadi.")
                return
            
            video_path = os.path.join(tmpdir, files[0])
            file_size = os.path.getsize(video_path)
            size_mb = file_size / (1024 * 1024)
            
            if file_size > 50 * 1024 * 1024:
                await msg.edit_text(
                    f"⚠️ Video hajmi juda katta ({size_mb:.1f} MB).\n"
                    "Telegram 50MB gacha qabul qiladi."
                )
                return
            
            # Send video first
            await msg.edit_text(f"📤 Video yuborilmoqda... ({size_mb:.1f} MB)")
            with open(video_path, "rb") as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption=f"✅ {platform} dan video yuklandi!"
                )
            
            # Now extract audio as MP3
            await msg.edit_text("🎵 Musiqa (MP3) ajratilmoqda...")
            audio_path = os.path.join(tmpdir, "audio.mp3")
            
            extract_cmd = [
                "ffmpeg", "-i", video_path,
                "-vn", "-acodec", "libmp3lame", "-q:a", "2",
                "-y", audio_path
            ]
            
            audio_result = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=60)
            
            if audio_result.returncode == 0 and os.path.exists(audio_path):
                audio_size = os.path.getsize(audio_path)
                audio_size_mb = audio_size / (1024 * 1024)
                
                if audio_size <= 50 * 1024 * 1024:
                    with open(audio_path, "rb") as audio_file:
                        await update.message.reply_audio(
                            audio=audio_file,
                            caption=f"🎵 Musiqa (MP3) - {platform}",
                            title=f"{platform} audio"
                        )
                    await msg.delete()
                else:
                    await msg.edit_text(f"✅ Video yuborildi! (Audio juda katta: {audio_size_mb:.1f}MB)")
            else:
                await msg.edit_text("✅ Video yuborildi! (Audio ajratib bo'lmadi)")
            
    except subprocess.TimeoutExpired:
        await msg.edit_text("❌ Vaqt tugadi. Qaytadan urinib ko'ring.")
    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.edit_text("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))
    logger.info("Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
