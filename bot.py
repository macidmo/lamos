"""
Telegram Media Forwarder Bot
يسحب الصور والفيديوهات من قناة محمية وينشرها بقناتك
الميزات: تجنب التكرار + وضع الصمت + مخزون احتياطي
"""

import asyncio
import os
import json
import logging
import random
from datetime import datetime, timezone
from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument
from telethon.tl.functions.channels import JoinChannelRequest

load_dotenv()

# ===================== الإعدادات =====================
API_ID       = int(os.environ.get("API_ID", "0"))
API_HASH     = os.environ.get("API_HASH", "")
PHONE        = os.environ.get("PHONE", "")
TWO_FA       = os.environ.get("TWO_FA_PASSWORD", "")

def parse_channel(value):
    """يحول القيمة لعدد صحيح إذا كانت رقم قناة (مثل -100xxxxxxxxxx)،
    أو يرجعها كـ username/رابط لو ما كانت رقم بحت."""
    if not value:
        return value
    try:
        return int(value)
    except (ValueError, TypeError):
        return value

SOURCE_CHANNEL = parse_channel(os.environ.get("SOURCE_CHANNEL", ""))
TARGET_CHANNEL = parse_channel(os.environ.get("TARGET_CHANNEL", ""))

# القناة الاحتياطية (تُستخدم لو القناة المصدر صمتت يومين)
BACKUP_CHANNEL = parse_channel(os.environ.get("BACKUP_CHANNEL", "0"))
# كم ساعة صمت قبل النشر من الاحتياطي
SILENCE_HOURS = int(os.environ.get("SILENCE_HOURS", "48"))

# رقم حسابك الشخصي على تلغرام (لاستقبال أوامر الإيقاف/التشغيل)
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "")

# القناة الثانية — مصدر وهدف
SOURCE_CHANNEL_2 = os.environ.get("SOURCE_CHANNEL_2", "@badgirl_reislin")
TARGET_CHANNEL_2 = os.environ.get("TARGET_CHANNEL_2", "@bad_reislin")

# ملف حفظ الرسائل المنشورة للقناة الثانية
POSTED_FILE_2 = "posted_ids_2.json"

# ملف حفظ الرسائل المنشورة
POSTED_FILE = "posted_ids.json"
# ======================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

client = TelegramClient("session", API_ID, API_HASH)

# حالة البوت — True = يعمل، False = متوقف مؤقتاً
is_active = True

# آخر وقت نُشر فيه من القناة المصدر
last_source_post = datetime.now(timezone.utc)


# =================== تجنب التكرار ===================

def load_posted_ids():
    """تحميل IDs الرسائل المنشورة مسبقاً"""
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_posted_id(msg_id):
    """حفظ ID رسالة تم نشرها"""
    posted_ids.add(msg_id)
    with open(POSTED_FILE, "w") as f:
        json.dump(list(posted_ids), f)

posted_ids = load_posted_ids()

def load_posted_ids_2():
    """تحميل IDs الرسائل المنشورة للقناة الثانية"""
    if os.path.exists(POSTED_FILE_2):
        with open(POSTED_FILE_2, "r") as f:
            return set(json.load(f))
    return set()

def save_posted_id_2(msg_id):
    """حفظ ID رسالة تم نشرها للقناة الثانية"""
    posted_ids_2.add(msg_id)
    with open(POSTED_FILE_2, "w") as f:
        json.dump(list(posted_ids_2), f)

posted_ids_2 = load_posted_ids_2()
scrape_done = os.path.exists("scrape_done.flag")
# =====================================================


def is_media(message):
    """تحقق إذا كانت الرسالة صورة أو فيديو فقط"""
    if not message.media:
        return False
    if isinstance(message.media, MessageMediaPhoto):
        return True
    if isinstance(message.media, MessageMediaDocument):
        mime = getattr(message.media.document, "mime_type", "") or ""
        if mime.startswith("video/") or mime.startswith("image/"):
            return True
    return False


