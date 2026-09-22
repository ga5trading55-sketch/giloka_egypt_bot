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

# --- إعداد البيانات والمتغيرات ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

ADMIN_ID = 1957078158  # معرف المالك الرئيسي المطلق للنظام

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- دالة التحقق من صلاحية الإدارة أو المالك المطلق ---
def is_authorized_admin(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    try:
        # الفحص من جدول المدراء لبقية المستويات
        mgr_resp = supabase.table("managers").select("expires_at").eq("manager_id", user_id).execute()
        if mgr_resp.data:
            return True
    except Exception:
        pass
    return False

# --- 1. أمر Start والرابط الخاص بكل مشترك ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    bot_info = await context.bot.get_me()
    
    # فحص إذا كان المستخدم هو المالك المطلق
    if user_id == ADMIN_ID:
        msg = (
            f"👑 **أهلاً بك يا مالك النظام!**\n\n"
            f"🛠 **أوامر التحكم بالمشتركين:**\n"
            f"• لإضافة/تجديد مشترك: `/add [ID] [DAYS] [NAME]`\n"
            f"• لحذف مشترك: `/del_sub [ID]`\n\n"
            f"🛠 **أوامر التحكم بالمدراء:**\n"
            f"• لإضافة مدير: `/add_manager [ID] [DAYS] [NAME]`\n"
            f"• لحذف مدير: `/del_manager [ID]`\n"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")
        return

    # فحص إذا كان المعتمد مشتركاً مفاعلاً
    sub_resp = supabase.table("subscribers").select("expires_at").eq("owner_id", user_id).execute()
    
    # إذا دخل شخص عبر رابط مشترك معين (/start OWNER_ID)
    if context.args and len(context.args) > 0:
        target_owner_id = context.args[0]
        context.user_data['assigned_owner'] = int(target_owner_id)

    if sub_resp.data:
        my_ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        msg = (
            f"أهلاً بك عزيزي المشترك! 👋\n\n"
            f"🔗 **رابط البوت الخاص بمتجرك/قناتك:**\n`{my_ref_link}`\n"
            f"*(قم بنشر هذا الرابط للزبائن ليرسلوا طلباتهم عبره)*\n\n"
            f"🛠 **لإدارة الردود التلقائية:**\n"
            f"`اضف: الكلمة = الرد`\n"
            f"`حذف: الكلمة`\n"
            f"/list - عرض كل الردود"
        )
    else:
        msg = "أهلاً بك! يمكنك الاستفسار عن الخدمات والأسرار، وسيقوم البوت بالرد عليك وتمرير طلبك للإدارة."
        
    await update.message.reply_text(msg, parse_mode="Markdown")

# --- 2. أوامر إضافة وحذف المشتركين والمدراء ---

async def add_sub_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.message.chat_id
    if not is_authorized_admin(sender_id):
        return

    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("⚠️ **الصيغة الصحيحة:**\n`/add [ID] [DAYS] [NAME]`", parse_mode="Markdown")
            return

        sub_id = int(args[0])
        days = int(args[1])
        sub_name = " ".join(args[2:]) if len(args) > 2 else "مشترك جديد"

        expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

        data = {
            "owner_id": sub_id,
            "manager_id": sender_id,
            "name": sub_name,
            "expires_at": expires_at
        }
        supabase.table("subscribers").upsert(data, on_conflict="owner_id").execute()
        
        await update.message.reply_text(f"✅ تم إضافة/تجديد المشترك `{sub_name}` (`{sub_id}`) بنجاح لمدة {days} يوم!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ حدث خطأ أثناء الإضافة:\n`{str(e)}`", parse_mode="Markdown")

async def del_sub_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.message.chat_id
    if not is_authorized_admin(sender_id):
        return

    try:
        if not context.args:
            await update.message.reply_text("⚠️ **الصيغة الصحيحة:**\n`/del_sub [ID]`", parse_mode="Markdown")
            return

        sub_id = int(context.args[0])
        supabase.table("subscribers").delete().eq("owner_id", sub_id).execute()
        await update.message.reply_text(f"🗑️ تم حذف المشترك `{sub_id}` بنجاح.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ أثناء الحذف:\n`{str(e)}`", parse_mode="Markdown")

async def add_manager_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.message.chat_id
    if sender_id != ADMIN_ID:
        return

    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("⚠️ **الصيغة الصحيحة:**\n`/add_manager [ID] [DAYS] [NAME]`", parse_mode="Markdown")
            return

        mgr_id = int(args[0])
        days = int(args[1])
        mgr_name = " ".join(args[2:]) if len(args) > 2 else "مدير جديد"

        expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

        data = {
            "manager_id": mgr_id,
            "name": mgr_name,
            "expires_at": expires_at
        }
        supabase.table("managers").upsert(data, on_conflict="manager_id").execute()
        
        await update.message.reply_text(f"👑 تم إضافة المدير `{mgr_name}` (`{mgr_id}`) بنجاح!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ أثناء إضافة المدير:\n`{str(e)}`", parse_mode="Markdown")

async def del_manager_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.message.chat_id
    if sender_id != ADMIN_ID:
        return

    try:
        if not context.args:
            await update.message.reply_text("⚠️ **الصيغة الصحيحة:**\n`/del_manager [ID]`", parse_mode="Markdown")
            return

        mgr_id = int(context.args[0])
        supabase.table("managers").delete().eq("manager_id", mgr_id).execute()
        await update.message.reply_text(f"🗑️ تم حذف المدير `{mgr_id}` بنجاح.", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ أثناء الحذف:\n`{str(e)}`", parse_mode="Markdown")

# --- 3. إدارة الردود التلقائية ---

async def list_replies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = update.message.chat_id
    try:
        response = supabase.table("custom_replies").select("keyword, reply_text").eq("owner_id", owner_id).execute()
        if not response.data:
            await update.message.reply_text("لا توجد لديك أسئلة أو ردود مسجلة حالياً.")
            return

        text = "📋 **قائمة الأسئلة والردود الخاصة بك:**\n\n"
        for item in response.data:
            text += f"🔹 **الكلمة:** `{item['keyword']}`\n💬 **الرد:** {item['reply_text']}\n-------------------\n"
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ:\n`{str(e)}`", parse_mode="Markdown")

# --- 4. معالجة الرسائل والطلبات ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    raw_text = update.message.text or update.message.caption
    if not raw_text:
        return

    raw_text = raw_text.strip()
    sender_id = update.message.chat_id
    user = update.message.from_user

    # أ) إضافة رد تلقائي (لالمشترك)
    if raw_text.startswith("اضف:") or raw_text.startswith("أضف:"):
        content = raw_text.split(":", 1)[1]
        if "=" in content:
            keyword, reply_text = content.split("=", 1)
            keyword = keyword.strip().lower()
            reply_text = reply_text.strip()

            try:
                data = {"owner_id": sender_id, "keyword": keyword, "reply_text": reply_text}
                supabase.table("custom_replies").upsert(data, on_conflict="owner_id, keyword").execute()
                await update.message.reply_text(f"✅ تم حفظ الرد بنجاح!\n🔹 الكلمة: `{keyword}`\n💬 الرد: {reply_text}", parse_mode="Markdown")
            except Exception as e:
                await update.message.reply_text(f"❌ خطأ أثناء الحفظ: {e}")
            return

    # ب) حذف رد تلقائي (للمشترك)
    if raw_text.startswith("حذف:"):
        keyword = raw_text.split(":", 1)[1].strip().lower()
        if keyword:
            try:
                supabase.table("custom_replies").delete().eq("owner_id", sender_id).eq("keyword", keyword).execute()
                await update.message.reply_text(f"🗑️ تم حذف `{keyword}` بنجاح.", parse_mode="Markdown")
            except Exception as e:
                await update.message.reply_text(f"❌ خطأ: {e}")
            return

    # ج) إذا كان المرسل زبوناً يراسل البوت
    assigned_owner = context.user_data.get('assigned_owner')

    if assigned_owner:
        try:
            response = supabase.table("custom_replies").select("keyword, reply_text").eq("owner_id", assigned_owner).execute()
            if response.data:
                for item in response.data:
                    kw = item["keyword"].lower()
                    pattern = r'(^|[^\w\u0600-\u06FF])' + re.escape(kw) + r'($|[^\w\u0600-\u06FF])'
                    if re.search(pattern, raw_text.lower()):
                        await update.message.reply_text(item["reply_text"])
                        break
            
            username_str = f"@{user.username}" if user.username else "لا يوجد"
            forward_msg = (
                f"📥 **طلب / رسالة جديدة من زبون:**\n\n"
                f"👤 **الزبون:** {user.first_name}\n"
                f"🆔 **الآيدي:** `{sender_id}`\n"
                f"رابط الحساب: {username_str}\n\n"
                f"💬 **الرسالة:**\n{raw_text}"
            )
            await context.bot.send_message(chat_id=assigned_owner, text=forward_msg, parse_mode="Markdown")

        except Exception as e:
            print(f"Error forwarding message: {e}")

if __name__ == "__main__":
    keep_alive()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # الأوامر الرئيسية
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_replies))
    
    # أوامر إدارة المشتركين والمدراء
    app.add_handler(CommandHandler("add", add_sub_cmd))
    app.add_handler(CommandHandler("del_sub", del_sub_cmd))
    app.add_handler(CommandHandler("add_manager", add_manager_cmd))
    app.add_handler(CommandHandler("del_manager", del_manager_cmd))

    # معالجة الرسائل العادية
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(drop_pending_updates=True)
