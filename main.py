import os
from flask import Flask
from threading import Thread
from supabase import create_client, Client
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- إعداد خادم Flask لإبقاء الخدمة تعمل على Render ---
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
        "*(مثال: `حذف: السعر`)*"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def list_replies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner_id = update.message.chat_id
    response = supabase.table("custom_replies").select("keyword, reply_text").eq("owner_id", owner_id).execute()
    
    if not response.data:
        await update.message.reply_text("لا توجد لديك أسئلة أو ردود مسجلة حالياً.")
        return

    text = "📋 **قائمة الأسئلة والردود الخاصة بك:**\n\n"
    for item in response.data:
        text += f"🔹 **السؤال/الكلمة:** `{item['keyword']}`\n💬 **الرد:** {item['reply_text']}\n-------------------\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    raw_text = update.message.text.strip()
    owner_id = update.message.chat_id

    # 1. إضافة أو تعديل رد (اضف: الكلمة = الرد)
    if raw_text.startswith("اضف:") or raw_text.startswith("أضف:"):
        content = raw_text.split(":", 1)[1]
        if "=" in content:
            keyword, reply_text = content.split("=", 1)
            keyword = keyword.strip().lower()
            reply_text = reply_text.strip()

            if not keyword or not reply_text:
                await update.message.reply_text("⚠️ يرجى كتابة الكلمة والرد بشكل صحيح.")
                return

            data = {
                "owner_id": owner_id,
                "keyword": keyword,
                "reply_text": reply_text
            }
            # يتم الحفظ والتحديث بالتوافق مع owner_id
            supabase.table("custom_replies").upsert(data, on_conflict="owner_id, keyword").execute()
            await update.message.reply_text(f"✅ تم حفظ / تغيير الرد بنجاح!\n\n🔹 الكلمة: `{keyword}`\n💬 الرد: {reply_text}", parse_mode="Markdown")
            return
        else:
            await update.message.reply_text("⚠️ اكتب الأمر بهذا الشكل:\n`اضف: الكلمة = الرد`", parse_mode="Markdown")
            return

    # 2. حذف رد (حذف: الكلمة)
    if raw_text.startswith("حذف:"):
        keyword = raw_text.split(":", 1)[1].strip().lower()
        if keyword:
            supabase.table("custom_replies").delete().eq("owner_id", owner_id).eq("keyword", keyword).execute()
            await update.message.reply_text(f"🗑️ تم حذف السؤال/الكلمة `{keyword}` والرد الخاص بها بنجاح.", parse_mode="Markdown")
            return

    # 3. الرد التلقائي عند كتابة الكلمة المفتاحية
    text_lower = raw_text.lower()
    response = supabase.table("custom_replies").select("reply_text").eq("owner_id", owner_id).eq("keyword", text_lower).execute()
    
    if response.data:
        reply = response.data[0]["reply_text"]
        await update.message.reply_text(reply)

if __name__ == "__main__":
    keep_alive()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("list", list_replies))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
