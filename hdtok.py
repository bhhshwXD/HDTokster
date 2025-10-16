import os
import logging
import asyncio
import tempfile
from pathlib import Path

from yt_dlp import YoutubeDL
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Environment variable BOT_TOKEN belum di-set.")

SEND_AS_VIDEO_MAX_BYTES = 50 * 1024 * 1024

YTDL_OPTS = {
    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
    "outtmpl": "%(id)s.%(ext)s",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "retries": 3,
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

async def run_yt_dlp(url: str, dest_dir: Path) -> list[Path]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _yt_dlp_sync, url, dest_dir)

def _yt_dlp_sync(url: str, dest_dir: Path) -> list[Path]:
    opts = YTDL_OPTS.copy()
    opts["outtmpl"] = str(dest_dir / opts.get("outtmpl", "%(id)s.%(ext)s"))
    downloaded_files = []
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if isinstance(info, dict):
                fpath = Path(ydl.prepare_filename(info))
                if fpath.exists():
                    downloaded_files.append(fpath)
                else:
                    maybe = list(Path(dest_dir).glob(f"{info.get('id', '*')}.*"))
                    downloaded_files.extend(maybe)
            elif isinstance(info, list):
                for entry in info:
                    fpath = Path(ydl.prepare_filename(entry))
                    if fpath.exists():
                        downloaded_files.append(fpath)
    except Exception as e:
        logger.exception("yt-dlp failed: %s", e)
    return downloaded_files

def human_readable_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024.0:
            return f"{n:3.1f}{unit}"
        n /= 1024.0
    return f"{n:.1f}TB"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Halo! Kirim link TikTok (video atau foto/slideshow) ke saya, "
        "saya akan mendownload dan mengirimkannya kembali.\n\n"
        "Contoh: https://www.tiktok.com/@username/video/1234567890\n\n"
        "Catatan: hanya untuk konten yang Anda berhak download."
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start untuk instruksi.\nKirimkan link TikTok di chat.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    text = (msg.text or "").strip()
    if not text:
        await msg.reply_text("Kirim link TikTok (text).")
        return

    await msg.reply_text("Menerima link, mulai proses download... ⏳")

    with tempfile.TemporaryDirectory() as td:
        dest = Path(td)
        logger.info("Downloading %s into %s", text, td)
        files = await run_yt_dlp(text, dest)
        if not files:
            await msg.reply_text("Gagal mendownload. Pastikan link TikTok valid dan dapat diakses.")
            return

        for file_path in files:
            file_size = file_path.stat().st_size
            caption = f"Diunduh dari TikTok — ukuran {human_readable_size(file_size)}"

            try:
                suffix = file_path.suffix.lower()
                if suffix in {".mp4", ".mov", ".mkv"} and file_size <= SEND_AS_VIDEO_MAX_BYTES:
                    await msg.reply_video(video=open(file_path, "rb"), caption=caption)
                elif suffix in {".jpg", ".jpeg", ".png"}:
                    await msg.reply_photo(photo=open(file_path, "rb"), caption=caption)
                else:
                    await msg.reply_document(document=open(file_path, "rb"), caption=caption)
            except Exception as e:
                logger.exception("Failed to send file: %s", e)
                await msg.reply_text(f"Gagal mengirim file {file_path.name}.")
        
        await msg.reply_text("Selesai ✅")

async def error_handler(update: Update | None, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Update error: %s", context.error)
    if update and update.effective_message:
        try:
            await update.effective_message.reply_text("Terjadi kesalahan internal. Coba lagi nanti.")
        except Exception:
            pass

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    logger.info("Bot starting...")
    app.run_polling(allowed_updates=["message"])

if __name__ == "__main__":
    main()
