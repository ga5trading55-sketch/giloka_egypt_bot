import os
import re
import logging
from datetime import datetime, timedelta, timezone
from flask import Flask
from threading import Thread
from supabase import create_client, Client
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- إعداد خادم Flask ---
server = Flask('')

@server.route('/')
def home():
    return "Bot is Live and Running!"

def run():
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# --- إعداد بيانات المتغيرات ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# ضع هنا معرف حسابك الرئيسي كـ أدمن للتحكم بالإشتراكات
ADMIN_ID = 1957078158  

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "أهلاً بك! 👋\n\n"
        "يمكنك إدارة الأسئلة والردود التلقائية الخاصة بك بسهولة في أي وقت:\n\n"
        "➕ **لإضافة أو تغيير رد:**\n"
        "`اضف: الكلمة = الرد الجديد`\n"
        "*(مثال: `اضف: السعر = سعر التوصيل 5000 دينار`)*\n\n"
        "📋 **لنعرض لك كل كلماتك والردود:**\n"
        "/list\n\n"
        "❌ **لحذف سؤال ورد معين:**\n"
        "`حذف: الكلمة`\n"
        "*(مثال: `حذف: السعر`)*\n\n"
        "🆔 **لمعرفة الآيدي الخاص بك:** /id"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    await update.message.reply_text(f"🆔 الـ ID الخاص بك هو:\n`{user_id}`", parse_mode="Markdown")

async def list_replies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = update.message.chat_id
    try:
        response = supabase.table("custom_replies").select("keyword, reply_text").eq("owner_id", owner_id).execute()
        
        if not response.data:
            await update.message.reply_text("لا توجد لديك أسئلة أو ردود مسجلة حالياً.")
            return

        text = "📋 **قائمة الأسئلة والردود الخاصة بك:**\n\n"
        for item in response.data:
            text += f"🔹 **السؤال/الكلمة:** `{item['keyword']}`\n💬 **الرد:** {item['reply_text']}\n-------------------\n"
        
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ في جلب القائمة:\n`{str(e)}`", parse_mode="Markdown")

# --- أوامر الأدمن لإدارة المشتركين ---

async def add_subscriber_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    if user_id != ADMIN_ID:
        return

    try:
        # /add USER_ID DAYS NAME
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("⚠️ طريقة الاستخدام الصحيحة:\n`/add [USER_ID] [DAYS] [NAME]`\n\nمثال:\n`/add 8913199795 30 علي`", parse_mode="Markdown")
            return

        sub_id = int(args[0])
        days = int(args[1])
        sub_name = " ".join(args[2:]) if len(args) > 2 else "مشترك"

        expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

        data = {
            "owner_id": sub_id,
            "name": sub_name,
            "expires_at": expires_at
        }

        supabase.table("subscribers").upsert(data, on_conflict="owner_id").execute()
        await update.message.reply_text(
            f"✅ **تمت إضافة/تمديد الاشتراك بنجاح!**\n\n"
            f"👤 **الاسم:** {sub_name}\n"
            f"🆔 **الآيدي:** `{sub_id}`\n"
            f"📅 **المدة:** {days} يوم\n"
            f"⏳ **ينتهي في:** `{expires_at[:10]}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ أثناء إضافة المشترك:\n`{str(e)}`", parse_mode="Markdown")

async def delete_subscriber_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    if user_id != ADMIN_ID:
        return

    try:
        args = context.args
        if not args:
            await update.message.reply_text("⚠️ يرجى كتابة الآيدي المراد حذفه:\n`/sub_delete 8913199795`", parse_mode="Markdown")
            return

        sub_id = int(args[0])
        supabase.table("subscribers").delete().eq("owner_id", sub_id).execute()
        await update.message.reply_text(f"🗑️ تم إلغاء اشتراك المشترك صاحب الآيدي `{sub_id}` بنجاح.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ أثناء الحذف:\n`{str(e)}`", parse_mode="Markdown")

