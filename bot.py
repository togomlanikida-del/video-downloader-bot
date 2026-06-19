import logging
import os
import secrets
import subprocess
import tempfile
import threading
import time
from flask import Flask, send_file, abort
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import BadRequest

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8851907428:AAGMTf9Mz0XWKvH9cP-r7Oe4CE6Fdqgpdm8")
CHANNEL_USERNAME = "@vakhidovv700"
CHANNEL_LINK = "https://t.me/vakhidovv700"

# Railway gives a public domain via RAILWAY_PUBLIC_DOMAIN or RAILWAY_STATIC_URL
PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
PORT = int(os.environ.get("PORT", 8080))

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------- Tiny file server for serving large videos to Telegram ----------
flask_app = Flask(__name__)
FILE_STORE = {}  # token -> (filepath, expiry_timestamp)

@flask_app.route("/file/<token>")
def serve_file(token):
    entry = FILE_STORE.get(token)
    if not entry:
        abort(404)
    filepath, expiry = entry
    if time.time() > expiry or not os.path.exists(filepath):
        abort(404)
    return send_file(filepath, mimetype="video/mp4", as_attachment=True, download_name="video.mp4")

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)

def register_temp_file(filepath, ttl_seconds=600):
    token = secrets.token_urlsafe(16)
    FILE_STORE[token] = (filepath, time.time() + ttl_seconds)
    return token

def cleanup_expired_files():
    while True:
        time.sleep(60)
        now = time.time()
        expired = [t for t, (_, exp) in FILE_STORE.items() if now > exp]
        for t in expired:
            FILE_STORE.pop(t, None)

# ---------- Bot logic ----------

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
        "Men sizga videoni HAM, uning musiqasini (MP3) HAM yuborib beraman!\n"
        "Katta hajmli videolarni ham yuklab beraman! 🚀"
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
    
    tmpdir = tempfile.mkdtemp()
    try:
        output_template = os.path.join(tmpdir, "media.%(ext)s")
        
        base_cmd = [
            "yt-dlp",
            "--no-playlist",
            "-f", "best[ext=mp4]/best",
            "--merge-output-format", "mp4",
            "-o", output_template,
        ]
        
        result = None
        if is_youtube(url):
            # Try multiple client strategies for YouTube/Shorts
            client_strategies = ["android", "ios", "web", "tv_embedded"]
            for client in client_strategies:
                cmd = base_cmd + ["--extractor-args", f"youtube:player_client={client}", url]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                if result.returncode == 0:
                    break
                # clean up any partial files between attempts
                for f in os.listdir(tmpdir):
                    try:
                        os.remove(os.path.join(tmpdir, f))
                    except OSError:
                        pass
        else:
            cmd = base_cmd + [url]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result is None or result.returncode != 0:
            error_detail = result.stderr[-300:] if result else "unknown"
            logger.error(f"yt-dlp failed for {url}: {error_detail}")
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
        
        await msg.edit_text(f"📤 Video yuborilmoqda... ({size_mb:.1f} MB)")
        
        # If file is small enough, send directly via bot API
        if file_size <= 49 * 1024 * 1024:
            with open(video_path, "rb") as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption=f"✅ {platform} dan video yuklandi!"
                )
        else:
            # Large file: serve via public URL, Telegram fetches it directly (up to ~2GB)
            if not PUBLIC_DOMAIN:
                await msg.edit_text(
                    f"⚠️ Video hajmi katta ({size_mb:.1f} MB) va serverda public domen sozlanmagan."
                )
                return
            
            token = register_temp_file(video_path, ttl_seconds=900)
            file_url = f"https://{PUBLIC_DOMAIN}/file/{token}"
            
            try:
                await update.message.reply_video(
                    video=file_url,
                    caption=f"✅ {platform} dan video yuklandi! ({size_mb:.1f} MB)"
                )
            except Exception as e:
                logger.error(f"Large video send error: {e}")
                await msg.edit_text(
                    f"❌ Katta hajmli videoni yuborishda xatolik yuz berdi ({size_mb:.1f} MB)."
                )
                return
        
        # Now extract audio as MP3
        await msg.edit_text("🎵 Musiqa (MP3) ajratilmoqda...")
        audio_path = os.path.join(tmpdir, "audio.mp3")
        
        extract_cmd = [
            "ffmpeg", "-i", video_path,
            "-vn", "-acodec", "libmp3lame", "-q:a", "2",
            "-y", audio_path
        ]
        
        audio_result = subprocess.run(extract_cmd, capture_output=True, text=True, timeout=120)
        
        if audio_result.returncode == 0 and os.path.exists(audio_path):
            audio_size = os.path.getsize(audio_path)
            audio_size_mb = audio_size / (1024 * 1024)
            
            if audio_size <= 49 * 1024 * 1024:
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
            await msg.edit_text("✅ Video yuborildi!")
            
    except subprocess.TimeoutExpired:
        await msg.edit_text("❌ Vaqt tugadi. Qaytadan urinib ko'ring.")
    except Exception as e:
        logger.error(f"Error: {e}")
        await msg.edit_text("❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.")
    finally:
        # Clean up after a delay to allow Telegram to fetch large files first
        def delayed_cleanup():
            time.sleep(900)
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)
        threading.Thread(target=delayed_cleanup, daemon=True).start()

def main():
    # Start Flask file server in background
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=cleanup_expired_files, daemon=True).start()
    
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_video))
    logger.info("Bot ishga tushdi!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