async def send_media(message):
    """تنزيل الميديا ونشرها بالقناة الهدف"""
    try:
        file_path = await client.download_media(message.media)
        logger.info(f"⬇️ تم التنزيل: {file_path}")

        is_video = isinstance(file_path, str) and any(
            file_path.lower().endswith(ext)
            for ext in [".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"]
        )
        await client.send_file(
            TARGET_CHANNEL,
            file_path,
            caption="",
            supports_streaming=is_video,
            force_document=False
        )
        logger.info("✅ تم النشر بنجاح!")

        # حفظ ID الرسالة لتجنب التكرار
        posted_ids.add(message.id)
        save_posted_id(message.id)

        if os.path.exists(file_path):
            os.remove(file_path)

    except Exception as e:
        logger.error(f"❌ خطأ أثناء النشر: {e}")


async def send_media_2(message):
    """تنزيل الميديا ونشرها بالقناة الهدف الثانية"""
    try:
        file_path = await client.download_media(message.media)
        logger.info(f"⬇️ [قناة2] تم التنزيل: {file_path}")

        is_video = isinstance(file_path, str) and any(
            file_path.lower().endswith(ext)
            for ext in [".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"]
        )
        await client.send_file(
            TARGET_CHANNEL_2,
            file_path,
            caption="",
            supports_streaming=is_video,
            force_document=False
        )
        logger.info("✅ [قناة2] تم النشر بنجاح!")

        posted_ids_2.add(message.id)
        save_posted_id_2(message.id)

        if os.path.exists(file_path):
            os.remove(file_path)

    except Exception as e:
        logger.error(f"❌ [قناة2] خطأ أثناء النشر: {e}")


# =================== مراقبة القناة ===================

@client.on(events.NewMessage(chats=SOURCE_CHANNEL))
async def handler(event):
    """يراقب الرسائل الجديدة تلقائياً"""
    global is_active
    message = event.message

    # تجاهل لو البوت متوقف
    if not is_active:
        logger.info("⏸️ البوت متوقف مؤقتاً، تم تجاهل الرسالة")
        return

    # تجنب التكرار
    if message.id in posted_ids:
        logger.info(f"⚠️ رسالة {message.id} منشورة مسبقاً، تم تجاهلها")
        return

    if not is_media(message):
        return

    global last_source_post
    logger.info("🆕 ميديا جديدة وصلت!")
    last_source_post = datetime.now(timezone.utc)
    await send_media(message)


@client.on(events.NewMessage(chats=SOURCE_CHANNEL_2))
async def handler_2(event):
    """يراقب الرسائل الجديدة من القناة الثانية"""
    message = event.message

    if not is_active:
        return

    if message.id in posted_ids_2:
        logger.info(f"⚠️ [قناة2] رسالة {message.id} منشورة مسبقاً")
        return

    if not is_media(message):
        return

    logger.info("🆕 [قناة2] ميديا جديدة وصلت!")
    await send_media_2(message)


# =================== وضع الصمت ===================

@client.on(events.NewMessage(chats=ADMIN_USERNAME if ADMIN_USERNAME else "me", pattern=r"(?i)^(stop|pause|وقف)$"))
async def pause_bot(event):
    """إيقاف البوت مؤقتاً بأمر منك"""
    global is_active
    is_active = False
    await event.respond("⏸️ تم إيقاف البوت مؤقتاً. أرسل 'start' أو 'شغل' لتشغيله.")
    logger.info("⏸️ البوت متوقف بأمر المدير")

@client.on(events.NewMessage(chats=ADMIN_USERNAME if ADMIN_USERNAME else "me", pattern=r"(?i)^(start|resume|شغل)$"))
async def resume_bot(event):
    """تشغيل البوت مجدداً بأمر منك"""
    global is_active
    is_active = True
    await event.respond("▶️ تم تشغيل البوت! يراقب القناة الآن.")
    logger.info("▶️ البوت يعمل بأمر المدير")