# --- معالجة الرسائل الرئيسية ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    raw_text = update.message.text or update.message.caption
    if not raw_text:
        return

    raw_text = raw_text.strip()
    owner_id = update.message.chat_id

    # --- 1. فحص الاشتراك وتاريخ الانتهاء ---
    try:
        sub_response = supabase.table("subscribers").select("expires_at").eq("owner_id", owner_id).execute()
        
        # إذا لم يكن المستخدم مضافاً في جدول المشتركين
        if not sub_response.data:
            await update.message.reply_text("❌ عذراً، أنت غير مشترك في الخدمة. يرجى التواصل مع الإدارة للتفعيل.")
            return

        # التحقق من أن الاشتراك لم ينتهِ بعد
        expires_at_str = sub_response.data[0]["expires_at"]
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)

        if now > expires_at:
            await update.message.reply_text("⚠️ انتهت فترة اشتراكك في الخدمة. يرجى تجديد الاشتراك للاستمرار.")
            return

    except Exception as e:
        print(f"Error checking subscription: {e}")
        await update.message.reply_text("❌ حدث خطأ أثناء التحقق من اشتراكك.")
        return

    # --- 2. إضافة أو تعديل رد ---
    if raw_text.startswith("اضف:") or raw_text.startswith("أضف:"):
        content = raw_text.split(":", 1)[1]
        if "=" in content:
            keyword, reply_text = content.split("=", 1)
            keyword = keyword.strip().lower()
            reply_text = reply_text.strip()

            if not keyword or not reply_text:
                await update.message.reply_text("⚠️ يرجى كتابة الكلمة والرد بشكل صحيح.")
                return

            try:
                data = {
                    "owner_id": owner_id,
                    "keyword": keyword,
                    "reply_text": reply_text
                }
                supabase.table("custom_replies").upsert(data, on_conflict="owner_id, keyword").execute()
                await update.message.reply_text(f"✅ تم حفظ / تغيير الرد بنجاح!\n\n🔹 الكلمة: `{keyword}`\n💬 الرد: {reply_text}", parse_mode="Markdown")
            except Exception as e:
                await update.message.reply_text(f"❌ خطأ أثناء الحفظ في قاعدة البيانات:\n`{str(e)}`", parse_mode="Markdown")
            return
        else:
            await update.message.reply_text("⚠️ اكتب الأمر بهذا الشكل:\n`اضف: الكلمة = الرد`", parse_mode="Markdown")
            return

    # --- 3. حذف رد ---
    if raw_text.startswith("حذف:"):
        keyword = raw_text.split(":", 1)[1].strip().lower()
        if keyword:
            try:
                supabase.table("custom_replies").delete().eq("owner_id", owner_id).eq("keyword", keyword).execute()
                await update.message.reply_text(f"🗑️ تم حذف الكلمة `{keyword}` بنجاح.", parse_mode="Markdown")
            except Exception as e:
                await update.message.reply_text(f"❌ خطأ أثناء الحذف:\n`{str(e)}`", parse_mode="Markdown")
            return

    # --- 4. الرد التلقائي عند مطابقة الكلمة ---
    text_clean = raw_text.lower()
    try:
        response = supabase.table("custom_replies").select("keyword, reply_text").eq("owner_id", owner_id).execute()
        if response.data:
            for item in response.data:
                kw = item["keyword"].lower()
                pattern = r'(^|[^\w\u0600-\u06FF])' + re.escape(kw) + r'($|[^\w\u0600-\u06FF])'
                if re.search(pattern, text_clean):
                    await update.message.reply_text(item["reply_text"])
                    break
    except Exception as e:
        print(f"Error fetching reply: {e}")

if __name__ == "__main__":
    keep_alive()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # الأوامر العامة
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", get_id))
    app.add_handler(CommandHandler("list", list_replies))
    
    # أوامر الأدمن
    app.add_handler(CommandHandler("add", add_subscriber_cmd))
    app.add_handler(CommandHandler("sub_delete", delete_subscriber_cmd))
    
    # معالجة الرسائل
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(drop_pending_updates=True)
