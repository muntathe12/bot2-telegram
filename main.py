#!/usr/bin/env python3
import asyncio
import logging
import os
import signal
import sys
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    PicklePersistence,
)
from telegram.error import TelegramError, Conflict

# إعداد التسجيل (Logging)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# إعدادات البوت
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN ليس محددًا في متغيرات البيئة")
    sys.exit(1)

# مسار ملف الجلسة لمنع التشغيل المتزامن
SESSION_FILE = "bot_session.lock"


class TelegramBot:
    def __init__(self):
        self.application: Optional[Application] = None
        self.event_loop = None
        self.shutdown_event = asyncio.Event()

    def check_existing_session(self) -> bool:
        """فحص إذا كانت هناك جلسة أخرى تعمل"""
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, "r") as f:
                    pid = int(f.read().strip())
                # فحص إذا كان العملية لا تزال قيد التشغيل
                try:
                    os.kill(pid, 0)
                    logger.warning(f"تم العثور على جلسة أخرى تعمل برقم العملية: {pid}")
                    return True
                except OSError:
                    # العملية غير موجودة، يمكننا حذف الملف
                    os.remove(SESSION_FILE)
                    return False
            except (ValueError, OSError) as e:
                logger.warning(f"خطأ في قراءة ملف الجلسة: {e}")
                if os.path.exists(SESSION_FILE):
                    os.remove(SESSION_FILE)
                return False
        return False

    def create_session_file(self):
        """إنشاء ملف الجلسة مع رقم العملية الحالي"""
        with open(SESSION_FILE, "w") as f:
            f.write(str(os.getpid()))

    def remove_session_file(self):
        """إزالة ملف الجلسة"""
        if os.path.exists(SESSION_FILE):
            os.remove(SESSION_FILE)

    async def start(self):
        """بدء تشغيل البوت"""
        # فحص إذا كانت هناك جلسة أخرى تعمل
        if self.check_existing_session():
            logger.error("هناك جلسة أخرى من نفس البوت تعمل بالفعل. يرجى إغلاقها أولاً.")
            return False

        # إنشاء ملف الجلسة
        self.create_session_file()

        try:
            logger.info("جاري بدء تشغيل البوت...")

            # إنشاء Application مع التأكد من عدم استخدام Webhook
            self.application = (
                Application.builder()
                .token(BOT_TOKEN)
                .persistence(PicklePersistence("persistence"))
                .build()
            )

            # إلغاء الـ webhook إذا كان موجودًا
            try:
                await self.application.bot.delete_webhook()
                logger.info("تم إلغاء الـ webhook بنجاح")
            except Exception as e:
                logger.warning(f"فشل في إلغاء الـ webhook أو لم يكن موجودًا: {e}")

            # إضافة المعالجات (Handlers)
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            self.application.add_error_handler(self.error_handler)

            # بدء الـ polling
            logger.info("بدء الـ polling...")
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(drop_pending_updates=True)

            logger.info("البوت يعمل الآن...")

            # انتظر حتى يتم إشارة الإغلاق
            await self.shutdown_event.wait()
            return True

        except Conflict as e:
            logger.error(f"خطأ في الاتصال: {e}. قد يكون هناك بوت آخر يستخدم نفس التوكن.")
            self.remove_session_file()
            return False
        except Exception as e:
            logger.error(f"حدث خطأ غير متوقع أثناء بدء تشغيل البوت: {e}")
            self.remove_session_file()
            return False

    async def stop(self):
        """إيقاف تشغيل البوت بشكل نظيف"""
        logger.info("جاري إيقاف البوت...")
        self.shutdown_event.set()

        if self.application:
            try:
                # إيقاف الـ updater
                if hasattr(self.application, 'updater') and self.application.updater:
                    await self.application.updater.stop()

                # إيقاف Application
                await self.application.stop()
                await self.application.shutdown()
                logger.info("تم إيقاف البوت بنجاح")
            except Exception as e:
                logger.error(f"حدث خطأ أثناء إيقاف البوت: {e}")

        self.remove_session_file()

    # أوامر البوت
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text("مرحباً! أنا بوت تيليجرام الجديد. كيف يمكنني مساعدتك؟")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = update.message.text
        response = f"لقد تلقيت رسالتك: {text}"
        await update.message.reply_text(response)

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """معالجة الأخطاء"""
        logger.error(f"Update {update} caused error {context.error}")

        # محاولة إرسال رسالة للمستخدم في حالة حدوث خطأ
        if update and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "عذراً، حدث خطأ أثناء معالجة طلبك. يرجى المحاولة مرة أخرى لاحقاً."
                )
            except Exception as e:
                logger.error(f"فشل في إرسال رسالة الخطأ للمستخدم: {e}")


def setup_event_loop():
    """إعداد حلقة الأحداث (Event Loop) بشكل صحيح"""
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop


def signal_handler(signum, frame):
    """معالجة إشارات الإغلاق"""
    logger.info(f"تم استلام إشارة الإغلاق: {signum}")
    if hasattr(signal_handler, 'bot_instance'):
        asyncio.create_task(signal_handler.bot_instance.stop())
    signal_handler.stop_event.set()


async def main():
    """الدالة الرئيسية لتشغيل البوت"""
    bot = TelegramBot()
    signal_handler.bot_instance = bot
    signal_handler.stop_event = asyncio.Event()

    # تسجيل معالجات الإشارات
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("تم إيقاف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"حدث خطأ غير متوقع في الدالة الرئيسية: {e}")
    finally:
        await bot.stop()


if __name__ == "__main__":
    loop = setup_event_loop()

    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.info("تم إيقاف البوت بواسطة المستخدم")
    except Exception as e:
        logger.error(f"حدث خطأ غير متوقع: {e}")
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception as e:
            logger.error(f"حدث خطأ أثناء إغلاق الـ asyncgens: {e}")

        try:
            loop.close()
        except Exception as e:
            logger.error(f"حدث خطأ أثناء إغلاق حلقة الأحداث: {e}")