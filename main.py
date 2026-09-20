import os
import re
import logging
from datetime import datetime, timezone
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

ADMIN_ID = 1957078158  # معرف المالك الرئيسي للنظام

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 1. أمر Start والرابط الخاص بكل مشترك ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    bot_info = await context.bot.get_me()
    
    # فحص إذا كان الممتلك مشتركاً مفاعلاً
    sub_resp = supabase.table("subscribers").select("expires_at").eq("owner_id", user_id).execute()
    
    # إذا دخل شخص عبر رابط مشترك معين (/start OWNER_ID)
    if context.args and len(context.args) > 0:
        target_owner_id = context.args[0]
        # حفظ العلاقة: هذا الزبون يتبع للمشترك صاحب target_owner_id
        context.user_data['assigned_owner'] = int(target_owner_id)

    # إذا كان المستخدم مشتركاً رئيساً في البوت
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

# --- 2. إدارة المشتركين والردود ---

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

# --- 3. معالجة الرسائل والطلبات ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    raw_text = update.message.text or update.message.caption
    if not raw_text:
        return

    raw_text = raw_text.strip()
    sender_id = update.message.chat_id
    user = update.message.from_user

    # أ) إضافة رد تلقائي (للمشترك)
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
        # 1. البحث عن الرد التلقائي المحدد من قبل هذا المشترك بالذات
        try:
            response = supabase.table("custom_replies").select("keyword, reply_text").eq("owner_id", assigned_owner).execute()
            replied = False
            if response.data:
                for item in response.data:
                    kw = item["keyword"].lower()
                    pattern = r'(^|[^\w\u0600-\u06FF])' + re.escape(kw) + r'($|[^\w\u0600-\u06FF])'
                    if re.search(pattern, raw_text.lower()):
                        await update.message.reply_text(item["reply_text"])
                        replied = True
                        break
            
            # 2. تحويل الطلب/الرسالة تلقائياً إلى حساب المشترك الأصلي
            username_str = f"@{user.username}" if user.username else "لا يوجد"
            forward_msg = (
                f"📥 **طلب / رسالة جديدة من زبون:**\n\n"
                f"👤 **الزبون:** {user.first_name}\n"
                f"🆔 **الآيدي:** `{sender_id}`\n"
                f"رابط الحساب: {username_str}\n\n"
                f"💬 **الرسالة:**\n{raw_text}"
            )
            # إرسال الإشعار للمشترك صاحب المتجر
            await context.bot.send_message(chat_id=assigned_owner, text=forward_msg, parse_mode="Markdown")

        except Exception as e:
            print(f"Error forwarding message: {e}")

if __name__ == "__main__":
    keep_alive()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_replies))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling(drop_pending_updates=True)