@client.on(events.NewMessage(chats=ADMIN_USERNAME if ADMIN_USERNAME else "me", pattern=r"(?i)^(status|حالة)$"))
async def bot_status(event):
    """اعرف حالة البوت"""
    state = "▶️ يعمل" if is_active else "⏸️ متوقف مؤقتاً"
    count = len(posted_ids)
    await event.respond(f"حالة البوت: {state}\nعدد الرسائل المنشورة: {count}")
# =====================================================



# =================== المخزون الاحتياطي ===================

async def post_from_backup():
    """ينشر رسالة عشوائية من القناة الاحتياطية"""
    try:
        # جمع كل الرسائل الميديا من القناة الاحتياطية
        available = []
        async for message in client.iter_messages(BACKUP_CHANNEL):
            if is_media(message) and message.id not in posted_ids:
                available.append(message)

        if not available:
            logger.warning("⚠️ المخزون الاحتياطي خلص!")
            admin = ADMIN_USERNAME if ADMIN_USERNAME else "me"
            await client.send_message(admin, "⚠️ تنبيه: المخزون الاحتياطي خلص! أضف محتوى جديد للقناة الاحتياطية.")
            return

        # اختيار رسالة عشوائية
        message = random.choice(available)
        logger.info(f"📦 نشر من المخزون الاحتياطي ID: {message.id}")
        await send_media(message)

    except Exception as e:
        logger.error(f"❌ خطأ بالمخزون الاحتياطي: {e}")


async def backup_scheduler():
    """يفحص كل 30 دقيقة إذا القناة صامتة ويقرر النشر من الاحتياطي"""
    # انتظر ساعة بعد التشغيل قبل ما يبدأ يفحص
    await asyncio.sleep(3600)

    while True:
        now = datetime.now(timezone.utc)
        hours_silent = (now - last_source_post).total_seconds() / 3600

        if hours_silent >= SILENCE_HOURS and is_active:
            logger.info(f"⏰ القناة المصدر صامتة {hours_silent:.1f} ساعة — نشر من الاحتياطي")
            await post_from_backup()
            # انتظر 12 ساعة قبل المرة الثانية
            await asyncio.sleep(43200)
        else:
            # فحص كل 30 دقيقة
            await asyncio.sleep(1800)

# =====================================================

async def main():
    logger.info("🚀 جاري تشغيل البوت...")

    await client.start(phone=PHONE, password=lambda: TWO_FA if TWO_FA else None)
    logger.info("✅ تم تسجيل الدخول بنجاح!")

    # الانضمام للقناة المصدر
    try:
        await client(JoinChannelRequest(SOURCE_CHANNEL))
        logger.info(f"✅ تم الانضمام لـ {SOURCE_CHANNEL}")
    except Exception as e:
        logger.info(f"ℹ️ {e}")

    # الانضمام للقناة الثانية
    try:
        await client(JoinChannelRequest(SOURCE_CHANNEL_2))
        logger.info(f"✅ تم الانضمام لـ {SOURCE_CHANNEL_2}")
    except Exception as e:
        logger.info(f"ℹ️ {e}")

    # نسخ المحتوى القديم من القناة الثانية (مرة وحدة فقط)
    global scrape_done
    if not scrape_done:
        logger.info("📦 [قناة2] جاري نسخ المحتوى القديم...")
        count = 0
        async for message in client.iter_messages(SOURCE_CHANNEL_2, reverse=True):
            if is_media(message) and message.id not in posted_ids_2:
                await send_media_2(message)
                count += 1
                await asyncio.sleep(3)
        logger.info(f"✅ [قناة2] تم نسخ {count} ملف")
        open("scrape_done.flag", "w").write("done")
        scrape_done = True

    # تشغيل مراقب المخزون الاحتياطي بالخلفية
    asyncio.ensure_future(backup_scheduler())

    logger.info(f"👂 يراقب {SOURCE_CHANNEL} → ينشر في {TARGET_CHANNEL}")
    logger.info(f"💬 أرسل 'stop' لإيقاف البوت أو 'start' لتشغيله أو 'status' لمعرفة حالته")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())