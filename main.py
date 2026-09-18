import os
from flask import Flask
from threading import Thread
from supabase import create_client, Client
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- إعداد خادم Flask لإبقاء البوت مستيقظاً على Render ---
server = Flask('')

@server.route('/')
def home():
    return "Bot is Live and Running!"

def run():
    # Render يحدد المنفذ تلقائياً عبر متغير البيئة PORT
    port = int(os.environ.get("PORT", 8080))
    server.run(host='0.0.0.0', port=port)

def keep_alive():
    t = Thread(target=run)
    t.daemon = True
    t.start()

# --- إعداد البيانات الخاصة بالبوت وقاعدة البيانات ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك! البوت يعمل بنجاح ومربوط بقاعدة البيانات.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    
    text = update.message.text.lower()
    owner_id = update.message.chat_id

    # البحث عن رد مطابق للكلمة المفتاحية في Supabase
    response = supabase.table("custom_replies").select("reply_text").eq("keyword", text).execute()
    
    if response.data:
        reply = response.data[0]["reply_text"]
        await update.message.reply_text(reply)

if __name__ == "__main__":
    # تشغيل خادم الويب في الخلفية لتفادي خطأ Port Scan Timeout
    keep_alive()
    
    # تشغيل البوت
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
